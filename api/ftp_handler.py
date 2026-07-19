"""
FTP Handler — Central Parking MVP
Endpoints para procesar archivos subidos por FTP desde la cámara Reolink.

Rutas:
  POST /api/ftp/image          — imagen JPEG desde watchdog → ALPR → auto-registro
  POST /api/ftp/video          — video MP4 desde watchdog → procesamiento batch
  GET  /api/ftp/events         — historial de detecciones vía FTP
  GET  /api/monitor/images     — imágenes detectadas del día (filesystem)
  GET  /api/monitor/review     — imágenes sin detección pendientes de revisión
  GET  /api/monitor/file/{...} — sirve archivo de imagen desde /ftp/
"""

import os
import re
import csv
import json
import numpy as np
import cv2
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.detect import alpr, HAS_ML, run_multi_strategy
from api.database import (
    now_cl,
    find_similar_active_session, correct_session_plate, log_audit_event,
)
from api.staging import calculate_quality_score, staging_submit
from api.video_processor import _process_video_task, VIDEO_RESULTS_DIR

router = APIRouter()

FTP_EVENTS_FILE  = "ftp_events.json"
FTP_ARCHIVE_DIR  = os.environ.get("FTP_ARCHIVE_DIR", "/ftp/historico")
FTP_REVIEW_DIR   = os.environ.get("FTP_REVIEW_DIR",  "/ftp/revisar")


# ─────────────────────────── Helpers ────────────────────────────────────────

def _load_ftp_events() -> list:
    if not os.path.exists(FTP_EVENTS_FILE):
        return []
    with open(FTP_EVENTS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # Log auxiliar (no es la fuente de verdad, esa es Postgres). Si
            # quedó truncado por un crash a mitad de escritura, no debe tirar
            # abajo el registro real de la detección: se reinicia el log.
            print(f"[ftp_events] {FTP_EVENTS_FILE} corrupto, reiniciando log")
            return []


def _append_ftp_event(plate: str, source: str, confidence: float, strategy: str, action: str = "ENTRY"):
    events = _load_ftp_events()
    events.append({
        "timestamp": now_cl().strftime("%Y-%m-%d %H:%M:%S"),
        "plate":      plate,
        "source":     source,
        "confidence": round(confidence, 3),
        "strategy":   strategy,
        "action":     action,
    })
    # Escritura atómica: evita que un crash a mitad de escritura vuelva a
    # truncar/corromper el archivo (fue la causa de la corrupción anterior).
    tmp_path = FTP_EVENTS_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(events[-500:], f, indent=2)
    os.replace(tmp_path, FTP_EVENTS_FILE)


def _quality_for(img: np.ndarray, plate: str, confidence: float) -> dict:
    if img is not None:
        return calculate_quality_score(img, plate, confidence)
    return {
        "quality_score":    confidence,
        "combined_score":   confidence,
        "sharpness":        0.5,
        "contrast_score":   0.5,
        "brightness_score": 0.5,
        "ocr_clarity":      confidence,
    }


def _handle_auto_detection(plate: str, source: str, confidence: float,
                            strategy: str, img: np.ndarray = None) -> dict:
    """
    Registra cada lectura de patente como un avistamiento — sin decidir
    automáticamente si es entrada o salida.

    2026-07-17: se desconectó DirectionTracker (geometría de posición/
    tamaño para clasificar APPROACHING/DEPARTING). El modelo de dirección
    no era confiable: generaba tanto salidas falsas (con la peor foto de
    la ráfaga, ya que necesita varias muestras consistentes antes de
    confirmar y para entonces el auto ya se había alejado) como
    duplicados. El archivo sigue en api/direction_tracker.py por si se
    retoma más adelante.

    Por ahora toda detección compite por la mejor foto de la misma forma
    (staging, ventana corta) y queda logueada para revisión — el frontend
    decidirá más adelante cómo mostrar, por patente, las fotos de sus
    avistamientos. La apertura/cierre real de parking_sessions sigue
    siendo manual (/api/entry, /api/exit).
    """
    # No hay match exacto, pero puede ser el mismo auto mal leído antes
    # (dígito perdido por luces, carácter confundido). Si hay una sesión
    # recién abierta con patente muy parecida, se corrige esa sesión en
    # vez de crear un ENTRY duplicado. Reutiliza correct_session_plate:
    # misma lógica que usa un admin al corregir manualmente (renombra
    # archivos, reasigna detection_log/staging_detections).
    similar = find_similar_active_session(plate)
    if similar:
        try:
            correct_session_plate(similar["id"], plate, "system_ocr_correction")
        except (ValueError, FileExistsError, LookupError) as e:
            log_audit_event(plate, "AUTO_CORRECTION_FAILED",
                             {"session_id": similar["id"], "old_plate": similar["plate"],
                              "attempted_plate": plate, "error": str(e)})
        else:
            log_audit_event(plate, "AUTO_CORRECTED_OCR",
                             {"session_id": similar["id"], "old_plate": similar["plate"],
                              "new_plate": plate, "distance": similar["distance"],
                              "confidence": confidence, "source": source})
        return {"plate": plate, "action": "AUTO_CORRECTED_OCR", "registered": False,
                "confidence": confidence,
                "old_plate": similar["plate"], "session_id": similar["id"],
                "image_path": None}

    # Calcular quality score y enviar a staging (decide ahí si guarda la imagen)
    quality = _quality_for(img, plate, confidence)
    staging_result = staging_submit(plate, confidence, quality, strategy, img)
    _append_ftp_event(plate, source, confidence, strategy, action="STAGED")
    return {"plate": plate, "action": "STAGED", "registered": False,
            "confidence": confidence, "strategy": strategy,
            "staging": staging_result,
            "image_path": staging_result.get("image_path")}


# ─────────────────────────── Background task video ──────────────────────────

def _process_ftp_video_and_register(video_path: str, result_csv_path: str):
    # auto_register=False: el registro lo hace acá _handle_auto_detection,
    # pasando el frame confirmado para que compita por calidad en staging
    # igual que las fotos (antes se descartaba y el video nunca aportaba imagen).
    _process_video_task(video_path, result_csv_path, auto_register=False)

    if not os.path.exists(result_csv_path):
        print(f"ftp_video: no CSV at {result_csv_path}")
        return

    with open(result_csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            plate = row.get("Plate", "").strip()
            if not plate:
                continue

            frame_path = (row.get("FramePath") or "").strip()
            img = None
            if frame_path and os.path.exists(frame_path):
                img = cv2.imread(frame_path)

            result = _handle_auto_detection(
                plate, "video",
                float(row.get("Confidence", 0)), "video_clahe", img=img,
            )
            print(f"ftp_video {result['action']}: {plate}")

            if frame_path and os.path.exists(frame_path):
                try:
                    os.remove(frame_path)
                except OSError:
                    pass


# ─────────────────────────── FTP Endpoints ──────────────────────────────────

@router.post("/api/ftp/image")
async def ftp_image(image: UploadFile = File(...)):
    if not HAS_ML:
        return {"plate": None, "registered": False, "error": "AI offline"}

    contents = await image.read()
    if not contents:
        return {"plate": None, "registered": False, "error": "image_decode_failed"}

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return {"plate": None, "registered": False, "error": "image_decode_failed"}

    result = run_multi_strategy(img)
    if not result:
        return {"plate": None, "registered": False, "error": "no_detection"}

    plate = result["plate"]

    # La imagen se guarda dentro de _handle_auto_detection, solo si la
    # detección efectivamente se usa (mejor candidata vigente en staging).
    detect_result = _handle_auto_detection(
        plate, "image", result["confidence"], result["strategy"], img=img,
    )
    image_path = detect_result.get("image_path")
    detect_result["image_url"] = f"/api/monitor/file/{image_path}" if image_path else None
    return detect_result


class VideoPathRequest(BaseModel):
    path: str


@router.post("/api/ftp/video")
async def ftp_video(req: VideoPathRequest, background_tasks: BackgroundTasks):
    if not HAS_ML:
        return {"error": "AI offline"}
    if not os.path.exists(req.path):
        return {"error": f"Archivo no encontrado: {req.path}"}

    safe_name = os.path.basename(req.path)
    result_csv_path = os.path.join(VIDEO_RESULTS_DIR, f"ftp_{safe_name}.csv")
    background_tasks.add_task(_process_ftp_video_and_register, req.path, result_csv_path)
    return {"status": "processing", "path": req.path, "result_csv": result_csv_path}


@router.get("/api/ftp/events")
async def ftp_events():
    return {"events": _load_ftp_events()}


# ─────────────────────────── Monitor Endpoints ──────────────────────────────

_NON_PLATE_LABELS = {"NO_DETECTADA", "VACIA", "ERROR"}

def _parse_archive_filename(fname: str) -> dict:
    """
    Formato: HH-MM-SS_PLATE_YYYY-MM-DD[_tag].ext
    La hora va primero para que los archivos queden ordenados cronológicamente.
    """
    base = os.path.splitext(fname)[0]
    result = {"filename": fname, "plate": None, "time": None, "date": None, "tag": None}
    m = re.match(r"^(\d{2}-\d{2}-\d{2})_(.+?)_(\d{4}-\d{2}-\d{2})(_.+)?$", base)
    if not m:
        return result
    time_str, middle, date_str, tag = m.groups()
    result["time"] = time_str.replace("-", ":")
    result["date"] = date_str
    result["tag"]  = tag.lstrip("_") if tag else None
    if middle in _NON_PLATE_LABELS:
        result["reason"] = middle
    else:
        result["plate"] = middle
    return result


@router.get("/api/monitor/images")
async def monitor_images(date: str = None, limit: int = 100):
    """Imágenes detectadas del día desde /ftp/historico/{date}/"""
    if not date:
        date = now_cl().strftime("%Y-%m-%d")

    folder = os.path.join(FTP_ARCHIVE_DIR, date)
    if not os.path.exists(folder):
        return {"date": date, "images": []}

    files = sorted(
        [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))],
        reverse=True,
    )[:limit]

    images = []
    for fname in files:
        meta = _parse_archive_filename(fname)
        meta["url"] = f"/api/monitor/file/historico/{date}/{fname}"
        images.append(meta)

    return {"date": date, "images": images}


@router.get("/api/monitor/review")
async def monitor_review(date: str = None):
    """Imágenes sin detección pendientes de revisión desde /ftp/revisar/{date}/"""
    if not date:
        date = now_cl().strftime("%Y-%m-%d")

    folder = os.path.join(FTP_REVIEW_DIR, date)
    if not os.path.exists(folder):
        return {"date": date, "images": []}

    files = sorted(
        [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))],
        reverse=True,
    )

    images = []
    for fname in files:
        meta = _parse_archive_filename(fname)
        meta["url"] = f"/api/monitor/file/revisar/{date}/{fname}"
        images.append(meta)

    return {"date": date, "images": images}


@router.get("/api/monitor/file/{folder}/{date}/{filename}")
async def serve_ftp_file(folder: str, date: str, filename: str):
    """Sirve una imagen desde /ftp/historico o /ftp/revisar."""
    base_dirs = {
        "historico": FTP_ARCHIVE_DIR,
        "revisar":   FTP_REVIEW_DIR,
    }
    if folder not in base_dirs:
        raise HTTPException(400, "Carpeta inválida")

    full_path = os.path.realpath(os.path.join(base_dirs[folder], date, filename))
    base_real = os.path.realpath(base_dirs[folder])

    if not full_path.startswith(base_real + os.sep):
        raise HTTPException(403, "Acceso denegado")
    if not os.path.isfile(full_path):
        raise HTTPException(404, "Imagen no encontrada")

    return FileResponse(full_path, media_type="image/jpeg")
