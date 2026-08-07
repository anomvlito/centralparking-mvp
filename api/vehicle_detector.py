"""
Filtro de vehículo — Central Parking MVP (ver ADR-004)

Detector genérico COCO (YOLOX-Tiny, ONNX, Apache 2.0) usado como gate barato
antes del pipeline de patente (12 estrategias, `api/detect.py`). Solo decide
"¿hay un vehículo en esta imagen?" — no reemplaza ni interactúa con el
modelo de patente (`yolo-v9-t-384-license-plate-end2end`).

2026-08-06: se evaluó primero YOLOX-Nano, pero contra imágenes reales de
este proyecto falló en casos claros (auto cerca y visible, sin oclusión,
score 0.11 — ver ADR-004 "Fix 2026-08-06"). La cámara SALIDA es fisheye/gran
angular y muy cercana al vehículo, una condición fuera de lo típico para un
detector COCO genérico. YOLOX-Tiny (mismo origen, ~3x más pesado, 65ms/frame
en este hardware) corrigió esos casos sin perder discriminación en escenas
vacías — validado contra 143 imágenes con vehículo confirmado + 535 sin
detección del 2026-08-06.

Carga perezosa + fail-open: si el modelo no está disponible (sin internet en
el primer arranque, ONNX corrupto, etc.), `has_vehicle()` siempre devuelve
`True` — un filtro que no pudo evaluar nunca debe bloquear la detección real
de patente. Mismo espíritu que `HAS_ML` en `api/detect.py`.
"""

import os
import urllib.request
from typing import Optional

import cv2
import numpy as np

from api.core.config import VEHICLE_FILTER_SETTINGS
from api.database import log_audit_event

_MODEL_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/"
    "0.1.1rc0/yolox_tiny.onnx"
)
_MODEL_CACHE_DIR = os.path.expanduser("~/.cache/vehicle-filter")
_MODEL_PATH = os.path.join(_MODEL_CACHE_DIR, "yolox_tiny.onnx")
_INPUT_SIZE = 416
_PAD_VALUE = 114

# Índices de clase COCO relevantes para "hay vehículo" (ver ADR-004).
_VEHICLE_CLASS_IDS = (2, 3, 5, 7)  # car, motorcycle, bus, truck

HAS_VEHICLE_FILTER = False
_session = None


def _ensure_model() -> Optional[str]:
    if os.path.exists(_MODEL_PATH):
        return _MODEL_PATH
    try:
        os.makedirs(_MODEL_CACHE_DIR, exist_ok=True)
        tmp_path = _MODEL_PATH + ".tmp"
        urllib.request.urlretrieve(_MODEL_URL, tmp_path)
        os.replace(tmp_path, _MODEL_PATH)
        return _MODEL_PATH
    except Exception as e:
        print(f"vehicle_detector: no se pudo descargar el modelo ({e})")
        return None


try:
    import onnxruntime as ort

    _model_path = _ensure_model()
    if _model_path:
        _session = ort.InferenceSession(
            _model_path, providers=["CPUExecutionProvider"]
        )
        HAS_VEHICLE_FILTER = True
        print("vehicle_detector: filtro de vehículo online — YOLOX-Tiny ONNX")
except Exception as e:
    print(f"vehicle_detector: filtro offline ({e}) — fail-open, no filtra")


def _letterbox(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(_INPUT_SIZE / h, _INPUT_SIZE / w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), _PAD_VALUE, dtype=np.uint8)
    canvas[:nh, :nw] = resized
    return canvas


def vehicle_score(img: np.ndarray) -> float:
    """
    Score máximo de "hay vehículo" en [0, 1]: objectness × score de clase,
    tomando el máximo entre las clases COCO de vehículo, sobre todas las
    anclas de salida. No decodifica cajas ni aplica NMS — no hacen falta
    para la decisión binaria de este filtro (validado contra imágenes
    reales de este proyecto, ver ADR-004).

    Si el modelo no está disponible, devuelve 1.0 (fail-open: nunca bloquea
    el pipeline de patente por no poder evaluar).
    """
    if not HAS_VEHICLE_FILTER or _session is None:
        return 1.0
    canvas = _letterbox(img)
    inp = canvas.transpose(2, 0, 1)[None].astype(np.float32)
    out = _session.run(None, {"images": inp})[0][0]  # (anchors, 85)
    objectness = out[:, 4]
    class_scores = out[:, 5:]
    best = 0.0
    for class_id in _VEHICLE_CLASS_IDS:
        combined = objectness * class_scores[:, class_id]
        m = float(combined.max())
        if m > best:
            best = m
    return best


def has_vehicle(img: np.ndarray, threshold: float) -> bool:
    return vehicle_score(img) >= threshold


def passes_vehicle_filter(img: np.ndarray, source: str) -> bool:
    """
    Gate barato antes de correr ALPR (ver ADR-004), reusado por el flujo de
    fotos (`api/ftp_handler.py`) y de video (`api/video_processor.py`).
    Devuelve True cuando hay que seguir con el pipeline de patente
    (comportamiento actual si el filtro está deshabilitado, en shadow_mode,
    o no logra evaluar).

    shadow_mode audita la decisión sin afectar el pipeline — paso
    obligatorio antes de confiar el filtro para saltar ALPR de verdad.
    """
    settings = VEHICLE_FILTER_SETTINGS
    if not settings.enabled:
        return True
    score = vehicle_score(img)
    vehicle_present = score >= settings.conf_threshold
    if not vehicle_present:
        try:
            log_audit_event(None, "VEHICLE_FILTER_EVAL", {
                "score": round(score, 4),
                "threshold": settings.conf_threshold,
                "shadow_mode": settings.shadow_mode,
                "source": source,
            })
        except Exception:
            # La auditoría no puede romper el pipeline de detección real
            # (mismo criterio que DirectionService._audit_sink).
            pass
    if settings.shadow_mode:
        return True
    return vehicle_present
