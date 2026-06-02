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
import time
import numpy as np
import cv2
from collections import defaultdict
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.detect import alpr, HAS_ML, run_multi_strategy
from api.database import (
    now_cl, vehicle_exists, remove_vehicle,
    log_to_db as log_to_csv,
)
from api.staging import calculate_quality_score, staging_submit
from api.video_processor import _process_video_task, VIDEO_RESULTS_DIR

router = APIRouter()

FTP_EVENTS_FILE  = "ftp_events.json"
FTP_ARCHIVE_DIR  = os.environ.get("FTP_ARCHIVE_DIR", "/ftp/historico")
FTP_REVIEW_DIR   = os.environ.get("FTP_REVIEW_DIR",  "/ftp/revisar")


# ─────────────────────────── Direction tracker ──────────────────────────────

class DirectionTracker:
    """
    Estima la dirección de movimiento de un vehículo comparando el ancho del
    bounding box de la patente en capturas consecutivas de la misma ráfaga FTP.

    Lógica:
      - bbox creciendo  →  vehículo acercándose  →  APPROACHING (entrada)
      - bbox achicándose →  vehículo alejándose   →  DEPARTING  (salida)
      - cambio < umbral  →  sin información       →  UNKNOWN

    El tracker mantiene las últimas N lecturas por patente dentro de una ventana
    de tiempo. Lecturas más antiguas que la ventana se descartan automáticamente.
    """

    # Ventana de tiempo para agrupar capturas de la misma ráfaga
    WINDOW_SEC       = 15
    # Cambio mínimo (%) para emitir señal; debajo → UNKNOWN
    MIN_CHANGE_PCT   = 10
    # Máximo de lecturas almacenadas por patente
    MAX_HISTORY      = 8

    def __init__(self):
        # plate → [(timestamp_float, bbox_width_px)]
        self._history: dict[str, list[tuple[float, int]]] = defaultdict(list)

    def record(self, plate: str, bbox_width: int) -> str:
        """
        Registra una nueva lectura y retorna la dirección estimada.

        Returns:
          "APPROACHING" | "DEPARTING" | "UNKNOWN"
        """
        if not bbox_width or bbox_width <= 0:
            return "UNKNOWN"

        now = time.monotonic()
        history = self._history[plate]

        # Purgar lecturas fuera de la ventana
        history[:] = [(t, w) for t, w in history if now - t <= self.WINDOW_SEC]

        if history:
            _, prev_width = history[-1]
            change_pct = ((bbox_width - prev_width) / prev_width) * 100

            if abs(change_pct) >= self.MIN_CHANGE_PCT:
                direction = "APPROACHING" if change_pct > 0 else "DEPARTING"
            else:
                direction = "UNKNOWN"
        else:
            direction = "UNKNOWN"   # primera lectura, sin referencia

        # Guardar y limitar historial
        history.append((now, bbox_width))
        if len(history) > self.MAX_HISTORY:
            history.pop(0)

        return direction

    def clear(self, plate: str):
        """Limpia el historial de una patente (llamar tras registrar EXIT)."""
        self._history.pop(plate, None)

    def get_trend(self, plate: str) -> str:
        """
        Evalúa el historial completo por regresión lineal simple.
        Útil cuando hay 3+ lecturas: más robusto que comparar solo la última.
        """
        history = self._history.get(plate, [])
        if len(history) < 3:
            return "UNKNOWN"

        widths = [w for _, w in history]
        n = len(widths)
        # Pendiente: m > 0 → creciendo (acercándose), m < 0 → alejándose
        mean_i = (n - 1) / 2
        mean_w = sum(widths) / n
        num = sum((i - mean_i) * (widths[i] - mean_w) for i in range(n))
        den = sum((i - mean_i) ** 2 for i in range(n))
        if den == 0:
            return "UNKNOWN"
        slope = num / den

        # Solo emitir señal si la pendiente es significativa
        threshold = mean_w * (self.MIN_CHANGE_PCT / 100) / n
        if slope >  threshold: return "APPROACHING"
        if slope < -threshold: return "DEPARTING"
        return "UNKNOWN"


# Instancia global — el proceso uvicorn tiene un solo worker por servicio
_direction = DirectionTracker()


# ─────────────────────────── Helpers ────────────────────────────────────────

def _load_ftp_events() -> list:
    if not os.path.exists(FTP_EVENTS_FILE):
        return []
    with open(FTP_EVENTS_FILE, "r") as f:
        return json.load(f)


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
    with open(FTP_EVENTS_FILE, "w") as f:
        json.dump(events[-500:], f, indent=2)


def _handle_auto_detection(plate: str, source: str, confidence: float,
                            strategy: str, img: np.ndarray = None,
                            bbox_width: int = 0, image_path: str = None) -> dict:
    """
    Lógica central de entrada/salida automática.

    Señal de dirección (DirectionTracker):
      DEPARTING  → fuerza EXIT si el auto está en parking, o descarta la
                   detección si no está (auto ya salió y sigue en cuadro)
      APPROACHING → staging normal (entrada probable)
      UNKNOWN    → comportamiento estándar (vehicle_exists decide)

    EXIT es siempre inmediato.
    ENTRY pasa por el buffer de staging (dedup + quality).
    """
    # 1. Registrar lectura en el tracker y obtener señal de dirección
    direction = _direction.record(plate, bbox_width)

    # Con ≥3 lecturas usamos la tendencia (más robusta que última comparación)
    history_len = len(_direction._history.get(plate, []))
    if history_len >= 3:
        direction = _direction.get_trend(plate)

    # 2. Si la dirección indica alejamiento Y el auto está estacionado → EXIT
    if direction == "DEPARTING" and vehicle_exists(plate):
        remove_vehicle(plate, image_path=image_path)
        log_to_csv(plate, "EXIT", status="FTP_AUTO", image_path=image_path)
        _append_ftp_event(plate, source, confidence, strategy, action="EXIT")
        _direction.clear(plate)
        return {"plate": plate, "action": "EXIT", "registered": True,
                "confidence": confidence, "strategy": strategy,
                "direction": direction}

    # 3. Si la dirección indica alejamiento pero NO está estacionado → ignorar
    #    (auto saliendo del campo visual sin haber entrado, o ya procesado)
    if direction == "DEPARTING" and not vehicle_exists(plate):
        return {"plate": plate, "action": "SKIP_DEPARTING", "registered": False,
                "confidence": confidence, "direction": direction}

    # 4. Si UNKNOWN o APPROACHING pero ya está en parking → SKIP (no registrar EXIT)
    #    (la ráfaga de fotos mientras está quieto no debe generar exits falsos)
    if (direction == "UNKNOWN" or direction == "APPROACHING") and vehicle_exists(plate):
        return {"plate": plate, "action": "SKIP_ALREADY_PARKED", "registered": False,
                "confidence": confidence, "direction": direction}

    # 5. Calcular quality score y enviar a staging
    if img is not None:
        quality = calculate_quality_score(img, plate, confidence)
    else:
        quality = {
            "quality_score":    confidence,
            "combined_score":   confidence,
            "sharpness":        0.5,
            "contrast_score":   0.5,
            "brightness_score": 0.5,
            "ocr_clarity":      confidence,
        }

    staging_result = staging_submit(plate, confidence, quality, strategy, image_path)
    _append_ftp_event(plate, source, confidence, strategy, action="STAGED")
    return {"plate": plate, "action": "STAGED", "registered": False,
            "confidence": confidence, "strategy": strategy,
            "direction": direction, "staging": staging_result}


# ─────────────────────────── Background task video ──────────────────────────

def _process_ftp_video_and_register(video_path: str, result_csv_path: str):
    _process_video_task(video_path, result_csv_path)

    if not os.path.exists(result_csv_path):
        print(f"ftp_video: no CSV at {result_csv_path}")
        return

    with open(result_csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            plate = row.get("Plate", "").strip()
            if not plate:
                continue
            result = _handle_auto_detection(
                plate, "video",
                float(row.get("Confidence", 0)), "video_clahe"
            )
            print(f"ftp_video {result['action']}: {plate}")


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
    now_dt = now_cl()
    date_str = now_dt.strftime("%Y-%m-%d")
    time_str = now_dt.strftime("%H-%M-%S")

    # Save image to disk
    os.makedirs(FTP_ARCHIVE_DIR + "/" + date_str, exist_ok=True)
    filename = f"{time_str}_{plate}_{date_str}.jpg"
    filepath = os.path.join(FTP_ARCHIVE_DIR, date_str, filename)
    cv2.imwrite(filepath, img)
    image_path = f"historico/{date_str}/{filename}"

    # Return detection result with image path
    detect_result = _handle_auto_detection(
        plate, "image", result["confidence"], result["strategy"],
        img=img, bbox_width=result.get("bbox_width", 0), image_path=image_path,
    )
    detect_result["image_path"] = image_path
    detect_result["image_url"] = f"/api/monitor/file/{image_path}"
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
