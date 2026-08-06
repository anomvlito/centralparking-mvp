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
import threading
import requests
from zoneinfo import ZoneInfo

_CL = ZoneInfo("America/Santiago")
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

FTP_WATCH_DIR  = os.environ.get("FTP_WATCH_DIR",   "/ftp/entrada")
FTP_ARCHIVE_DIR = os.environ.get("FTP_ARCHIVE_DIR", "/ftp/historico")
FTP_REVIEW_DIR  = os.environ.get("FTP_REVIEW_DIR",  "/ftp/revisar")
API_BASE        = os.environ.get("API_BASE",         "http://localhost:8000")

# on_created de watchdog solo ve eventos en vivo: un archivo que llega
# mientras el proceso no corre (crash-loop, deploy, reboot) se pierde para
# siempre si nadie lo barre al reiniciar. FTP_SWEEP_MAX_AGE_SECONDS acota
# ese barrido a lo reciente para no reprocesar meses de backlog viejo cada
# vez que el servicio reinicia.
FTP_SWEEP_MAX_AGE = int(os.environ.get("FTP_SWEEP_MAX_AGE_SECONDS", "7200"))

# El backend corre como usuario sin permiso de escritura sobre
# FTP_WATCH_DIR (es del usuario FTP), así que no puede borrar el .mp4
# fuente una vez procesado. El watchdog sí puede (corre como root):
# espera a que aparezca el CSV de resultados y recién ahí lo borra.
VIDEO_CLEANUP_POLL_SECONDS   = int(os.environ.get("VIDEO_CLEANUP_POLL_SECONDS", "5"))
VIDEO_CLEANUP_TIMEOUT_SECONDS = int(os.environ.get("VIDEO_CLEANUP_TIMEOUT_SECONDS", "1800"))

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


def _archive(src: str, plate: str | None, suffix: str = "") -> str | None:
    """
    Mueve la imagen a subcarpeta por fecha.
    Retorna el path relativo 'historico/{date}/{filename}' para vincularlo en la BD.
    """
    if not os.path.exists(src):
        return None

    now = datetime.datetime.now(_CL)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    ext = os.path.splitext(src)[1].lower() or ".jpg"

    if plate:
        folder = os.path.join(FTP_ARCHIVE_DIR, date_str)
        filename = f"{time_str}_{plate}_{date_str}{suffix}{ext}"
        rel_path = f"historico/{date_str}/{filename}"
    else:
        folder = os.path.join(FTP_REVIEW_DIR, date_str)
        label = suffix.lstrip("_").upper() if suffix else "NO_DETECTADA"
        filename = f"{time_str}_{label}_{date_str}{ext}"
        rel_path = None  # no vinculamos imágenes sin patente

    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, filename)

    counter = 1
    base, extension = os.path.splitext(dest)
    while os.path.exists(dest):
        dest = f"{base}_{counter}{extension}"
        counter += 1

    try:
        shutil.move(src, dest)
        log.info(f"ARC   {os.path.relpath(dest, '/ftp')}")
        return rel_path
    except Exception as e:
        log.error(f"Error archivando {os.path.basename(src)}: {e}")
        return None


def _discard(path: str):
    """Elimina el archivo temporal ya subido: el backend es quien decide si
    guarda una imagen (y dónde), así que acá no queda nada más por archivar."""
    try:
        os.remove(path)
    except OSError:
        pass


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
            plate  = data.get("plate")
            action = data.get("action")

            if action == "AUTO_CORRECTED_OCR":
                old_plate = data.get("old_plate")
                log.info(f"CORR  {old_plate} -> {plate} conf={data.get('confidence', 0):.2f}")
                _archive(path, plate=plate, suffix="_corr")

            elif action == "STAGED":
                # El backend ya decide y guarda (o descarta) la imagen dentro de
                # staging_submit(): solo persiste la de mejor calidad vigente en
                # la ventana y borra la anterior al ser superada. Archivar acá
                # también creaba un segundo archivo por cada frame que nunca se
                # limpiaba, dejando "fotos duplicadas" de la misma patente en
                # /ftp/historico.
                staging = data.get("staging", {})
                log.info(f"STG   {plate} {staging.get('action')} score={staging.get('combined_score', 0):.3f}")
                _discard(path)

            elif action is None and data.get("error") == "no_vehicle":
                # Filtro de vehículo activo (ver ADR-004) sin shadow_mode:
                # el backend ya decidió que no hay vehículo y ni siquiera
                # corrió ALPR — no tiene sentido archivar en revisión, es
                # justamente el espacio que el filtro busca ahorrar.
                log.info("SKIP  sin vehículo (filtro pre-ALPR)")
                _discard(path)

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
                return

            log.info(f"VID   queued: {data.get('status')}")
            result_csv = data.get("result_csv")
            if result_csv:
                threading.Thread(
                    target=self._cleanup_video_after_processing,
                    args=(path, result_csv),
                    daemon=True,
                ).start()
        except Exception as e:
            log.error(f"Error enviando video: {e}")

    def _cleanup_video_after_processing(self, video_path: str, result_csv_path: str):
        """Espera a que el backend termine de procesar el video (aparece
        result_csv_path) y recién ahí borra el .mp4 fuente. Si el backend
        nunca llega a escribir el CSV (video corrupto, AI offline), se deja
        el archivo donde está tras el timeout en vez de perderlo."""
        waited = 0
        while waited < VIDEO_CLEANUP_TIMEOUT_SECONDS:
            if os.path.exists(result_csv_path):
                _discard(video_path)
                log.info(f"VID   limpiado: {os.path.basename(video_path)}")
                return
            if not os.path.exists(video_path):
                return
            time.sleep(VIDEO_CLEANUP_POLL_SECONDS)
            waited += VIDEO_CLEANUP_POLL_SECONDS
        log.warning(f"VID   timeout esperando resultado de {os.path.basename(video_path)}, no se borra")


# ─────────────────────────── Reconciliacion al arrancar ─────────────────────

def _sweep_existing(handler: "ReoLinkFTPHandler"):
    """Procesa imagenes que ya estaban en FTP_WATCH_DIR al arrancar, dentro
    de la ventana FTP_SWEEP_MAX_AGE. Cubre lo que se haya perdido durante
    cortes recientes del watchdog sin tocar backlog antiguo.

    Solo imagenes: /api/ftp/video encola _process_video_task como
    BackgroundTask sincrono sin ningun limite de concurrencia. Mandar
    muchos videos de golpe (ej. el backlog acumulado tras un corte) ya
    causo un OOM-kill del backend (2026-07-20 18:52 UTC, memoria a 5.7G).
    _handle_video ya limpia el .mp4 fuente cuando corresponde (ver
    _cleanup_video_after_processing), pero eso no evita el pico de
    memoria si se disparan muchos en paralelo — por eso los videos igual
    se excluyen del barrido hasta que haya un límite de concurrencia.
    """
    now = time.time()
    pending = []
    for root, _dirs, files in os.walk(FTP_WATCH_DIR):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in IMAGE_EXTS:
                continue
            path = os.path.join(root, fname)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if now - mtime <= FTP_SWEEP_MAX_AGE:
                pending.append((mtime, path, ext))

    if not pending:
        return

    pending.sort()
    log.info(f"Barrido inicial: {len(pending)} archivo(s) de los ultimos {FTP_SWEEP_MAX_AGE}s pendientes")
    for _mtime, path, _ext in pending:
        if os.path.exists(path):
            handler._handle_image(path)


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
    _sweep_existing(handler)

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
