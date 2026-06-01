"""
Motor de Detección de Patentes — Central Parking MVP
=======================================================
Pipeline multi-estrategia inspirado en:
  - fast-alpr  (YOLOv9 + CCT-XS ONNX)     → detección moderna deep learning
  - fast-plate-ocr  (LicensePlateRecognizer) → OCR de alta precisión global
  - ParkingAPP (SIFT feature-matching)      → lógica de validación alternativa

Estrategias de detección (en orden de prioridad):
  1. Raw Image          - imagen directa al modelo ALPR
  2. CLAHE Enhancement  - realce de contraste adaptativo para escenas oscuras/pantalla
  3. Sharpening         - desenfoque invertido para imágenes borrosas o anguladas
  4. Grayscale+Equalize - histograma equalizado en escala de grises
  5. Cropped Center     - recorte del 60% central (útil cuando el viewfinder no está bien centrado)
"""

import asyncio
import os
import datetime
import random
import statistics
import cv2
import numpy as np
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

_API_KEY = os.environ.get("API_KEY", "")

from api.database import (
    init_db, load_db, upsert_vehicle, remove_vehicle, void_vehicle, vehicle_exists,
    log_to_db as log_to_csv, get_history, get_stats_today, clear_history, now_cl,
)


_JWT_SECRET = os.environ.get("JWT_SECRET", "changeme-set-JWT_SECRET-in-env")

# Rutas que no requieren JWT
_PUBLIC_PATHS = {"/auth/login", "/docs", "/openapi.json", "/redoc"}
_PUBLIC_PATH_PREFIXES = {"/api/monitor/file", "/api/monitor/images", "/api/monitor/review"}  # imágenes sin auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from api.auth import ensure_default_admin
    ensure_default_admin()
    from api.staging import staging_loop
    task = asyncio.create_task(staging_loop())
    yield
    task.cancel()


app = FastAPI(title="CParking AI Backend", version="2.0", lifespan=lifespan)

# CORS middleware PRIMERO (se agrega al inicio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600"
    }


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    from jose import JWTError, jwt as _jwt
    from fastapi.responses import Response

    # Preflight requests siempre OK
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=_cors_headers())

    client = request.client.host if request.client else ""
    is_local = client in ("127.0.0.1", "::1", "localhost")
    path = request.url.path

    # 1. API key OR JWT check (externo solamente)
    is_public = path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PATH_PREFIXES)
    if not is_local and not is_public:
        has_valid_api_key = False
        if _API_KEY and request.headers.get("X-API-Key", "") == _API_KEY:
            has_valid_api_key = True

        has_valid_jwt = False
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                _jwt.decode(auth_header[7:], _JWT_SECRET, algorithms=["HS256"])
                has_valid_jwt = True
            except JWTError:
                pass

        if not (has_valid_api_key or has_valid_jwt):
            return JSONResponse({"detail": "Se requiere autenticación (API Key o JWT)"}, status_code=401, headers=_cors_headers())

    response = await call_next(request)
    # Agregar CORS headers a TODAS las respuestas
    for key, value in _cors_headers().items():
        response.headers[key] = value
    return response

# ─────────────────────────── Motor de IA ───────────────────────────────────

HAS_ML = False
alpr = None

try:
    from fast_alpr import ALPR
    alpr = ALPR(
        detector_model="yolo-v9-t-384-license-plate-end2end",
        ocr_model="cct-xs-v2-global-model",
        detector_conf_thresh=0.25,   # Umbral más bajo → detecta patentes más difíciles
    )
    HAS_ML = True
    print("AI engine online — YOLOv9 + CCT-XS ONNX")
except Exception as e:
    print(f"AI engine offline: {e} — modo simulado activado")


# ─────────────────────────── Pipeline de pre-procesamiento ─────────────────

def strategy_clahe(img: np.ndarray) -> np.ndarray:
    """
    CLAHE (Contrast Limited Adaptive Histogram Equalization).
    Inspirado en técnicas industriales para lectura en condiciones de baja luz
    o al fotografiar pantallas (como se hace en este parking).
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)


def strategy_sharpen(img: np.ndarray) -> np.ndarray:
    """
    Desenfoque invertido (Unsharp Masking).
    Útil cuando la imagen viene borrosa por ángulo, movimiento o lente.
    """
    blur = cv2.GaussianBlur(img, (0, 0), sigmaX=3)
    return cv2.addWeighted(img, 1.5, blur, -0.5, 0)


def strategy_grayscale_eq(img: np.ndarray) -> np.ndarray:
    """
    Normalización en escala de grises con ecualización de histograma.
    Vuelve el contraste más uniforme entre caracteres y fondo de la placa.
    Inspirado en el flujo de ParkingAPP que convierte BGR a GRAY antes del SIFT.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    eq = cv2.equalizeHist(gray)
    return cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR)


def strategy_center_crop(img: np.ndarray) -> np.ndarray:
    """
    Recorta el 60% central de la imagen.
    Útil cuando el operador toma la foto de lejos y la patente
    queda en el centro pero el modelo tiene dificultad con la escena completa.
    """
    h, w = img.shape[:2]
    margin_y = int(h * 0.2)
    margin_x = int(w * 0.2)
    cropped = img[margin_y:h-margin_y, margin_x:w-margin_x]
    return cv2.resize(cropped, (w, h))


def strategy_bilateral_denoise(img: np.ndarray) -> np.ndarray:
    """Filtro bilateral: reduce ruido JPEG preservando bordes de caracteres."""
    return cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)


def strategy_perspective_deskew(img: np.ndarray) -> np.ndarray:
    """
    Corrección de perspectiva automática (deskew).

    PROBLEMA: el operador fotografía la patente en diagonal → caracteres torcidos → OCR falla.
    SOLUCIÓN: detectar el rectángulo dominante (Canny + findContours) y aplicar
    warpPerspective para enderezarlo antes de enviar al modelo.

    Confirmado en la imagen de prueba fast-alpr/assets/test_image.png:
    El modelo YOLOv9 detectó '5AU5341' con confianza 99.9% desde la foto del auto completo.
    Esta estrategia ayuda cuando la foto viene inclinada.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) != 4:
            continue
        pts = approx.reshape(4, 2).astype(np.float32)
        s, diff = pts.sum(axis=1), np.diff(pts, axis=1)
        ordered = np.array([
            pts[np.argmin(s)], pts[np.argmin(diff)],
            pts[np.argmax(s)], pts[np.argmax(diff)],
        ], dtype=np.float32)
        w = float(max(np.linalg.norm(ordered[1]-ordered[0]), np.linalg.norm(ordered[2]-ordered[3])))
        h = float(max(np.linalg.norm(ordered[3]-ordered[0]), np.linalg.norm(ordered[2]-ordered[1])))
        if w < 10 or h < 5:
            continue
        dst = np.array([[0,0],[w,0],[w,h],[0,h]], dtype=np.float32)
        warped = cv2.warpPerspective(img, cv2.getPerspectiveTransform(ordered, dst), (int(w), int(h)))
        return cv2.resize(warped, (img.shape[1], img.shape[0]))
    return img


def strategy_upscale(img: np.ndarray) -> np.ndarray:
    """
    Upscale 2x con interpolación bicúbica.
    Para fotos de lejos donde la patente queda muy pequeña en píxeles.
    YOLOv9 fue entrenado a 384px — imágenes muy pequeñas pierden precisión.
    """
    h, w = img.shape[:2]
    return cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)


STRATEGIES = [
    # Primera pasada — imagen tal cual (la más rápida)
    ("raw",                   lambda img: img),
    # Realce de contraste — para fotos a pantalla o escenas oscuras
    ("clahe",                 strategy_clahe),
    # Sharpening — para fotos movidas o con blur por ángulo
    ("sharpen",               strategy_sharpen),
    # Corrección de perspectiva — para fotos diagonales
    ("deskew",                strategy_perspective_deskew),
    # Deskew + realce combinado
    ("deskew+clahe",          lambda img: strategy_clahe(strategy_perspective_deskew(img))),
    # Denoising + contraste — para JPEG comprimido
    ("bilateral+clahe",       lambda img: strategy_clahe(strategy_bilateral_denoise(img))),
    # Escala de grises equalizada — inspirado en ParkingAPP SIFT pipeline
    ("grayscale_eq",          strategy_grayscale_eq),
    # Recorte central — si el operador encuadró mal
    ("center_crop",           strategy_center_crop),
    ("center_crop+clahe",     lambda img: strategy_clahe(strategy_center_crop(img))),
    # Upscale — foto tomada de lejos
    ("upscale",               strategy_upscale),
    ("upscale+clahe",         lambda img: strategy_clahe(strategy_upscale(img))),
]


import re

# ─────────────────────────── Validación de patentes ─────────────────────────

_PLATE_PATTERNS = [
    # Chile actual (2007-hoy): 4 letras + 2 dígitos — BBCC12
    re.compile(r'^[A-Z]{4}\d{2}$'),
    # Chile antiguo (1985-2007): 2 letras + 4 dígitos — AA1000
    re.compile(r'^[A-Z]{2}\d{4}$'),
    # Chile próximo (4+ ruedas): 5 letras + 1 dígito — BBBBB0
    re.compile(r'^[A-Z]{5}\d{1}$'),
    # Chile moto actual: 3 letras + 2 dígitos — BBB12
    re.compile(r'^[A-Z]{3}\d{2}$'),
    # Chile moto próximo: 4 letras + 1 dígito — BBBB0
    re.compile(r'^[A-Z]{4}\d{1}$'),
    # Argentina Mercosur (1994-hoy): 3 letras + 3 dígitos — ABC123
    re.compile(r'^[A-Z]{3}\d{3}$'),
    # Argentina nuevo Mercosur (2016-hoy): 2 letras + 3 dígitos + 2 letras — AB123CD
    re.compile(r'^[A-Z]{2}\d{3}[A-Z]{2}$'),
    # Perú: 3 letras + 3 dígitos — ABC123
    re.compile(r'^[A-Z]{3}\d{3}$'),
    # Bolivia: 3 letras + 3-4 dígitos — ABC1234
    re.compile(r'^[A-Z]{3}\d{3,4}$'),
]


def is_valid_plate(text: str) -> bool:
    """Valida que el texto leído calce con algún formato de patente conocido en la región."""
    return any(p.match(text) for p in _PLATE_PATTERNS)


def extract_best_plate(results, strategy_name: str) -> Optional[dict]:
    """
    Extrae el texto de patente con mayor confianza promedio de los resultados ALPR.
    Filtra lecturas que no calzan con formatos de patente chilenos o de países vecinos.
    """
    if not results:
        return None

    best_text = None
    best_conf = -1.0

    for r in results:
        if r.ocr is None or not r.ocr.text:
            continue

        conf_raw = r.ocr.confidence
        if isinstance(conf_raw, list) and conf_raw:
            conf = statistics.mean(conf_raw)
        elif isinstance(conf_raw, (float, int)):
            conf = float(conf_raw)
        else:
            conf = 0.0

        text = "".join(c for c in str(r.ocr.text).upper() if c.isalnum())

        if not is_valid_plate(text):
            continue

        if conf > best_conf:
            best_conf = conf
            best_text = text
            best_bbox_w = r.detection.bounding_box.width if r.detection else 0

    if best_text:
        return {
            "plate":      best_text,
            "confidence": best_conf,
            "strategy":   strategy_name,
            "bbox_width": best_bbox_w,  # ancho del bounding box de la patente en px
        }
    return None


def run_multi_strategy(img: np.ndarray) -> Optional[dict]:
    """
    Votación por consenso: corre todas las estrategias, agrupa por texto de placa,
    y elige la que más estrategias detectaron. Empates se resuelven por confianza promedio.
    """
    candidates = []
    reports = []

    for name, fn in STRATEGIES:
        try:
            processed = fn(img)
            results = alpr.predict(processed)
            candidate = extract_best_plate(results, name)
            if candidate:
                candidates.append(candidate)
            else:
                pass
        except Exception as e:
            print(f"strategy {name} error: {e}")

    if not candidates:
        print("no_detection")
        return None

    votes: dict[str, list[dict]] = {}
    for c in candidates:
        votes.setdefault(c["plate"], []).append(c)

    def score(plate_group):
        group = votes[plate_group]
        return (len(group), statistics.mean(c["confidence"] for c in group))

    winner_plate = max(votes, key=score)
    winner_group = votes[winner_plate]
    best = max(winner_group, key=lambda c: c["confidence"])
    avg_conf = statistics.mean(c["confidence"] for c in winner_group)

    print(
        f"detection: {best['plate']} "
        f"votes={len(winner_group)}/{len(STRATEGIES)} "
        f"conf_avg={avg_conf:.2f} conf_max={best['confidence']:.2f} "
        f"strategy={best['strategy']}"
    )
    return best


# ─────────────────────────── Modelos Pydantic ───────────────────────────────

class CarEntry(BaseModel):
    plate: str
    isEvent: bool = False
    eventFee: Optional[float] = None

# ─────────────────────────── Endpoints ─────────────────────────────────────

@app.get("/api/cars")
async def get_cars():
    return load_db()


@app.get("/api/history")
async def api_get_history(limit: int = 50):
    return get_history(limit=min(limit, 2000))


@app.post("/api/clear-history")
async def api_clear_history():
    clear_history()
    return {"status": "cleared"}


@app.get("/api/stats")
async def get_stats():
    return get_stats_today()


@app.post("/api/detect")
async def detect(image: UploadFile = File(...)):
    # Modo simulado si la IA no está disponible
    if not HAS_ML:
        plate = f"SIM{random.randint(1000, 9999)}"
        log_to_csv(plate, "DETECTION", "MOCKED")
        return {"plate": plate, "mocked": True, "confidence": 0.9, "strategy": "mock"}

    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return {"plate": None, "error": "image decode failed"}

        result = run_multi_strategy(img)

        if result:
            log_to_csv(result["plate"], "DETECTION", "REAL", conf=result["confidence"])
            return {
                "plate": result["plate"],
                "confidence": result["confidence"],
                "strategy": result["strategy"],
                "mocked": False,
            }

        return {"plate": None, "error": "no_detection"}

    except Exception as e:
        print(f"Error en /detect: {e}")
        return {"plate": None, "error": str(e)}


@app.post("/api/entry")
async def entry(e: CarEntry):
    entry_time = now_cl().timestamp() * 1000
    upsert_vehicle(e.plate, entry_time, e.isEvent, e.eventFee)
    log_to_csv(e.plate, "ENTRY")
    return {"plate": e.plate, "entryTime": entry_time, "isEvent": e.isEvent, "eventFee": e.eventFee}


@app.post("/api/exit/{plate}")
async def exit_car(plate: str, fee: float = 0):
    if not vehicle_exists(plate):
        raise HTTPException(status_code=404, detail="Plate not in parking")
    remove_vehicle(plate, fee=fee)
    log_to_csv(plate, "EXIT", fee=fee)
    return {"status": "ok"}


@app.delete("/api/cars/{plate}")
async def delete_car(plate: str):
    void_vehicle(plate)
    log_to_csv(plate, "VOID")
    return {"status": "voided"}

# Register video processor at the end to avoid circular imports
from .video_processor import router as video_router
app.include_router(video_router)

# Register FTP handler
from .ftp_handler import router as ftp_router
app.include_router(ftp_router)

# Register staging + audit endpoints
from .staging import router as staging_router
app.include_router(staging_router)

# Register Excel upload + reconciliation
from .excel import router as excel_router
app.include_router(excel_router)

# Register auth
from .auth import router as auth_router
app.include_router(auth_router)

