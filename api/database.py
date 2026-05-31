"""
database.py — Central Parking MVP
Capa de persistencia PostgreSQL.
Misma interfaz pública que la versión SQLite — detect.py, ftp_handler.py y
video_processor.py no requieren cambios.
"""

import os
import datetime
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
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
                   is_event: bool = False, event_fee=None):
    entry_dt = datetime.datetime.fromtimestamp(entry_time_ms / 1000, tz=_CL)
    with _db() as conn:
        with conn.cursor() as cur:
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
                cur.execute("""
                    UPDATE parking_sessions
                    SET entry_time = %s, is_event = %s, event_fee = %s, updated_at = now()
                    WHERE id = %s
                """, (entry_dt, is_event, event_fee, existing["id"]))
            else:
                cur.execute("""
                    INSERT INTO parking_sessions
                        (plate, entry_time, is_event, event_fee, source, status)
                    VALUES (%s, %s, %s, %s, 'camera_auto', 'REAL')
                """, (plate, entry_dt, is_event, event_fee))


def remove_vehicle(plate: str, fee: float = 0):
    """Cierra la sesión activa registrando la salida y la tarifa."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE parking_sessions
                SET exit_time = now(), fee = %s, updated_at = now()
                WHERE plate = %s AND exit_time IS NULL AND status != 'VOID'
            """, (fee or 0, plate))


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


# ─────────────────────── log / historial ────────────────────────────────────

def log_to_db(plate: str, action: str, status: str = "REAL",
              fee: float = 0, conf: float = 1.0, image_path: str = None):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO detection_log (plate, action, status, fee, confidence, image_path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (plate, action, status, fee, conf, image_path))


def get_history(limit: int = 200) -> list:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT logged_at AS timestamp, plate, action, status,
                       fee, confidence, image_path
                FROM detection_log
                ORDER BY logged_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
    result = []
    for r in rows:
        entry = {
            "timestamp":  r["timestamp"].astimezone(_CL).strftime("%Y-%m-%d %H:%M:%S"),
            "plate":      r["plate"],
            "action":     r["action"],
            "status":     r["status"],
            "fee":        float(r["fee"]),
            "confidence": float(r["confidence"]),
            "image_url":  f"/api/monitor/file/{r['image_path']}" if r["image_path"] else None,
        }
        result.append(entry)
    return result


def get_stats_today() -> dict:
    today = now_cl().replace(hour=0, minute=0, second=0, microsecond=0)
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE action = 'ENTRY')               AS entries,
                    COUNT(*) FILTER (WHERE action = 'EXIT')                AS exits,
                    COALESCE(SUM(fee) FILTER (WHERE action = 'EXIT'), 0)   AS revenue
                FROM detection_log
                WHERE logged_at >= %s AND action IN ('ENTRY', 'EXIT')
            """, (today,))
            stats = cur.fetchone()
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
