#!/usr/bin/env python3
"""
audit_ftp.py — Auditoría de consistencia entre /ftp/historico y detection_log

Checks:
  1. Filesystem → BD: imágenes sin registro en DB (orphans)
  2. BD → Filesystem: detection_log.image_path apunta a archivo inexistente (broken links)
  3. Duplicados: misma patente, mismo día, capturada dentro de la ventana de tiempo
     → mueve el/los duplicado(s) a /ftp/duplicados/{date}/

Clasificación de multi-capturas:
  - < DUP_WINDOW_MIN   min  → duplicado (mismo evento, mover)
  - DUP_WINDOW_MIN..30 min  → sospechoso (flagear en reporte)
  - > 30 min                → re-entrada legítima (mantener)

Modos:
  --dry-run   Solo reporta, no mueve ni modifica nada (default)
  --fix       Mueve duplicados y repara image_path en DB
  --window N  Ventana de duplicados en minutos (default 5)

Uso:
  python scripts/audit_ftp.py --dry-run
  python scripts/audit_ftp.py --fix --window 3
"""

import os
import re
import sys
import shutil
import datetime
import psycopg2
import psycopg2.extras
from collections import defaultdict
from zoneinfo import ZoneInfo

_CL = ZoneInfo("America/Santiago")

DATABASE_URL   = os.environ.get("DATABASE_URL", "postgresql://parking:parking_mvp_2026@127.0.0.1/centralparking")
FTP_ARCHIVE    = os.environ.get("FTP_ARCHIVE_DIR", "/ftp/historico")
FTP_DUPLICADOS = os.environ.get("FTP_DUP_DIR",     "/ftp/duplicados")

DRY_RUN        = "--dry-run" in sys.argv or "--fix" not in sys.argv
FIX            = "--fix" in sys.argv

_window_arg    = next((sys.argv[sys.argv.index("--window") + 1]
                       for i, a in enumerate(sys.argv) if a == "--window"), "5")
DUP_WINDOW_MIN = int(_window_arg)
SUSPICIOUS_MIN = 30   # entre DUP_WINDOW_MIN y este valor → sospechoso

FILE_RE = re.compile(
    r"^(\d{2})-(\d{2})-(\d{2})_(.+?)_(\d{4}-\d{2}-\d{2})(_.+)?\.(?:jpg|jpeg|png)$",
    re.IGNORECASE,
)


def log(msg):    print(msg)
def info(msg):   print(f"  {msg}")
def warn(msg):   print(f"  ⚠ {msg}")
def ok(msg):     print(f"  ✓ {msg}")
def action(msg): print(f"  {'[DRY] ' if DRY_RUN else ''}→ {msg}")


# ─────────────────────── Filesystem scan ────────────────────────────────────

def scan_filesystem():
    """
    Devuelve dict: rel_path → {dt, plate, date_str, fname, folder_abs}
    rel_path = "historico/YYYY-MM-DD/fname"
    """
    images = {}
    for date_folder in sorted(os.listdir(FTP_ARCHIVE)):
        folder = os.path.join(FTP_ARCHIVE, date_folder)
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            m = FILE_RE.match(fname)
            if not m:
                continue
            hh, mm, ss, plate, date_str, suffix = m.groups()
            try:
                dt = datetime.datetime(
                    *[int(x) for x in date_str.split("-")],
                    int(hh), int(mm), int(ss),
                    tzinfo=_CL,
                )
            except ValueError:
                continue
            rel = f"historico/{date_str}/{fname}"
            images[rel] = {
                "dt":         dt,
                "plate":      plate.upper(),
                "date_str":   date_str,
                "fname":      fname,
                "folder_abs": folder,
                "suffix":     (suffix or "").lstrip("_"),
                "is_dup":     bool(suffix and "dup" in suffix.lower()),
            }
    return images


# ─────────────────────── DB scan ────────────────────────────────────────────

def scan_db():
    """Devuelve lista de (id, plate, action, logged_at_cl, image_path)."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, plate, action,
                       logged_at AT TIME ZONE 'America/Santiago' AS logged_cl,
                       image_path
                FROM detection_log
                ORDER BY logged_at
            """)
            rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ─────────────────────── Consistency checks ─────────────────────────────────

def check_broken_links(db_rows, fs_images):
    """image_path en DB pero archivo no existe en disco."""
    broken = []
    for r in db_rows:
        if r["image_path"] and r["image_path"] not in fs_images:
            broken.append(r)
    return broken


def check_orphans(db_rows, fs_images):
    """Imagen en disco sin referencia en DB."""
    linked = {r["image_path"] for r in db_rows if r["image_path"]}
    orphans = [rel for rel in fs_images if rel not in linked]
    return orphans


# ─────────────────────── Duplicate detection ────────────────────────────────

def detect_duplicates(fs_images, db_rows):
    """
    Agrupa imágenes por (date, plate).
    Clasifica cada grupo como: ok / suspicious / duplicates.
    """
    # Construir índice de image_path → db_id (para saber cuál está vinculado)
    db_linked = {r["image_path"]: r["id"] for r in db_rows if r["image_path"]}

    # Agrupar
    groups = defaultdict(list)
    for rel, meta in fs_images.items():
        if meta["is_dup"]:
            continue   # ya marcado como dup en nombre
        groups[(meta["date_str"], meta["plate"])].append((meta["dt"], rel, meta))

    results = {"ok": [], "suspicious": [], "duplicates": [], "reentry": []}

    for (date_str, plate), captures in groups.items():
        if len(captures) == 1:
            results["ok"].append((date_str, plate, captures))
            continue

        # Ordenar por timestamp
        captures.sort(key=lambda x: x[0])

        # Calcular diferencias entre capturas consecutivas
        processed = set()
        dup_groups = []   # cada elemento = lista de rel_paths que son duplicados entre sí

        for i, (dt_i, rel_i, _) in enumerate(captures):
            if rel_i in processed:
                continue
            dup_cluster = [rel_i]
            for j, (dt_j, rel_j, _) in enumerate(captures):
                if j <= i or rel_j in processed:
                    continue
                delta_min = abs((dt_j - dt_i).total_seconds()) / 60
                if delta_min <= DUP_WINDOW_MIN:
                    dup_cluster.append(rel_j)
                    processed.add(rel_j)
            processed.add(rel_i)

            if len(dup_cluster) > 1:
                dup_groups.append(dup_cluster)
            elif i > 0:
                # Check against previous non-dup
                prev_dt = captures[i - 1][0]
                delta = abs((dt_i - prev_dt).total_seconds()) / 60
                if DUP_WINDOW_MIN < delta <= SUSPICIOUS_MIN:
                    pass  # handled below

        # Si encontramos clusters de duplicados
        if dup_groups:
            for cluster in dup_groups:
                # Preferir el que tiene vínculo en DB; si hay empate, el primero cronológicamente
                linked_in_cluster = [r for r in cluster if r in db_linked]
                keep = linked_in_cluster[0] if linked_in_cluster else cluster[0]
                to_move = [r for r in cluster if r != keep]
                results["duplicates"].append({
                    "date": date_str, "plate": plate,
                    "keep": keep, "move": to_move,
                    "linked": keep in db_linked,
                })
        else:
            # Sin clusters de dups — verificar si es re-entrada o sospechoso
            dts = [c[0] for c in captures]
            max_delta = max(
                abs((dts[j] - dts[i]).total_seconds()) / 60
                for i in range(len(dts)) for j in range(i + 1, len(dts))
            )
            if max_delta <= SUSPICIOUS_MIN:
                results["suspicious"].append((date_str, plate, captures))
            else:
                results["reentry"].append((date_str, plate, captures))

    return results


# ─────────────────────── Actions ────────────────────────────────────────────

def move_to_duplicados(rel_path, meta):
    src = os.path.join(meta["folder_abs"], meta["fname"])
    dest_dir = os.path.join(FTP_DUPLICADOS, meta["date_str"])
    dest = os.path.join(dest_dir, meta["fname"])
    if not DRY_RUN:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(src, dest)
    return f"duplicados/{meta['date_str']}/{meta['fname']}"


def fix_broken_links(broken_rows):
    if not broken_rows or DRY_RUN:
        return
    conn = psycopg2.connect(DATABASE_URL)
    with conn:
        with conn.cursor() as cur:
            for r in broken_rows:
                cur.execute(
                    "UPDATE detection_log SET image_path = NULL WHERE id = %s",
                    (r["id"],)
                )
    conn.close()


def update_image_path(old_rel, new_rel):
    if DRY_RUN:
        return
    conn = psycopg2.connect(DATABASE_URL)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE detection_log SET image_path = %s WHERE image_path = %s",
                (new_rel, old_rel)
            )
    conn.close()


# ─────────────────────── Main ───────────────────────────────────────────────

def main():
    mode = "DRY RUN" if DRY_RUN else "FIX"
    print(f"\n{'='*60}")
    print(f" audit_ftp.py  [{mode}]  ventana duplicados: {DUP_WINDOW_MIN} min")
    print(f"{'='*60}")

    log("\n[1/4] Escaneando filesystem...")
    fs_images = scan_filesystem()
    info(f"{len(fs_images)} imágenes en {FTP_ARCHIVE}")

    log("\n[2/4] Escaneando base de datos...")
    db_rows = scan_db()
    info(f"{len(db_rows)} registros en detection_log")
    info(f"{sum(1 for r in db_rows if r['image_path'])} con image_path")

    log("\n[3/4] Verificando consistencia...")

    broken = check_broken_links(db_rows, fs_images)
    if broken:
        warn(f"{len(broken)} links rotos (image_path en DB apunta a archivo inexistente):")
        for r in broken:
            info(f"    id={r['id']} {r['plate']} → {r['image_path']}")
        if FIX:
            fix_broken_links(broken)
            ok("Links rotos limpiados (image_path = NULL)")
    else:
        ok("Sin links rotos")

    orphans = check_orphans(db_rows, fs_images)
    if orphans:
        info(f"{len(orphans)} imágenes sin vínculo en DB (orphans)")
        for rel in orphans[:10]:
            info(f"    {rel}")
        if len(orphans) > 10:
            info(f"    ... y {len(orphans) - 10} más")
    else:
        ok("Todas las imágenes tienen vínculo en DB")

    log("\n[4/4] Detectando duplicados...")
    dup_results = detect_duplicates(fs_images, db_rows)

    ok_count  = len(dup_results["ok"])
    dup_count = len(dup_results["duplicates"])
    sus_count = len(dup_results["suspicious"])
    re_count  = len(dup_results["reentry"])

    info(f"Grupos únicos (date+plate):  {ok_count + dup_count + sus_count + re_count}")
    info(f"  Sin duplicados:            {ok_count}")
    info(f"  Duplicados (< {DUP_WINDOW_MIN} min):     {dup_count} grupos")
    info(f"  Sospechosos ({DUP_WINDOW_MIN}-{SUSPICIOUS_MIN} min):    {sus_count} grupos")
    info(f"  Re-entradas (> {SUSPICIOUS_MIN} min):   {re_count} grupos")

    moved_total = 0

    if dup_count > 0:
        print(f"\n  Duplicados a mover → {FTP_DUPLICADOS}/:")
        for d in dup_results["duplicates"]:
            keep_meta  = fs_images[d["keep"]]
            print(f"\n    {d['date']} {d['plate']} ({'en DB' if d['linked'] else 'sin DB link'})")
            print(f"      KEEP : {keep_meta['fname']}")
            for mv_rel in d["move"]:
                mv_meta = fs_images[mv_rel]
                new_rel = move_to_duplicados(mv_rel, mv_meta)
                moved_total += 1
                action(f"MOVE : {mv_meta['fname']}  →  duplicados/{mv_meta['date_str']}/")
                # Si el que movemos está en DB, actualizar path
                if mv_rel in {r["image_path"] for r in db_rows if r["image_path"]}:
                    update_image_path(mv_rel, new_rel)
                    action(f"DB   : image_path actualizado a {new_rel}")

    if sus_count > 0:
        print(f"\n  Sospechosos ({DUP_WINDOW_MIN}-{SUSPICIOUS_MIN} min entre capturas) — revisar manualmente:")
        for date_str, plate, captures in dup_results["suspicious"]:
            times = [c[0].strftime("%H:%M:%S") for c in sorted(captures)]
            print(f"    {date_str} {plate}: {times}")

    print(f"\n{'='*60}")
    print(f" RESUMEN")
    print(f"  Imágenes en disco:    {len(fs_images)}")
    print(f"  Links rotos en DB:    {len(broken)}")
    print(f"  Orphans (sin DB):     {len(orphans)}")
    print(f"  Duplicados movidos:   {moved_total}")
    print(f"  {'(simulado - usar --fix para aplicar)' if DRY_RUN else 'aplicado'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
