"""
migrate_timestamps.py
Convierte los timestamps de la tabla history de UTC a America/Santiago.
Ejecutar una sola vez: python migrate_timestamps.py
"""

import sqlite3
import datetime
from zoneinfo import ZoneInfo

DB_PATH = "parking.db"
UTC = ZoneInfo("UTC")
CL  = ZoneInfo("America/Santiago")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, timestamp FROM history").fetchall()

    updated = 0
    skipped = 0
    for row_id, ts_str in rows:
        try:
            ts_utc = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            ts_cl  = ts_utc.astimezone(CL)
            new_ts = ts_cl.strftime("%Y-%m-%d %H:%M:%S")
            if new_ts != ts_str:
                conn.execute("UPDATE history SET timestamp = ? WHERE id = ?", (new_ts, row_id))
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  fila {row_id} error: {e}")

    conn.commit()
    conn.close()
    print(f"Migración completa: {updated} actualizadas, {skipped} sin cambios")


if __name__ == "__main__":
    migrate()
