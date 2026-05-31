"""
watchdog_ftp.py — Central Parking MVP
Monitorea la carpeta FTP de la cámara Reolink y envía archivos al backend.

Variables de entorno:
  FTP_WATCH_DIR    Carpeta a monitorear        (default: /ftp/entrada)
  FTP_ARCHIVE_DIR  Carpeta de imágenes válidas (default: /ftp/historico)
  FTP_REVIEW_DIR   Carpeta de no detectadas    (default: /ftp/revisar)
  API_BASE         URL del backend             (default: http://localhost:8000)
"""

import os
import time
import shutil
import datetime
import logging
import requests
from zoneinfo import ZoneInfo

_CL = ZoneInfo("America/Santiago")
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

FTP_WATCH_DIR  = os.environ.get("FTP_WATCH_DIR",   "/ftp/entrada")
FTP_ARCHIVE_DIR = os.environ.get("FTP_ARCHIVE_DIR", "/ftp/historico")
FTP_REVIEW_DIR  = os.environ.get("FTP_REVIEW_DIR",  "/ftp/revisar")
API_BASE        = os.environ.get("API_BASE",         "http://localhost:8000")

FILE_SETTLE_SECONDS = 2
FILE_SETTLE_TIMEOUT = 15

IMAGE_EXTS = (".jpg", ".jpeg", ".png")
VIDEO_EXTS = (".mp4", ".avi", ".mov")

for d in [FTP_ARCHIVE_DIR, FTP_REVIEW_DIR]:
    os.makedirs(d, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────── Helpers ────────────────────────────────────────

def _wait_for_file_ready(path: str) -> bool:
    """Espera hasta que el archivo tenga contenido y deje de crecer."""
    time.sleep(FILE_SETTLE_SECONDS)
    prev_size = -1
    for _ in range(FILE_SETTLE_TIMEOUT):
        if not os.path.exists(path):
            return False
        size = os.path.getsize(path)
        if size > 0 and size == prev_size:
            return True
        prev_size = size
        time.sleep(1)
    return False


def _archive(src: str, plate: str | None, suffix: str = "") -> None:
    """
    Mueve la imagen a subcarpeta por fecha con nombre PLATE_HH-MM-SS_YYYY-MM-DD.jpg

    Detectada:      /ftp/historico/2026-05-26/ZHBW94_14-23-51_2026-05-26.jpg
    Duplicada:      /ftp/historico/2026-05-26/ZHBW94_14-23-56_2026-05-26_dup.jpg
    No detectada:   /ftp/revisar/2026-05-26/NO_DETECTADA_14-24-01_2026-05-26.jpg
    Vacía/corrupta: /ftp/revisar/2026-05-26/VACIA_14-24-06_2026-05-26.jpg
    """
    if not os.path.exists(src):
        return

    now = datetime.datetime.now(_CL)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    ext = os.path.splitext(src)[1].lower() or ".jpg"

    if plate:
        folder = os.path.join(FTP_ARCHIVE_DIR, date_str)
        filename = f"{time_str}_{plate}_{date_str}{suffix}{ext}"
    else:
        folder = os.path.join(FTP_REVIEW_DIR, date_str)
        label = suffix.lstrip("_").upper() if suffix else "NO_DETECTADA"
        filename = f"{time_str}_{label}_{date_str}{ext}"

    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, filename)

    # Evitar colisión si ya existe un archivo con ese nombre
    counter = 1
    base, extension = os.path.splitext(dest)
    while os.path.exists(dest):
        dest = f"{base}_{counter}{extension}"
        counter += 1

    try:
        shutil.move(src, dest)
        log.info(f"ARC   {os.path.relpath(dest, '/ftp')}")
    except Exception as e:
        log.error(f"Error archivando {os.path.basename(src)}: {e}")


# ─────────────────────────── Handler ────────────────────────────────────────

class ReoLinkFTPHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        ext = os.path.splitext(filepath)[1].lower()

        if not _wait_for_file_ready(filepath):
            log.warning(f"Archivo vacio o no existe tras espera: {os.path.basename(filepath)}")
            _archive(filepath, plate=None, suffix="_VACIA")
            return

        if ext in IMAGE_EXTS:
            self._handle_image(filepath)
        elif ext in VIDEO_EXTS:
            self._handle_video(filepath)

    def _handle_image(self, path: str):
        log.info(f"IMG: {os.path.basename(path)}")
        try:
            with open(path, "rb") as f:
                res = requests.post(
                    f"{API_BASE}/api/ftp/image",
                    files={"image": (os.path.basename(path), f, "image/jpeg")},
                    timeout=30,
                )
            data = res.json()

            if data.get("registered"):
                plate = data["plate"]
                log.info(
                    f"ENTRY {plate} "
                    f"conf={data.get('confidence', 0):.2f} "
                    f"strategy={data.get('strategy')}"
                )
                _archive(path, plate=plate)

            elif data.get("reason") == "duplicate_within_window":
                plate = data["plate"]
                log.info(f"DUP   {plate}")
                _archive(path, plate=plate, suffix="_dup")

            else:
                error = data.get("error", "desconocido")
                log.info(f"MISS  {error}")
                suffix = "_VACIA" if error == "image_decode_failed" else "_NO_DETECTADA"
                _archive(path, plate=None, suffix=suffix)

        except Exception as e:
            log.error(f"ERROR img: {e}")
            _archive(path, plate=None, suffix="_ERROR")

    def _handle_video(self, path: str):
        log.info(f"VID:  {os.path.basename(path)}")
        try:
            res = requests.post(
                f"{API_BASE}/api/ftp/video",
                json={"path": path},
                timeout=10,
            )
            data = res.json()
            if "error" in data:
                log.error(f"ERROR vid: {data['error']}")
            else:
                log.info(f"VID   queued: {data.get('status')}")
        except Exception as e:
            log.error(f"Error enviando video: {e}")


# ─────────────────────────── Main ───────────────────────────────────────────

def main():
    if not os.path.exists(FTP_WATCH_DIR):
        log.error(f"Carpeta FTP no existe: {FTP_WATCH_DIR}")
        log.error("Créala con: sudo mkdir -p /ftp/entrada")
        return

    handler = ReoLinkFTPHandler()
    observer = Observer()
    observer.schedule(handler, FTP_WATCH_DIR, recursive=True)
    observer.start()

    log.info(f"Monitoreando:  {FTP_WATCH_DIR}")
    log.info(f"Archivando en: {FTP_ARCHIVE_DIR}")
    log.info(f"Revision en:   {FTP_REVIEW_DIR}")
    log.info(f"Backend API:   {API_BASE}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Deteniendo watchdog...")
        observer.stop()
    observer.join()
    log.info("Watchdog detenido.")


if __name__ == "__main__":
    main()
