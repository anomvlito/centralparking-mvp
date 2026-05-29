"""
reformat_filenames.py
Renombra archivos del formato antiguo  PLATE_HH-MM-SS_YYYY-MM-DD[_tag].ext
al formato nuevo                       HH-MM-SS_PLATE_YYYY-MM-DD[_tag].ext
Aplica a /ftp/historico y /ftp/revisar.
Ejecutar una sola vez.
"""

import os
import re

FTP_DIRS = ["/ftp/historico", "/ftp/revisar"]

# Formato antiguo: PLATE_HH-MM-SS_YYYY-MM-DD[_tag].ext
_RE_OLD = re.compile(r"^(.+?)_(\d{2}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(_.+)?(\.\w+)$")

renamed = skipped = 0

for base_dir in FTP_DIRS:
    for dirpath, _, filenames in os.walk(base_dir):
        for fname in sorted(filenames):
            m = _RE_OLD.match(fname)
            if not m:
                continue
            plate, time_str, date_str, tag, ext = m.groups()
            tag_part = tag or ""
            new_name = f"{time_str}_{plate}_{date_str}{tag_part}{ext}"
            if new_name == fname:
                skipped += 1
                continue
            src  = os.path.join(dirpath, fname)
            dest = os.path.join(dirpath, new_name)
            if os.path.exists(dest):
                print(f"  COLISION {new_name} — omitido")
                skipped += 1
                continue
            os.rename(src, dest)
            print(f"  {fname}  →  {new_name}")
            renamed += 1

print(f"\nListo: {renamed} renombrados, {skipped} omitidos")
