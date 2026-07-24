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

import os
import datetime
import statistics
import cv2
import numpy as np
from fastapi import FastAPI
from typing import Optional

from api.core.lifespan import lifespan
from api.core.security import install_security


app = FastAPI(title="CParking AI Backend", version="2.0", lifespan=lifespan)
install_security(app)

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


def strategy_highlight_recovery(img: np.ndarray) -> np.ndarray:
    """
    Recuperación de altas luces (highlight recovery).

    PROBLEMA: luces delanteras/traseras del auto sobreexponen parte de la
    patente — típicamente el último carácter, más cercano al foco de luz.
    Un píxel ya saturado a blanco puro (255) no tiene detalle que recuperar,
    pero la franja "casi blanca" (L≈180-254 en espacio LAB) suele conservar
    algo de gradiente real entre el carácter y el fondo, solo que comprimido
    en un rango tan angosto que se ve plano. Bajar la exposición global (o
    CLAHE de tile fijo) no ayuda: aplasta el resto de la placa que ya estaba
    bien expuesta sin aportar contraste donde realmente falta.

    SOLUCIÓN: estira lo que haya de variación real dentro de esa franja alta
    (min-max stretch acotado a L>180) para ocupar todo el rango 180-255, y
    luego aplica CLAHE de tile chico para resaltar los bordes de los
    caracteres ya separados. Si la franja está perfectamente saturada
    (sin variación real, min==max), no hay nada que estirar y la imagen
    queda igual — evita inventar contraste donde no hay información.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    highlights = l[l > 180]
    if highlights.size > 20:
        lo = float(highlights.min())
        hi = float(highlights.max())
        if hi - lo > 1:
            lut = np.arange(256, dtype=np.float32)
            mask = lut > 180
            lut[mask] = 180 + (lut[mask] - lo) / (hi - lo) * (255 - 180)
            lut = np.clip(lut, 0, 255).astype(np.uint8)
            l = cv2.LUT(l, lut)

    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    l = clahe.apply(l)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


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
    # Recuperación de altas luces — para luces del auto que queman parte de la placa
    ("highlight_recovery",    strategy_highlight_recovery),
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


def extract_best_plate(results, strategy_name: str,
                       image_shape=None) -> Optional[dict]:
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
            if r.detection:
                bbox = r.detection.bounding_box
                if image_shape is not None:
                    height, width = image_shape[:2]
                    best_center_x = ((bbox.x1 + bbox.x2) / 2) / width
                    best_center_y = ((bbox.y1 + bbox.y2) / 2) / height
                    # Tamaño normalizado de la patente (promedio ancho/alto):
                    # crece cuando el auto se acerca a la cámara, sin importar
                    # el ángulo de la toma — complementa a center_x/center_y,
                    # que solo aporta señal cuando el auto cruza el cuadro.
                    norm_width = (bbox.x2 - bbox.x1) / width
                    norm_height = (bbox.y2 - bbox.y1) / height
                    best_size = (norm_width + norm_height) / 2
                else:
                    best_center_x = best_center_y = best_size = None
            else:
                best_center_x = best_center_y = best_size = None

    if best_text:
        return {
            "plate":      best_text,
            "confidence": best_conf,
            "strategy":   strategy_name,
            "center_x":   best_center_x,
            "center_y":   best_center_y,
            "size":       best_size,
        }
    return None


# Una lectura corroborada por una sola estrategia (de 12) es la más fácil de
# confundir con ruido/objetos fijos del fondo (ver caso real: bloque de
# hormigón/plástico leído como patente con confianza 0.62-0.69 por una sola
# estrategia). Lecturas de 2+ estrategias no pasan por este filtro: ya están
# corroboradas independientemente y bajarles el piso de confianza rechazaría
# patentes reales verificadas (ver LLPD45, VYFJ45 en el archivo histórico).
#
# El piso se bajó de 0.75 a 0.70 (2026-07-17): deja solo 0.01 de margen sobre
# el techo documentado del falso positivo (0.69), así que recupera lecturas
# reales de una sola estrategia entre 0.70-0.75 que hoy se descartaban, sin
# reabrir ese caso puntual. Si en producción reaparecen falsos positivos de
# fondo en ese rango, subir MIN_SINGLE_VOTE_CONFIDENCE por env var (sin tocar
# código) es la primera palanca a probar antes de tocar esta lógica.
MIN_SINGLE_VOTE_CONFIDENCE = float(os.environ.get("MIN_SINGLE_VOTE_CONFIDENCE", "0.70"))


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
            candidate = extract_best_plate(results, name, processed.shape)
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

    if len(winner_group) == 1 and best["confidence"] < MIN_SINGLE_VOTE_CONFIDENCE:
        print(
            f"no_detection: {winner_plate} descartado "
            f"(1 sola estrategia, conf={best['confidence']:.2f} "
            f"< {MIN_SINGLE_VOTE_CONFIDENCE})"
        )
        return None

    # Para dirección se prefieren estrategias que conservan la geometría original.
    geometry_preserving = {
        "raw", "clahe", "highlight_recovery", "sharpen", "bilateral+clahe", "grayscale_eq"
    }
    position_candidates = [
        candidate for candidate in winner_group
        if candidate["strategy"] in geometry_preserving
        and candidate.get("center_x") is not None
    ]
    if position_candidates:
        position_source = max(position_candidates, key=lambda c: c["confidence"])
        best = {
            **best,
            "center_x": position_source["center_x"],
            "center_y": position_source["center_y"],
            "size": position_source["size"],
            "position_strategy": position_source["strategy"],
        }
    avg_conf = statistics.mean(c["confidence"] for c in winner_group)

    print(
        f"detection: {best['plate']} "
        f"votes={len(winner_group)}/{len(STRATEGIES)} "
        f"conf_avg={avg_conf:.2f} conf_max={best['confidence']:.2f} "
        f"strategy={best['strategy']}"
    )
    return best


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

# Register direction configuration and aggregated audit endpoints
from .routers.direction import router as direction_router
app.include_router(direction_router)

# Register extracted domain routers while preserving every public path
from .routers.detection import router as detection_router
from .routers.history import router as history_router
from .routers.parking import router as parking_router
from .routers.reconciliation import router as reconciliation_router
app.include_router(detection_router)
app.include_router(history_router)
app.include_router(parking_router)
app.include_router(reconciliation_router)
