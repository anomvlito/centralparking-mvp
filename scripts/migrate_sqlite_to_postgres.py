#!/usr/bin/env python3
"""
Migra datos de parking.db (SQLite) a PostgreSQL.
Idempotente: se puede correr más de una vez sin duplicar datos.

Uso:
    python scripts/migrate_sqlite_to_postgres.py

Variables de entorno requeridas:
    DATABASE_URL   — postgresql://parking:...@127.0.0.1/centralparking
    SQLITE_PATH    — ruta a parking.db (default: parking.db)
"""

import os
import sys
import datetime
import sqlite3
import psycopg2
import psycopg2.extras
from zoneinfo import ZoneInfo

_CL = ZoneInfo("America/Santiago")

SQLITE_PATH  = os.environ.get("SQLITE_PATH", "parking.db")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL no está configurada.")
if not os.path.exists(SQLITE_PATH):
    sys.exit(f"ERROR: No se encontró {SQLITE_PATH}")


def _pg():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def migrate_vehicles(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute("SELECT plate, entry_time, is_event, event_fee FROM vehicles").fetchall()
    print(f"  Vehículos activos en SQLite: {len(rows)}")
    inserted = 0
    with pg_conn.cursor() as cur:
        for r in rows:
            entry_dt = datetime.datetime.fromtimestamp(r["entry_time"] / 1000, tz=_CL)
            # Registrar en catálogo de vehículos
            cur.execute(
                "INSERT INTO vehicles (plate) VALUES (%s) ON CONFLICT (plate) DO NOTHING",
                (r["plate"],)
            )
            # Insertar sesión abierta solo si no existe ya una
            cur.execute("""
                SELECT 1 FROM parking_sessions
                WHERE plate = %s AND exit_time IS NULL AND status != 'VOID'
            """, (r["plate"],))
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO parking_sessions
                    (plate, entry_time, is_event, event_fee, source, status)
                VALUES (%s, %s, %s, %s, 'camera_auto', 'REAL')
            """, (r["plate"], entry_dt, bool(r["is_event"]), r["event_fee"]))
            inserted += 1
    print(f"  → Sesiones abiertas insertadas: {inserted} (omitidas: {len(rows) - inserted})")


def migrate_history(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute(
        "SELECT timestamp, plate, action, status, fee, confidence FROM history ORDER BY id"
    ).fetchall()
    print(f"  Registros de history en SQLite: {len(rows)}")
    inserted = 0
    with pg_conn.cursor() as cur:
        for r in rows:
            try:
                logged_at = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
                logged_at = logged_at.replace(tzinfo=_CL)
            except ValueError:
                logged_at = datetime.datetime.now(_CL)

            # Deduplicar por (logged_at, plate, action)
            cur.execute("""
                SELECT 1 FROM detection_log
                WHERE logged_at = %s AND plate = %s AND action = %s
                LIMIT 1
            """, (logged_at, r["plate"], r["action"]))
            if cur.fetchone():
                continue

            cur.execute("""
                INSERT INTO detection_log (logged_at, plate, action, status, fee, confidence)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (logged_at, r["plate"], r["action"], r["status"], r["fee"], r["confidence"]))
            inserted += 1
    print(f"  → Eventos insertados: {inserted} (omitidos/duplicados: {len(rows) - inserted})")


def main():
    print(f"Conectando a SQLite: {SQLITE_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    print(f"Conectando a PostgreSQL...")
    pg_conn = _pg()

    try:
        print("\n── Migrando vehículos activos ──")
        migrate_vehicles(sqlite_conn, pg_conn)

        print("\n── Migrando historial ──")
        migrate_history(sqlite_conn, pg_conn)

        pg_conn.commit()
        print("\n✓ Migración completada.")
    except Exception as e:
        pg_conn.rollback()
        print(f"\n✗ Error durante la migración: {e}")
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
