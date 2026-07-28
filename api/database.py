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
            cur.execute("""
                ALTER TABLE detection_log
                ADD COLUMN IF NOT EXISTS normalized_plate VARCHAR(20)
            """)
            cur.execute("""
                ALTER TABLE detection_log
                ADD COLUMN IF NOT EXISTS direction VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'
            """)
            cur.execute("""
                ALTER TABLE detection_log
                ADD COLUMN IF NOT EXISTS match_status VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED'
            """)
            cur.execute("""
                ALTER TABLE detection_log
                ADD COLUMN IF NOT EXISTS linked_session_id BIGINT REFERENCES parking_sessions(id)
            """)
            cur.execute("""
                ALTER TABLE detection_log
                ADD COLUMN IF NOT EXISTS source VARCHAR(40)
            """)
            cur.execute("""
                UPDATE detection_log
                SET normalized_plate = regexp_replace(upper(plate), '[^A-Z0-9]', '', 'g')
                WHERE normalized_plate IS NULL
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detection_match_status_backup_hu011 (
                    detection_id BIGINT PRIMARY KEY REFERENCES detection_log(id),
                    previous_status VARCHAR(20) NOT NULL,
                    backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                INSERT INTO detection_match_status_backup_hu011
                    (detection_id, previous_status)
                SELECT id, match_status
                FROM detection_log
                WHERE match_status = 'UNMATCHED'
                  AND length(normalized_plate) != 6
                ON CONFLICT (detection_id) DO NOTHING
            """)
            cur.execute("""
                UPDATE detection_log AS detection
                SET match_status = 'INVALID_FORMAT'
                FROM detection_match_status_backup_hu011 AS backup
                WHERE detection.id = backup.detection_id
                  AND detection.match_status = 'UNMATCHED'
                  AND length(detection.normalized_plate) != 6
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
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS entry_detection_id BIGINT REFERENCES detection_log(id)
            """)
            cur.execute("""
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS exit_detection_id BIGINT REFERENCES detection_log(id)
            """)
            cur.execute("""
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS match_type VARCHAR(20) NOT NULL DEFAULT 'UNRESOLVED'
            """)
            cur.execute("""
                ALTER TABLE parking_sessions
                ADD COLUMN IF NOT EXISTS match_confidence NUMERIC(5,4)
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
                CREATE INDEX IF NOT EXISTS idx_detection_log_match_status
                ON detection_log(match_status, logged_at DESC)
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_parking_sessions_entry_detection
                ON parking_sessions(entry_detection_id)
                WHERE entry_detection_id IS NOT NULL AND status != 'VOID'
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_parking_sessions_exit_detection
                ON parking_sessions(exit_detection_id)
                WHERE exit_detection_id IS NOT NULL AND status != 'VOID'
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_staging_detections_plate_status
                ON staging_detections(plate, status)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_staging_detections_expires_at
                ON staging_detections(expires_at)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plate_exclusions (
                    normalized_plate VARCHAR(6) PRIMARY KEY,
                    max_distance INTEGER NOT NULL DEFAULT 1 CHECK (max_distance BETWEEN 0 AND 2),
                    active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    created_by VARCHAR(100) NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS zero_duration_backup_hu012 (
                    session_id BIGINT PRIMARY KEY REFERENCES parking_sessions(id),
                    previous_status VARCHAR(20) NOT NULL,
                    backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plate_exclusion_session_backup_hu012 (
                    session_id BIGINT PRIMARY KEY REFERENCES parking_sessions(id),
                    previous_status VARCHAR(20) NOT NULL,
                    backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                INSERT INTO zero_duration_backup_hu012 (session_id, previous_status)
                SELECT id, status FROM parking_sessions
                WHERE status != 'VOID' AND entry_time IS NOT NULL AND exit_time IS NOT NULL
                  AND exit_time >= entry_time
                  AND exit_time < entry_time + INTERVAL '1 minute'
                ON CONFLICT (session_id) DO NOTHING
            """)
            cur.execute("""
                UPDATE parking_sessions session SET status = 'VOID'
                FROM zero_duration_backup_hu012 backup
                WHERE session.id = backup.session_id AND session.status != 'VOID'
            """)
            cur.execute("""
                UPDATE detection_log SET match_status = 'DISMISSED'
                WHERE linked_session_id IN (SELECT session_id FROM zero_duration_backup_hu012)
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


def get_direction_audit_metrics(date: str = None, limit: int = 5000) -> dict:
    """Agrega evaluaciones direccionales sin exponer patentes."""
    bounded_limit = max(1, min(limit, 10000))
    with _db() as conn:
        with conn.cursor() as cur:
            if date:
                cur.execute("""
                    SELECT details
                    FROM audit_log
                    WHERE event_type = 'DIRECTION_EVALUATED'
                      AND logged_at::date = %s::date
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (date, bounded_limit))
            else:
                cur.execute("""
                    SELECT details
                    FROM audit_log
                    WHERE event_type = 'DIRECTION_EVALUATED'
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (bounded_limit,))
            rows = cur.fetchall()

    directions: dict[str, int] = {}
    unknown_reasons: dict[str, int] = {}
    modes: dict[str, int] = {}
    configurations: dict[str, int] = {}
    for row in rows:
        details = row["details"]
        if isinstance(details, str):
            details = json.loads(details)
        direction = details.get("direction", "UNKNOWN")
        directions[direction] = directions.get(direction, 0) + 1
        if direction == "UNKNOWN":
            reason = details.get("reason") or "unspecified"
            unknown_reasons[reason] = unknown_reasons.get(reason, 0) + 1
        mode = details.get("mode", "unknown")
        modes[mode] = modes.get(mode, 0) + 1
        version = details.get("config_version", "unknown")
        configurations[version] = configurations.get(version, 0) + 1

    return {
        "total": len(rows),
        "directions": directions,
        "unknown_reasons": unknown_reasons,
        "modes": modes,
        "configurations": configurations,
        "truncated": len(rows) == bounded_limit,
    }


# ─────────────────────── log / historial ────────────────────────────────────

def normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", plate.upper())


def is_valid_plate(plate: str) -> bool:
    return len(normalize_plate(plate)) == 6


def plate_matches_exclusion(candidate: str, excluded: str, max_distance: int) -> bool:
    return _levenshtein(
        normalize_plate(candidate or ""), normalize_plate(excluded or "")
    ) <= max_distance


def is_zero_minute_duration(
    entry_time: datetime.datetime, exit_time: datetime.datetime
) -> bool:
    return 0 < (exit_time - entry_time).total_seconds() < 60


def _is_excluded(cur, normalized: str) -> bool:
    cur.execute("""
        SELECT normalized_plate, max_distance FROM plate_exclusions
        WHERE active = true
    """)
    return any(
        plate_matches_exclusion(normalized, row["normalized_plate"], row["max_distance"])
        for row in cur.fetchall()
    )


def add_plate_exclusion(plate: str, max_distance: int, username: str) -> dict:
    normalized = normalize_plate(plate)
    if len(normalized) != 6:
        raise ValueError("La patente excluida debe tener exactamente 6 caracteres")
    if max_distance not in {0, 1, 2}:
        raise ValueError("La distancia debe estar entre 0 y 2")
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO plate_exclusions
                    (normalized_plate, max_distance, active, created_by)
                VALUES (%s, %s, true, %s)
                ON CONFLICT (normalized_plate) DO UPDATE
                SET max_distance = EXCLUDED.max_distance, active = true,
                    created_by = EXCLUDED.created_by
            """, (normalized, max_distance, username))
            cur.execute("""
                SELECT id, normalized_plate FROM detection_log
                WHERE match_status = 'UNMATCHED'
            """)
            ids = [
                row["id"] for row in cur.fetchall()
                if plate_matches_exclusion(
                    row["normalized_plate"], normalized, max_distance
                )
            ]
            if ids:
                cur.execute("""
                    UPDATE detection_log SET match_status = 'DISMISSED'
                    WHERE id = ANY(%s)
                """, (ids,))
            cur.execute("""
                SELECT id, plate, status FROM parking_sessions
                WHERE status != 'VOID'
            """)
            matching_sessions = [
                row for row in cur.fetchall()
                if plate_matches_exclusion(row["plate"], normalized, max_distance)
            ]
            session_ids = [row["id"] for row in matching_sessions]
            if session_ids:
                cur.executemany("""
                    INSERT INTO plate_exclusion_session_backup_hu012
                        (session_id, previous_status)
                    VALUES (%s, %s)
                    ON CONFLICT (session_id) DO NOTHING
                """, [(row["id"], row["status"]) for row in matching_sessions])
                cur.execute("""
                    UPDATE parking_sessions SET status = 'VOID'
                    WHERE id = ANY(%s)
                """, (session_ids,))
                cur.execute("""
                    UPDATE detection_log SET match_status = 'DISMISSED'
                    WHERE linked_session_id = ANY(%s)
                """, (session_ids,))
            cur.execute("""
                INSERT INTO audit_log (plate, event_type, details)
                VALUES (NULL, 'PLATE_EXCLUDED', %s::jsonb)
            """, (json.dumps({
                "distance": max_distance,
                "dismissed_count": len(ids),
                "voided_sessions": len(session_ids),
                "username": username,
            }),))
    return {
        "max_distance": max_distance,
        "dismissed_count": len(ids),
        "voided_sessions": len(session_ids),
    }


def log_to_db(plate: str, action: str, status: str = "REAL",
              fee: float = 0, conf: float = 1.0, image_path: str = None,
              direction: str = "UNKNOWN", source: str = None):
    normalized = normalize_plate(plate)
    with _db() as conn:
        with conn.cursor() as cur:
            match_status = (
                "INVALID_FORMAT" if len(normalized) != 6
                else "DISMISSED" if _is_excluded(cur, normalized)
                else "UNMATCHED"
            )
            cur.execute("""
                INSERT INTO detection_log
                    (plate, normalized_plate, action, status, fee, confidence,
                     image_path, direction, match_status, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (plate, normalized, action, status, fee, conf, image_path,
                  direction, match_status, source or status))
            row = cur.fetchone()
    return int(row["id"])


_DETECTION_MATCH_STATUSES = {
    "UNMATCHED", "MATCHED_ENTRY", "MATCHED_EXIT", "DISMISSED",
    "INVALID_FORMAT",
}


def build_stay_proposals(events: list[dict], max_hours: int = 24) -> list[dict]:
    valid = sorted(
        [event for event in events if len(event["normalized_plate"]) == 6],
        key=lambda event: event["detected_at"],
    )
    used: set[int] = set()
    proposals: list[dict] = []
    max_seconds = max_hours * 3600

    def add_pairs(max_distance: int, match_type: str) -> None:
        for index, entry in enumerate(valid):
            if entry["detection_id"] in used:
                continue
            best = None
            for exit_event in valid[index + 1:]:
                if exit_event["detection_id"] in used:
                    continue
                seconds = (
                    datetime.datetime.fromisoformat(exit_event["detected_at"])
                    - datetime.datetime.fromisoformat(entry["detected_at"])
                ).total_seconds()
                if seconds <= 0 or seconds > max_seconds:
                    continue
                distance = _levenshtein(
                    entry["normalized_plate"], exit_event["normalized_plate"]
                )
                if distance > max_distance:
                    continue
                score = min(entry["confidence"], exit_event["confidence"])
                if entry["direction"] == "APPROACHING":
                    score += 0.05
                if exit_event["direction"] == "DEPARTING":
                    score += 0.05
                candidate = (distance, -score, seconds, exit_event)
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
            if best is None:
                continue
            exit_event = best[3]
            used.update({entry["detection_id"], exit_event["detection_id"]})
            proposals.append({
                "entry": entry,
                "exit": exit_event,
                "resolved_plate": entry["normalized_plate"],
                "match_type": match_type,
                "distance": best[0],
                "score": round(-best[1], 4),
                "duration_minutes": int(best[2] // 60),
            })

    add_pairs(0, "EXACT")
    add_pairs(1, "FUZZY")
    return sorted(proposals, key=lambda item: item["exit"]["detected_at"], reverse=True)


def get_stay_proposals(
    date: str, limit: int = 200, include_zero_duration: bool = False
) -> list[dict]:
    day_start, _ = _operational_day_bounds(date)
    previous_date = (day_start.date() - datetime.timedelta(days=1)).isoformat()
    events = get_detection_events(limit=500, match_status="UNMATCHED", date=date)
    events += get_detection_events(
        limit=500, match_status="UNMATCHED", date=previous_date
    )
    unique = {event["detection_id"]: event for event in events}
    proposals = build_stay_proposals(list(unique.values()))
    if not include_zero_duration:
        proposals = [
            item for item in proposals if item["duration_minutes"] > 0
        ]
    return proposals[:max(1, min(limit, 200))]


def auto_reconcile_exact_matches(date: str, limit: int = 200) -> dict:
    proposals = [
        item for item in get_stay_proposals(
            date=date, limit=limit, include_zero_duration=True
        )
        if item["match_type"] == "EXACT" or item["duration_minutes"] == 0
    ]
    reconciled = 0
    duplicates = 0
    skipped = 0
    for item in proposals:
        try:
            result = reconcile_detection_events(
                item["entry"]["detection_id"],
                item["exit"]["detection_id"],
                item["resolved_plate"],
                match_type=item["match_type"],
            )
            if result.get("status") == "DUPLICATE":
                duplicates += 1
            else:
                reconciled += 1
        except (LookupError, ValueError):
            skipped += 1
    return {
        "date": date,
        "reconciled": reconciled,
        "duplicates": duplicates,
        "skipped": skipped,
    }


def promote_review_image(
    plate: str, image_path: str, detected_at: datetime.datetime, username: str
) -> dict:
    normalized = normalize_plate(plate)
    if len(normalized) != 6:
        raise ValueError("La patente normalizada debe tener exactamente 6 caracteres")
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM detection_log WHERE image_path = %s LIMIT 1",
                (image_path,),
            )
            existing = cur.fetchone()
            if existing:
                raise ValueError("La imagen ya fue promovida")
            cur.execute("""
                INSERT INTO detection_log
                    (logged_at, plate, normalized_plate, action, status, fee,
                     confidence, image_path, direction, match_status, source)
                VALUES (%s, %s, %s, 'DETECTED', 'REVIEW_MANUAL', 0, 1.0,
                        %s, 'UNKNOWN', 'UNMATCHED', 'review_manual')
                RETURNING id
            """, (detected_at, plate, normalized, image_path))
            detection_id = int(cur.fetchone()["id"])
            cur.execute("""
                INSERT INTO audit_log (plate, event_type, details)
                VALUES (%s, 'REVIEW_PROMOTED', %s::jsonb)
            """, (normalized, json.dumps({
                "detection_id": detection_id,
                "image_path": image_path,
                "username": username,
            })))
    return {"detection_id": detection_id, "match_status": "UNMATCHED"}


def _operational_day_bounds(value: str) -> tuple[datetime.datetime, datetime.datetime]:
    try:
        target_date = datetime.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("La fecha debe usar el formato YYYY-MM-DD") from exc
    day_start = datetime.datetime.combine(
        target_date, datetime.time.min, tzinfo=_CL
    )
    return day_start, day_start + datetime.timedelta(days=1)


def _add_operational_day_overlap(
    conditions: list[str], params: list, value: str
) -> None:
    day_start, day_end = _operational_day_bounds(value)
    conditions.extend([
        "COALESCE(entry_time, exit_time) < %s",
        "COALESCE(exit_time, entry_time, 'infinity'::timestamptz) >= %s",
    ])
    params.extend([day_end, day_start])


def _image_url(image_path: str | None) -> str | None:
    if not image_path:
        return None
    backend_url = os.environ.get(
        "BACKEND_URL", "https://2.24.69.49.nip.io"
    ).rstrip("/")
    return f"{backend_url}/api/monitor/file/{image_path}"


def get_detection_events(
    limit: int = 100,
    match_status: str | None = None,
    date: str | None = None,
) -> list:
    bounded_limit = max(1, min(limit, 500))
    if match_status and match_status not in _DETECTION_MATCH_STATUSES:
        raise ValueError("Estado de conciliación inválido")

    conditions = [
        "action IN ('DETECTED', 'DETECTION')",
        "image_path IS NOT NULL",
    ]
    params: list = []
    if match_status:
        conditions.append("match_status = %s")
        params.append(match_status)
    if date:
        conditions.append(
            "(logged_at AT TIME ZONE 'America/Santiago')::date = %s::date"
        )
        params.append(date)
    params.append(bounded_limit)

    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, plate, COALESCE(normalized_plate, plate) normalized_plate,
                       logged_at, confidence, image_path, direction, match_status,
                       linked_session_id, COALESCE(source, status) source
                FROM detection_log
                WHERE {' AND '.join(conditions)}
                ORDER BY logged_at DESC
                LIMIT %s
            """, params)
            rows = cur.fetchall()

    return [
        {
            "detection_id": int(row["id"]),
            "detected_plate": row["plate"],
            "normalized_plate": row["normalized_plate"],
            "detected_at": row["logged_at"].astimezone(_CL).isoformat(),
            "confidence": float(row["confidence"]),
            "image_url": _image_url(row["image_path"]),
            "direction": row["direction"] or "UNKNOWN",
            "match_status": row["match_status"],
            "stay_id": (
                int(row["linked_session_id"])
                if row["linked_session_id"] is not None else None
            ),
            "source": row["source"],
        }
        for row in rows
    ]


def _stay_from_row(row: dict) -> dict:
    entry_time = row["entry_time"]
    exit_time = row["exit_time"]
    technical_close = row["session_status"] == "AUTO_CLOSED"
    if technical_close:
        status = "NEEDS_REVIEW"
        duration = None
    elif entry_time and exit_time:
        status = "COMPLETED"
        duration = max(
            0, int((exit_time - entry_time).total_seconds() // 60)
        )
    elif entry_time:
        status = "ENTRY_ONLY"
        duration = None
    elif exit_time:
        status = "EXIT_ONLY"
        duration = None
    else:
        status = "NEEDS_REVIEW"
        duration = None
    return {
        "stay_id": int(row["id"]),
        "resolved_plate": row["plate"],
        "entry_detection_id": (
            int(row["entry_detection_id"])
            if row["entry_detection_id"] is not None else None
        ),
        "exit_detection_id": (
            int(row["exit_detection_id"])
            if row["exit_detection_id"] is not None else None
        ),
        "entry_time": entry_time.astimezone(_CL).isoformat() if entry_time else None,
        "exit_time": exit_time.astimezone(_CL).isoformat() if exit_time else None,
        "duration_minutes": duration,
        "match_type": row["match_type"] or "UNRESOLVED",
        "match_confidence": (
            float(row["match_confidence"])
            if row["match_confidence"] is not None else None
        ),
        "status": status,
        "entry_image_url": _image_url(row["entry_image_path"]),
        "exit_image_url": _image_url(row["exit_image_path"]),
        "fee": float(row["fee"] or 0),
    }


def get_parking_stays(
    limit: int = 100,
    status: str | None = None,
    date: str | None = None,
    plate: str | None = None,
) -> list:
    allowed_statuses = {
        "ENTRY_ONLY", "EXIT_ONLY", "COMPLETED", "NEEDS_REVIEW"
    }
    if status and status not in allowed_statuses:
        raise ValueError("Estado de estadía inválido")
    bounded_limit = max(1, min(limit, 500))
    conditions = ["status != 'VOID'"]
    params: list = []
    if status == "COMPLETED":
        conditions.extend([
            "entry_time IS NOT NULL",
            "exit_time IS NOT NULL",
            "status != 'AUTO_CLOSED'",
        ])
    elif status == "ENTRY_ONLY":
        conditions.extend(["entry_time IS NOT NULL", "exit_time IS NULL"])
    elif status == "EXIT_ONLY":
        conditions.extend(["entry_time IS NULL", "exit_time IS NOT NULL"])
    elif status == "NEEDS_REVIEW":
        conditions.append(
            "(entry_time IS NULL OR exit_time IS NULL OR status = 'AUTO_CLOSED')"
        )
    if date:
        _add_operational_day_overlap(conditions, params, date)
    if plate:
        normalized = re.sub(r"[^A-Z0-9]", "", plate.upper())
        conditions.append("plate = %s")
        params.append(normalized)
    params.append(bounded_limit)

    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, plate, entry_time, exit_time, status session_status,
                       entry_image_path,
                       exit_image_path, fee, entry_detection_id,
                       exit_detection_id, match_type, match_confidence
                FROM parking_sessions
                WHERE {' AND '.join(conditions)}
                ORDER BY COALESCE(exit_time, entry_time) DESC
                LIMIT %s
            """, params)
            rows = cur.fetchall()
    return [_stay_from_row(row) for row in rows]


def get_parking_stay(stay_id: int) -> dict:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, plate, entry_time, exit_time, status session_status,
                       entry_image_path,
                       exit_image_path, fee, entry_detection_id,
                       exit_detection_id, match_type, match_confidence
                FROM parking_sessions
                WHERE id = %s AND status != 'VOID'
            """, (stay_id,))
            row = cur.fetchone()
    if not row:
        raise LookupError("Estadía no encontrada")
    return _stay_from_row(row)


def reconcile_detection_events(
    entry_detection_id: int,
    exit_detection_id: int,
    resolved_plate: str,
    match_type: str = "MANUAL",
) -> dict:
    if entry_detection_id == exit_detection_id:
        raise ValueError("Entrada y salida deben ser detecciones distintas")
    normalized = normalize_plate(resolved_plate)
    if len(normalized) != 6:
        raise ValueError("La patente resuelta debe tener exactamente 6 caracteres")

    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, plate, COALESCE(normalized_plate, plate) normalized_plate,
                       logged_at, confidence, image_path, match_status
                FROM detection_log
                WHERE id IN (%s, %s)
                ORDER BY id
                FOR UPDATE
            """, (entry_detection_id, exit_detection_id))
            found = {int(row["id"]): row for row in cur.fetchall()}
            if set(found) != {entry_detection_id, exit_detection_id}:
                raise LookupError("Una o más detecciones no existen")
            entry = found[entry_detection_id]
            exit_event = found[exit_detection_id]
            if entry["match_status"] != "UNMATCHED" or exit_event["match_status"] != "UNMATCHED":
                raise ValueError("Una o más detecciones ya fueron conciliadas")
            if len(entry["normalized_plate"]) != 6 or len(exit_event["normalized_plate"]) != 6:
                raise ValueError("Las detecciones deben tener patentes normalizadas de 6 caracteres")
            if exit_event["logged_at"] <= entry["logged_at"]:
                raise ValueError("La salida debe ser posterior a la entrada")
            if is_zero_minute_duration(
                entry["logged_at"], exit_event["logged_at"]
            ):
                cur.execute("""
                    INSERT INTO parking_sessions
                        (plate, entry_time, exit_time, is_event, event_fee, fee,
                         entry_image_path, exit_image_path, source, status,
                         entry_detection_id, exit_detection_id, match_type,
                         match_confidence)
                    VALUES (%s, %s, %s, false, NULL, 0, %s, %s,
                            'manual', 'VOID', %s, %s, %s, 0)
                    RETURNING id
                """, (
                    normalized, entry["logged_at"], exit_event["logged_at"],
                    entry["image_path"], exit_event["image_path"],
                    entry_detection_id, exit_detection_id, match_type,
                ))
                stay_id = int(cur.fetchone()["id"])
                cur.execute("""
                    UPDATE detection_log SET match_status = 'DISMISSED',
                        linked_session_id = %s WHERE id IN (%s, %s)
                """, (stay_id, entry_detection_id, exit_detection_id))
                return {
                    "stay_id": stay_id,
                    "status": "DUPLICATE",
                    "duration_minutes": 0,
                }

            cur.execute(
                "INSERT INTO vehicles (plate) VALUES (%s) ON CONFLICT (plate) DO NOTHING",
                (normalized,),
            )
            confidence = min(
                float(entry["confidence"]), float(exit_event["confidence"])
            )
            cur.execute("""
                INSERT INTO parking_sessions
                    (plate, entry_time, exit_time, is_event, event_fee, fee,
                     entry_image_path, exit_image_path, source, status,
                     entry_detection_id, exit_detection_id, match_type,
                     match_confidence)
                VALUES (%s, %s, %s, false, NULL, 0, %s, %s,
                        'manual', 'REAL', %s, %s, %s, %s)
                RETURNING id
            """, (
                normalized, entry["logged_at"], exit_event["logged_at"],
                entry["image_path"], exit_event["image_path"],
                entry_detection_id, exit_detection_id, match_type, confidence,
            ))
            stay_id = int(cur.fetchone()["id"])
            cur.execute("""
                UPDATE detection_log
                SET match_status = CASE
                        WHEN id = %s THEN 'MATCHED_ENTRY'
                        ELSE 'MATCHED_EXIT'
                    END,
                    linked_session_id = %s
                WHERE id IN (%s, %s)
            """, (
                entry_detection_id, stay_id,
                entry_detection_id, exit_detection_id,
            ))
            cur.execute("""
                INSERT INTO audit_log (plate, event_type, details)
                VALUES (%s, 'STAY_RECONCILED', %s::jsonb)
            """, (
                normalized,
                json.dumps({
                    "stay_id": stay_id,
                    "entry_detection_id": entry_detection_id,
                    "exit_detection_id": exit_detection_id,
                    "match_type": match_type,
                }),
            ))

    return get_parking_stay(stay_id)


def dismiss_detection_event(detection_id: int) -> dict:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE detection_log
                SET match_status = 'DISMISSED'
                WHERE id = %s AND match_status = 'UNMATCHED'
                RETURNING id
            """, (detection_id,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "SELECT match_status FROM detection_log WHERE id = %s",
                    (detection_id,),
                )
                existing = cur.fetchone()
                if not existing:
                    raise LookupError("Detección no encontrada")
                raise ValueError("La detección ya fue conciliada o descartada")
    return {"detection_id": detection_id, "match_status": "DISMISSED"}


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
            "image_path": r["image_path"],
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
