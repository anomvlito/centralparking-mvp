"""
database.py — Central Parking MVP
Capa de persistencia PostgreSQL.
Misma interfaz pública que la versión SQLite — detect.py, ftp_handler.py y
video_processor.py no requieren cambios.
"""

import os
import datetime
import json
import re
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Optional
from zoneinfo import ZoneInfo

_CL = ZoneInfo("America/Santiago")
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no está configurada en el servicio systemd")


def now_cl() -> datetime.datetime:
    return datetime.datetime.now(_CL)


@contextmanager
def _db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Crea tablas faltantes (idempotente). Se llama al arrancar FastAPI."""
    with _db() as conn:
        with conn.cursor() as cur:
            # Log de cada evento de detección/entrada/salida/void
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detection_log (
                    id          BIGSERIAL    PRIMARY KEY,
                    logged_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    plate       VARCHAR(20)  NOT NULL,
                    action      VARCHAR(20)  NOT NULL,
                    status      VARCHAR(10)  NOT NULL DEFAULT 'REAL',
                    fee         NUMERIC(10,2) NOT NULL DEFAULT 0,
                    confidence  NUMERIC(5,4)  NOT NULL DEFAULT 1.0
                )
            """)
            # Migración: agregar columna image_path a detection_log
            cur.execute("""
                ALTER TABLE detection_log
                ADD COLUMN IF NOT EXISTS image_path VARCHAR(255)
            """)
            # Buffer de staging: deduplicación + quality scoring de detecciones
            cur.execute("""
                CREATE TABLE IF NOT EXISTS staging_detections (
                    id                  BIGSERIAL    PRIMARY KEY,
                    detected_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    plate               VARCHAR(20)  NOT NULL,
                    confidence          NUMERIC(5,4) NOT NULL,
                    quality_score       NUMERIC(5,4),
                    combined_score      NUMERIC(5,4),
                    sharpness           NUMERIC(5,4),
                    contrast_score      NUMERIC(5,4),
                    brightness_score    NUMERIC(5,4),
                    ocr_clarity         NUMERIC(5,4),
                    strategy            VARCHAR(50),
                    status              VARCHAR(20)  NOT NULL DEFAULT 'pending',
                    rejection_reason    VARCHAR(100),
                    expires_at          TIMESTAMPTZ  NOT NULL,
                    image_path          VARCHAR(255)
                )
            """)
            # Migración: EXIT también compite por calidad en staging (antes era
            # inmediato y usaba el primer frame que confirmara alejamiento, casi
            # siempre el más lejano/peor de la ráfaga).
            cur.execute("""
                ALTER TABLE staging_detections
                ADD COLUMN IF NOT EXISTS kind VARCHAR(10) NOT NULL DEFAULT 'ENTRY'
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_staging_detections_plate_kind_status
                ON staging_detections(plate, kind, status)
            """)
            # Migración: agregar columnas de fotos a parking_sessions
            cur.execute("""
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS entry_image_path VARCHAR(255)
            """)
            cur.execute("""
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS exit_image_path VARCHAR(255)
            """)
            cur.execute("""
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
            """)
            cur.execute("ALTER TABLE parking_sessions ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ")
            cur.execute("""
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES users(id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_log_plate
                ON detection_log(plate)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_log_logged_at
                ON detection_log(logged_at)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_log_action
                ON detection_log(action)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_staging_detections_plate_status
                ON staging_detections(plate, status)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_staging_detections_expires_at
                ON staging_detections(expires_at)
            """)


# ─────────────────────── vehículos activos ──────────────────────────────────

def load_db() -> dict:
    """Devuelve {plate: {...}} de vehículos actualmente en el estacionamiento."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT plate,
                       EXTRACT(EPOCH FROM entry_time)::bigint * 1000 AS entry_time_ms,
                       is_event,
                       event_fee
                FROM parking_sessions
                WHERE exit_time IS NULL AND status != 'VOID'
            """)
            rows = cur.fetchall()
    return {
        r["plate"]: {
            "plate":     r["plate"],
            "entryTime": int(r["entry_time_ms"]),
            "isEvent":   bool(r["is_event"]),
            "eventFee":  float(r["event_fee"]) if r["event_fee"] is not None else None,
        }
        for r in rows
    }


def upsert_vehicle(plate: str, entry_time_ms: float,
                   is_event: bool = False, event_fee=None, image_path: str = None,
                   source: str = "camera_auto"):
    plate = re.sub(r"[^A-Z0-9]", "", plate.upper())
    entry_dt = datetime.datetime.fromtimestamp(entry_time_ms / 1000, tz=_CL)
    with _db() as conn:
        with conn.cursor() as cur:
            # Serializa altas concurrentes de la misma patente. Sin este lock,
            # dos workers pueden hacer el SELECT antes de que cualquiera inserte.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (plate,))
            cur.execute(
                "INSERT INTO vehicles (plate) VALUES (%s) ON CONFLICT (plate) DO NOTHING",
                (plate,)
            )
            cur.execute("""
                SELECT id FROM parking_sessions
                WHERE plate = %s AND exit_time IS NULL AND status != 'VOID'
                LIMIT 1
            """, (plate,))
            existing = cur.fetchone()
            if existing:
                # La detección repetida no debe reiniciar la hora ni reemplazar
                # los datos de la sesión que ya está abierta.
                return False
            else:
                cur.execute("""
                    INSERT INTO parking_sessions
                        (plate, entry_time, is_event, event_fee, entry_image_path, source, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'REAL')
                """, (plate, entry_dt, is_event, event_fee, image_path, source))
                return True


def remove_vehicle(plate: str, fee: float = 0, image_path: str = None):
    """Cierra la sesión activa registrando la salida, tarifa e imagen."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE parking_sessions
                SET exit_time = now(), fee = %s, exit_image_path = %s, updated_at = now()
                WHERE plate = %s AND exit_time IS NULL AND status != 'VOID'
            """, (fee or 0, image_path, plate))


def void_vehicle(plate: str):
    """Anula la sesión activa sin registrar salida (no se pierde el registro)."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE parking_sessions
                SET status = 'VOID', exit_time = now(), updated_at = now()
                WHERE plate = %s AND exit_time IS NULL
            """, (plate,))


def vehicle_exists(plate: str) -> bool:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM parking_sessions
                WHERE plate = %s AND exit_time IS NULL AND status != 'VOID'
            """, (plate,))
            return cur.fetchone() is not None


# ─────────────────────── dedup por lectura de OCR similar ───────────────────

# Ventana y distancia alineadas con el criterio ya usado en correct_session_plate
# (± 5 minutos) para reasignar detection_log/staging_detections tras una corrección.
PLATE_FUZZY_WINDOW_MIN = int(os.environ.get("PLATE_FUZZY_WINDOW_MIN", "5"))
PLATE_FUZZY_MAX_DISTANCE = int(os.environ.get("PLATE_FUZZY_MAX_DISTANCE", "2"))


def _levenshtein(a: str, b: str) -> int:
    """Distancia de edición simple (sin librerías externas)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def find_similar_active_session(plate: str) -> Optional[dict]:
    """
    Busca una sesión activa reciente cuya patente sea muy parecida a `plate`
    (posible error de OCR sobre el mismo auto: dígito perdido por luces,
    carácter confundido, etc.), en vez de un vehículo nuevo.

    Se limita a una ventana corta (PLATE_FUZZY_WINDOW_MIN) y a sesiones de
    origen cámara, para minimizar el riesgo de fusionar dos autos reales con
    patentes parecidas que entren casi al mismo tiempo.
    """
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, plate FROM parking_sessions
                WHERE exit_time IS NULL AND status != 'VOID'
                  AND source = 'camera_auto'
                  AND entry_time > now() - make_interval(mins => %s)
            """, (PLATE_FUZZY_WINDOW_MIN,))
            rows = cur.fetchall()

    best = None
    for r in rows:
        if r["plate"] == plate:
            continue
        dist = _levenshtein(plate, r["plate"])
        if dist <= PLATE_FUZZY_MAX_DISTANCE and (best is None or dist < best["distance"]):
            best = {"id": r["id"], "plate": r["plate"], "distance": dist}
    return best


def log_audit_event(plate: Optional[str], event_type: str, details: dict):
    """Registra un evento en audit_log (uso general, fuera de staging.py)."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_log (plate, event_type, details)
                VALUES (%s, %s, %s::jsonb)
            """, (plate, event_type, json.dumps(details)))


# ─────────────────────── log / historial ────────────────────────────────────

def log_to_db(plate: str, action: str, status: str = "REAL",
              fee: float = 0, conf: float = 1.0, image_path: str = None):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO detection_log (plate, action, status, fee, confidence, image_path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (plate, action, status, fee, conf, image_path))


def get_history(limit: int = 200, date: str = None) -> list:
    """Lee desde parking_sessions como fuente de verdad: 0 duplicados por diseño."""
    with _db() as conn:
        with conn.cursor() as cur:
            if date:
                # Filtrado server-side: solo sesiones con entry/exit en esa fecha
                cur.execute("""
                    WITH session_events AS (
                        SELECT id as session_id, plate, entry_time as event_time,
                               'ENTRY' as action, source, 0::numeric as fee,
                               COALESCE(ai_confidence, 1.0) as confidence,
                               entry_image_path as image_path, status as session_status,
                               review_status
                        FROM parking_sessions
                        WHERE status != 'VOID'
                          AND (entry_time AT TIME ZONE 'America/Santiago')::date = %s::date

                        UNION ALL

                        SELECT id, plate, exit_time,
                               'EXIT', source, COALESCE(fee, 0),
                               COALESCE(ai_confidence, 1.0),
                               exit_image_path, status, review_status
                        FROM parking_sessions
                        WHERE exit_time IS NOT NULL AND status != 'VOID'
                          AND (exit_time AT TIME ZONE 'America/Santiago')::date = %s::date
                    )
                    SELECT session_id, plate, event_time, action, source, fee, confidence, image_path, session_status, review_status
                    FROM session_events
                    ORDER BY event_time DESC
                    LIMIT %s
                """, (date, date, limit))
            else:
                # Sin filtro de fecha: las sesiones más recientes
                cur.execute("""
                    WITH session_events AS (
                        SELECT id as session_id, plate, entry_time as event_time,
                               'ENTRY' as action, source, 0::numeric as fee,
                               COALESCE(ai_confidence, 1.0) as confidence,
                               entry_image_path as image_path, status as session_status,
                               review_status
                        FROM parking_sessions
                        WHERE status != 'VOID'

                        UNION ALL

                        SELECT id, plate, exit_time,
                               'EXIT', source, COALESCE(fee, 0),
                               COALESCE(ai_confidence, 1.0),
                               exit_image_path, status, review_status
                        FROM parking_sessions
                        WHERE exit_time IS NOT NULL AND status != 'VOID'
                    )
                    SELECT session_id, plate, event_time, action, source, fee, confidence, image_path, session_status, review_status
                    FROM session_events
                    ORDER BY event_time DESC
                    LIMIT %s
                """, (limit,))
            rows = cur.fetchall()

    result = []
    backend_url = os.environ.get("BACKEND_URL", "https://2.24.69.49.nip.io").rstrip("/")

    for r in rows:
        image_url = f"{backend_url}/api/monitor/file/{r['image_path']}" if r["image_path"] else None
        entry = {
            "session_id": int(r["session_id"]),
            "timestamp":  r["event_time"].astimezone(_CL).strftime("%Y-%m-%d %H:%M:%S"),
            "plate":      r["plate"],
            "action":     r["action"],
            "status":     ("AUTO_CLOSED" if r["session_status"] == "AUTO_CLOSED"
                           else "FTP_AUTO" if r["source"] == "camera_auto" else "MANUAL"),
            "fee":        float(r["fee"]),
            "confidence": float(r["confidence"]),
            "image_url":  image_url,
            "review_status": r["review_status"],
        }
        result.append(entry)
    return result


def get_sightings(limit: int = 50, plate: str = None, near: str = None,
                  window_minutes: int = 30, date: str = None) -> list:
    """
    Avistamientos de cámara con foto (detection_log) — no confundir con
    get_history(), que lee parking_sessions (entradas/salidas manuales).

    Incluye acción 'DETECTED' (avistamiento plano, flujo actual) y también
    'ENTRY'/'EXIT' (flujo anterior, que sí abría/cerraba parking_sessions
    directamente): son la misma clase de evento — una foto de la patente en
    un momento dado — solo que logueadas bajo un nombre distinto según qué
    versión del pipeline estaba corriendo. Filtrar solo por 'DETECTED'
    dejaba afuera toda foto tomada antes del cambio de arquitectura.

    Sin `plate` ni `date`: feed con el avistamiento más reciente por cada
    patente (para listar "qué autos se vieron últimamente").
    Sin `plate` y con `date` ("YYYY-MM-DD"): igual, pero acotado a esa fecha
    (para reconstruir el Historial de un día puntual).
    Con `plate` y `near` ("YYYY-MM-DD HH:MM:SS", hora de Chile): solo fotos
    dentro de `window_minutes` de esa hora, ordenadas por cercanía — para
    una fila de sesión real, evita mostrar la foto de un avistamiento no
    relacionado de esa misma patente en otro momento.
    Con `plate` y `date` ("YYYY-MM-DD", hora de Chile): todas las fotos de
    esa patente tomadas ese día — para una fila de avistamiento sin sesión,
    que representa a la patente en ese día, no un instante puntual.
    Con solo `plate`: todas las fotos recientes de esa patente, sin acotar.
    """
    with _db() as conn:
        with conn.cursor() as cur:
            if plate and near:
                normalized = re.sub(r"[^A-Z0-9]", "", plate.upper())
                near_dt = datetime.datetime.strptime(near, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CL)
                cur.execute("""
                    SELECT plate, logged_at, confidence, image_path
                    FROM detection_log
                    WHERE action IN ('DETECTED', 'ENTRY', 'EXIT')
                      AND image_path IS NOT NULL AND plate = %s
                      AND logged_at BETWEEN %s - make_interval(mins => %s)
                                         AND %s + make_interval(mins => %s)
                    ORDER BY ABS(EXTRACT(EPOCH FROM (logged_at - %s)))
                    LIMIT %s
                """, (normalized, near_dt, window_minutes, near_dt, window_minutes, near_dt, limit))
            elif plate and date:
                normalized = re.sub(r"[^A-Z0-9]", "", plate.upper())
                cur.execute("""
                    SELECT plate, logged_at, confidence, image_path
                    FROM detection_log
                    WHERE action IN ('DETECTED', 'ENTRY', 'EXIT')
                      AND image_path IS NOT NULL AND plate = %s
                      AND (logged_at AT TIME ZONE 'America/Santiago')::date = %s::date
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (normalized, date, limit))
            elif plate:
                normalized = re.sub(r"[^A-Z0-9]", "", plate.upper())
                cur.execute("""
                    SELECT plate, logged_at, confidence, image_path
                    FROM detection_log
                    WHERE action IN ('DETECTED', 'ENTRY', 'EXIT')
                      AND image_path IS NOT NULL AND plate = %s
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (normalized, limit))
            elif date:
                cur.execute("""
                    SELECT plate, logged_at, confidence, image_path FROM (
                        SELECT DISTINCT ON (plate) plate, logged_at, confidence, image_path
                        FROM detection_log
                        WHERE action IN ('DETECTED', 'ENTRY', 'EXIT')
                          AND image_path IS NOT NULL
                          AND (logged_at AT TIME ZONE 'America/Santiago')::date = %s::date
                        ORDER BY plate, logged_at DESC
                    ) latest
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (date, limit))
            else:
                cur.execute("""
                    SELECT plate, logged_at, confidence, image_path FROM (
                        SELECT DISTINCT ON (plate) plate, logged_at, confidence, image_path
                        FROM detection_log
                        WHERE action IN ('DETECTED', 'ENTRY', 'EXIT')
                          AND image_path IS NOT NULL
                        ORDER BY plate, logged_at DESC
                    ) latest
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (limit,))
            rows = cur.fetchall()

    backend_url = os.environ.get("BACKEND_URL", "https://2.24.69.49.nip.io").rstrip("/")
    return [
        {
            "plate":      r["plate"],
            "timestamp":  r["logged_at"].astimezone(_CL).strftime("%Y-%m-%d %H:%M:%S"),
            "confidence": float(r["confidence"]),
            "image_url":  f"{backend_url}/api/monitor/file/{r['image_path']}" if r["image_path"] else None,
        }
        for r in rows
    ]


def review_session(session_id: int, review_status: str, user_id: int, username: str) -> dict:
    if review_status not in {"PLATE_OK", "DUPLICATE"}:
        raise ValueError("Estado de revisión inválido")
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT plate, status FROM parking_sessions WHERE id = %s FOR UPDATE", (session_id,))
            row = cur.fetchone()
            if not row:
                raise LookupError("Sesión no encontrada")
            status = "VOID" if review_status == "DUPLICATE" else row["status"]
            cur.execute("""
                UPDATE parking_sessions
                SET review_status = %s, reviewed_at = now(), reviewed_by = %s, status = %s
                WHERE id = %s
            """, (review_status, user_id, status, session_id))
            details = json.dumps({"session_id": session_id, "review_status": review_status,
                                  "reviewed_by": username})
            cur.execute("""
                INSERT INTO audit_log (plate, event_type, details)
                VALUES (%s, 'REVIEW_STATUS', %s::jsonb)
            """, (row["plate"], details))
    return {"session_id": session_id, "plate": row["plate"],
            "review_status": review_status, "removed": review_status == "DUPLICATE"}


def correct_session_plate(session_id: int, new_plate: str, changed_by: str) -> dict:
    """Corrige una patente y sus archivos asociados para una sesión completa."""
    normalized = re.sub(r"[^A-Z0-9]", "", new_plate.upper())
    if not 4 <= len(normalized) <= 8:
        raise ValueError("La patente debe tener entre 4 y 8 letras o números")

    moved: list[tuple[str, str]] = []
    missing_files: list[str] = []
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, plate, entry_time, exit_time, entry_image_path, exit_image_path
                    FROM parking_sessions WHERE id = %s FOR UPDATE
                """, (session_id,))
                session = cur.fetchone()
                if not session:
                    raise LookupError("Sesión no encontrada")

                old_plate = session["plate"]
                if old_plate == normalized:
                    return {"session_id": session_id, "old_plate": old_plate,
                            "new_plate": normalized, "renamed_files": [], "missing_files": []}

                path_changes: dict[str, str] = {}
                for rel_path in {session["entry_image_path"], session["exit_image_path"]} - {None}:
                    old_abs = os.path.realpath(os.path.join("/ftp", rel_path))
                    if not old_abs.startswith("/ftp/"):
                        raise ValueError("Ruta de imagen inválida")
                    filename = os.path.basename(old_abs)
                    new_filename = filename.replace(old_plate, normalized, 1)
                    if new_filename == filename:
                        continue
                    new_abs = os.path.join(os.path.dirname(old_abs), new_filename)
                    new_rel = os.path.relpath(new_abs, "/ftp")
                    if not os.path.isfile(old_abs):
                        missing_files.append(rel_path)
                        continue
                    if os.path.exists(new_abs):
                        raise FileExistsError(f"Ya existe el archivo {new_rel}")
                    os.rename(old_abs, new_abs)
                    moved.append((old_abs, new_abs))
                    path_changes[rel_path] = new_rel

                cur.execute("INSERT INTO vehicles (plate) VALUES (%s) ON CONFLICT DO NOTHING", (normalized,))
                cur.execute("UPDATE parking_sessions SET plate = %s WHERE id = %s", (normalized, session_id))

                for old_path, new_path in path_changes.items():
                    cur.execute("""
                        UPDATE parking_sessions
                        SET entry_image_path = CASE WHEN entry_image_path = %s THEN %s ELSE entry_image_path END,
                            exit_image_path = CASE WHEN exit_image_path = %s THEN %s ELSE exit_image_path END
                        WHERE id = %s
                    """, (old_path, new_path, old_path, new_path, session_id))
                    cur.execute("UPDATE detection_log SET image_path = %s WHERE image_path = %s", (new_path, old_path))
                    cur.execute("UPDATE staging_detections SET image_path = %s WHERE image_path = %s", (new_path, old_path))

                cur.execute("""
                    UPDATE detection_log SET plate = %s
                    WHERE plate = %s
                      AND logged_at BETWEEN %s - INTERVAL '5 minutes'
                                        AND COALESCE(%s, %s + INTERVAL '20 hours') + INTERVAL '5 minutes'
                """, (normalized, old_plate, session["entry_time"], session["exit_time"], session["entry_time"]))
                cur.execute("""
                    UPDATE staging_detections SET plate = %s
                    WHERE plate = %s
                      AND detected_at BETWEEN %s - INTERVAL '5 minutes'
                                          AND COALESCE(%s, %s + INTERVAL '20 hours') + INTERVAL '5 minutes'
                """, (normalized, old_plate, session["entry_time"], session["exit_time"], session["entry_time"]))

                details = {
                    "session_id": session_id, "old_plate": old_plate,
                    "new_plate": normalized, "changed_by": changed_by,
                    "renamed_files": list(path_changes.values()),
                    "missing_files": missing_files,
                }
                cur.execute("""
                    INSERT INTO audit_log (plate, event_type, details)
                    VALUES (%s, 'PLATE_CORRECTION', %s::jsonb)
                """, (normalized, json.dumps(details)))
                cur.execute("""
                    DELETE FROM vehicles v WHERE v.plate = %s
                      AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.plate = v.plate)
                """, (old_plate,))

        return {"session_id": session_id, "old_plate": old_plate,
                "new_plate": normalized,
                "renamed_files": list(path_changes.values()),
                "missing_files": missing_files}
    except Exception:
        for old_abs, new_abs in reversed(moved):
            if os.path.exists(new_abs) and not os.path.exists(old_abs):
                os.rename(new_abs, old_abs)
        raise


def get_stats_today() -> dict:
    today = now_cl().replace(hour=0, minute=0, second=0, microsecond=0)
    with _db() as conn:
        with conn.cursor() as cur:
            # Contar entries/exits/revenue desde parking_sessions (fuente de verdad)
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE entry_time >= %s)                   AS entries,
                    COUNT(*) FILTER (WHERE exit_time IS NOT NULL AND exit_time >= %s) AS exits,
                    COALESCE(SUM(fee) FILTER (WHERE exit_time >= %s), 0)        AS revenue
                FROM parking_sessions
                WHERE status != 'VOID'
            """, (today, today, today))
            stats = cur.fetchone()

            # Contar vehículos actualmente estacionados
            cur.execute("""
                SELECT COUNT(*) AS parked
                FROM parking_sessions
                WHERE exit_time IS NULL
                  AND status NOT IN ('VOID', 'AUTO_CLOSED')
                  AND entry_time > now() - INTERVAL '20 hours'
            """)
            parked = cur.fetchone()
    return {
        "today_income":  float(stats["revenue"]),
        "today_entries": int(stats["entries"]),
        "today_exits":   int(stats["exits"]),
        "parked_now":    int(parked["parked"]),
    }


def clear_history():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM detection_log")
