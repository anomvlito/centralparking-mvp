"""
database.py — Central Parking MVP
Capa de persistencia SQLite. Reemplaza parking_db.json y history.csv.
"""

import sqlite3
import datetime
import os
from zoneinfo import ZoneInfo

_CL = ZoneInfo("America/Santiago")


def now_cl() -> datetime.datetime:
    return datetime.datetime.now(_CL)

DB_PATH = os.environ.get("PARKING_DB_PATH", "parking.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vehicles (
                plate       TEXT PRIMARY KEY,
                entry_time  INTEGER NOT NULL,
                is_event    INTEGER NOT NULL DEFAULT 0,
                event_fee   REAL
            );

            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                plate       TEXT NOT NULL,
                action      TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'REAL',
                fee         REAL DEFAULT 0,
                confidence  REAL DEFAULT 1.0
            );

            CREATE INDEX IF NOT EXISTS idx_history_plate     ON history(plate);
            CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_history_action    ON history(action);
        """)


# ─────────────────────── vehicles ───────────────────────────────────────────

def load_db() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM vehicles").fetchall()
    return {
        r["plate"]: {
            "plate":     r["plate"],
            "entryTime": r["entry_time"],
            "isEvent":   bool(r["is_event"]),
            "eventFee":  r["event_fee"],
        }
        for r in rows
    }


def upsert_vehicle(plate: str, entry_time_ms: float, is_event: bool = False, event_fee=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO vehicles (plate, entry_time, is_event, event_fee)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(plate) DO UPDATE SET
                   entry_time = excluded.entry_time,
                   is_event   = excluded.is_event,
                   event_fee  = excluded.event_fee""",
            (plate, int(entry_time_ms), int(is_event), event_fee),
        )


def remove_vehicle(plate: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM vehicles WHERE plate = ?", (plate,))


def vehicle_exists(plate: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM vehicles WHERE plate = ?", (plate,)).fetchone()
    return row is not None


def count_vehicles() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]


# ─────────────────────── history ────────────────────────────────────────────

def log_to_db(plate: str, action: str, status: str = "REAL", fee: float = 0, conf: float = 1.0):
    ts = now_cl().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO history (timestamp, plate, action, status, fee, confidence) VALUES (?,?,?,?,?,?)",
            (ts, plate, action, status, fee, round(conf, 2)),
        )


def get_history(limit: int = 50) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, plate, action, status, fee, confidence FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [[r["timestamp"], r["plate"], r["action"], r["status"], r["fee"], r["confidence"]] for r in rows]


def get_stats_today() -> dict:
    today = now_cl().strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN action='EXIT'  THEN fee   ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN action='ENTRY' THEN 1     ELSE 0 END), 0) AS entries,
                COALESCE(SUM(CASE WHEN action='EXIT'  THEN 1     ELSE 0 END), 0) AS exits,
                COUNT(*) AS total_parked
            FROM history
            WHERE timestamp LIKE ?
        """, (f"{today}%",)).fetchone()
        parked = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    return {
        "today_income":  row["income"],
        "today_entries": row["entries"],
        "today_exits":   row["exits"],
        "parked_now":    parked,
    }


def clear_history():
    with get_conn() as conn:
        conn.execute("DELETE FROM history")
