#!/usr/bin/env python3
"""
Vincula imágenes históricas de /ftp/historico/ con registros de detection_log.

Lógica:
  - Parsea cada imagen: {HH-MM-SS}_{PLATE}_{YYYY-MM-DD}[_suffix].jpg
  - Busca en detection_log la entrada más cercana con la misma patente y fecha
  - Ajusta por el delay de staging (~2 min entre captura e ingreso al log)
  - Actualiza image_path si la diferencia es menor al umbral (5 min)

Uso:
    python scripts/backfill_image_paths.py [--dry-run]
"""

import os
import re
import sys
import datetime
import psycopg2
import psycopg2.extras
from zoneinfo import ZoneInfo

_CL = ZoneInfo("America/Santiago")
DATABASE_URL = os.environ.get("DATABASE_URL",
    "postgresql://parking:parking_mvp_2026@127.0.0.1/centralparking")
FTP_ARCHIVE_DIR = os.environ.get("FTP_ARCHIVE_DIR", "/ftp/historico")

DRY_RUN = "--dry-run" in sys.argv
MAX_DELTA_MINUTES = 5   # tolerancia: staging (~2 min) + margen

_FILE_RE = re.compile(
    r"^(\d{2})-(\d{2})-(\d{2})_(.+?)_(\d{4}-\d{2}-\d{2})(?:_.*)?\.(?:jpg|jpeg|png)$",
    re.IGNORECASE,
)


def parse_filename(fname: str):
    """Retorna (datetime, plate, rel_path) o None si no matchea."""
    m = _FILE_RE.match(fname)
    if not m:
        return None
    hh, mm, ss, plate, date_str = m.groups()
    try:
        dt = datetime.datetime.strptime(
            f"{date_str} {hh}:{mm}:{ss}", "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=_CL)
    except ValueError:
        return None
    return dt, plate.upper(), date_str


def collect_images():
    """Devuelve lista de (image_dt, plate, rel_path) para todas las imágenes."""
    images = []
    for date_folder in sorted(os.listdir(FTP_ARCHIVE_DIR)):
        folder = os.path.join(FTP_ARCHIVE_DIR, date_folder)
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            parsed = parse_filename(fname)
            if not parsed:
                continue
            img_dt, plate, date_str = parsed
            rel = f"historico/{date_str}/{fname}"
            images.append((img_dt, plate, rel))
    return images


def main():
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Escaneando {FTP_ARCHIVE_DIR}...")
    images = collect_images()
    print(f"  {len(images)} imágenes encontradas")

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

    # Cargar registros sin image_path agrupados por (plate, date)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, plate, logged_at, action
            FROM detection_log
            WHERE image_path IS NULL
            ORDER BY logged_at
        """)
        log_rows = cur.fetchall()

    print(f"  {len(log_rows)} registros sin foto en detection_log")

    # Índice: plate -> lista de (logged_at, id)
    from collections import defaultdict
    log_index = defaultdict(list)
    for row in log_rows:
        log_index[row["plate"]].append((row["logged_at"], row["id"], row["action"]))

    updates = []   # [(id, rel_path)]
    threshold = datetime.timedelta(minutes=MAX_DELTA_MINUTES)

    for img_dt, plate, rel in images:
        candidates = log_index.get(plate, [])
        if not candidates:
            continue

        best_id = None
        best_delta = None

        for logged_at, row_id, action in candidates:
            # Para ENTRY vía staging: logged_at ≈ img_dt + 2 min
            # Para EXIT: logged_at ≈ img_dt
            delta = abs(logged_at - img_dt)
            if delta <= threshold:
                if best_delta is None or delta < best_delta:
                    best_id = row_id
                    best_delta = delta

        if best_id is not None:
            updates.append((best_id, rel))
            # Remover del índice para no reusar
            log_index[plate] = [
                (t, i, a) for t, i, a in log_index[plate] if i != best_id
            ]

    print(f"\n  {len(updates)} matches encontrados")

    if DRY_RUN:
        for row_id, rel in updates[:10]:
            print(f"    id={row_id}  →  {rel}")
        if len(updates) > 10:
            print(f"    ... y {len(updates)-10} más")
        print("\n[DRY RUN] Sin cambios aplicados.")
        conn.close()
        return

    if not updates:
        print("Nada que actualizar.")
        conn.close()
        return

    with conn:
        with conn.cursor() as cur:
            for row_id, rel in updates:
                cur.execute(
                    "UPDATE detection_log SET image_path = %s WHERE id = %s",
                    (rel, row_id)
                )

    print(f"✓ {len(updates)} registros actualizados.")

    unmatched = sum(len(v) for v in log_index.values())
    print(f"  Sin match: {unmatched} registros (foto no encontrada o fuera de ventana)")
    conn.close()


if __name__ == "__main__":
    main()
