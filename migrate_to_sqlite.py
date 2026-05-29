"""
migrate_to_sqlite.py — Importa parking_db.json y history.csv a SQLite.
Ejecutar una sola vez: python migrate_to_sqlite.py
"""
import json, csv, os, sys
sys.path.insert(0, os.path.dirname(__file__))

from api.database import init_db, upsert_vehicle, get_conn

init_db()

# ── Migrar vehicles desde JSON ────────────────────────────────────────────
migrated_v = 0
if os.path.exists("parking_db.json"):
    with open("parking_db.json") as f:
        db = json.load(f)
    for v in db.values():
        upsert_vehicle(
            plate=v["plate"],
            entry_time_ms=v["entryTime"],
            is_event=bool(v.get("isEvent")),
            event_fee=v.get("eventFee"),
        )
        migrated_v += 1
    print(f"✅ Vehículos migrados: {migrated_v}")
else:
    print("⚠️  parking_db.json no encontrado — omitido")

# ── Migrar historial desde CSV ────────────────────────────────────────────
migrated_h = 0
if os.path.exists("history.csv"):
    with open("history.csv") as f:
        reader = csv.reader(f)
        next(reader, None)  # saltar header
        rows = []
        for row in reader:
            if len(row) < 4:
                continue
            ts, plate, action = row[0], row[1], row[2]
            status = row[3] if len(row) > 3 else "REAL"
            fee    = float(row[4]) if len(row) > 4 and row[4] else 0
            conf   = float(row[5]) if len(row) > 5 and row[5] else 1.0
            rows.append((ts, plate, action, status, fee, round(conf, 2)))
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO history (timestamp, plate, action, status, fee, confidence) VALUES (?,?,?,?,?,?)",
            rows,
        )
    migrated_h = len(rows)
    print(f"✅ Registros de historial migrados: {migrated_h}")
else:
    print("⚠️  history.csv no encontrado — omitido")

print(f"\n✅ Migración completa → parking.db")
print(f"   Vehículos activos : {migrated_v}")
print(f"   Historial         : {migrated_h} registros")
