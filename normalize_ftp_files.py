"""
normalize_ftp_files.py
Normaliza archivos en /ftp/historico y /ftp/revisar:
  - Un único formato: PLATE_HH-MM-SS_YYYY-MM-DD[_tag].ext en subcarpeta YYYY-MM-DD/
  - Hora convertida de UTC a America/Santiago
Ejecutar una sola vez.
"""

import os
import re
import shutil
import datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
CL  = ZoneInfo("America/Santiago")

FTP_HISTORICO = "/ftp/historico"
FTP_REVISAR   = "/ftp/revisar"

# Formato A (viejo, en root): PLATE_YYYY-MM-DD_HH-MM-SS[_tag].ext
_RE_OLD = re.compile(r"^(.+?)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})(_\w+)?(\.\w+)$")

# Formato B (nuevo, en subcarpeta): PLATE_HH-MM-SS_YYYY-MM-DD[_tag].ext
_RE_NEW = re.compile(r"^(.+?)_(\d{2}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(_\w+)?(\.\w+)$")


def _utc_to_cl(date_str: str, time_str: str):
    """date_str='2026-05-26', time_str='19-48-36' → datetime en Santiago."""
    naive = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H-%M-%S")
    return naive.replace(tzinfo=UTC).astimezone(CL)


def _target_path(base_dir: str, plate: str, dt_cl: datetime.datetime, tag: str, ext: str) -> str:
    date_str = dt_cl.strftime("%Y-%m-%d")
    time_str = dt_cl.strftime("%H-%M-%S")
    tag_part = tag if tag else ""
    filename = f"{plate}_{time_str}_{date_str}{tag_part}{ext}"
    folder   = os.path.join(base_dir, date_str)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, filename)
    # Evitar colisión
    counter = 1
    base_dest, ext_dest = os.path.splitext(dest)
    while os.path.exists(dest):
        dest = f"{base_dest}_{counter}{ext_dest}"
        counter += 1
    return dest


def migrate_dir(base_dir: str):
    moved = renamed = skipped = 0

    # 1. Archivos en root (formato viejo)
    for fname in os.listdir(base_dir):
        src = os.path.join(base_dir, fname)
        if not os.path.isfile(src):
            continue
        m = _RE_OLD.match(fname)
        if not m:
            print(f"  SKIP (desconocido): {fname}")
            skipped += 1
            continue
        plate, date_str, time_str, tag, ext = m.groups()
        dt_cl = _utc_to_cl(date_str, time_str)
        dest  = _target_path(base_dir, plate, dt_cl, tag or "", ext)
        shutil.move(src, dest)
        print(f"  MOVED  {fname} → {os.path.relpath(dest, base_dir)}")
        moved += 1

    # 2. Archivos en subcarpetas fechadas (formato nuevo, hora UTC)
    for entry in os.scandir(base_dir):
        if not entry.is_dir():
            continue
        for fname in os.listdir(entry.path):
            src = os.path.join(entry.path, fname)
            if not os.path.isfile(src):
                continue
            m = _RE_NEW.match(fname)
            if not m:
                print(f"  SKIP (desconocido): {entry.name}/{fname}")
                skipped += 1
                continue
            plate, time_str, date_str, tag, ext = m.groups()
            dt_cl = _utc_to_cl(date_str, time_str)
            new_time = dt_cl.strftime("%H-%M-%S")
            new_date = dt_cl.strftime("%Y-%m-%d")
            tag_part = tag or ""
            new_name = f"{plate}_{new_time}_{new_date}{tag_part}{ext}"
            dest = os.path.join(entry.path, new_name)
            if dest == src:
                skipped += 1
                continue
            # Evitar colisión
            counter = 1
            base_dest, ext_dest = os.path.splitext(dest)
            while os.path.exists(dest) and dest != src:
                dest = f"{base_dest}_{counter}{ext_dest}"
                counter += 1
            os.rename(src, dest)
            print(f"  RENAME {fname} → {new_name}")
            renamed += 1

    print(f"  → {moved} movidos, {renamed} renombrados, {skipped} omitidos")
    return moved + renamed


if __name__ == "__main__":
    print(f"\n[historico] {FTP_HISTORICO}")
    migrate_dir(FTP_HISTORICO)
    print(f"\n[revisar] {FTP_REVISAR}")
    migrate_dir(FTP_REVISAR)
    print("\nListo.")
