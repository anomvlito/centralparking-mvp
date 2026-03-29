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

import json
import os
import datetime
import random
import statistics
import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="CParking AI Backend", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "parking_db.json"
HISTORY_FILE = "history.csv"

# ─────────────────────────── Helpers de persistencia ────────────────────────

def load_db():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE, 'r') as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=2)

def log_to_csv(plate, action, status="REAL", fee=0, conf=1.0):
    import csv
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([ts, plate, action, status, fee, f"{conf:.2f}"])

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
    print("✅ AI Engine ONLINE — YOLOv9 + CCT-XS ONNX")
except Exception as e:
    print(f"⚠️  AI Engine OFFLINE: {e}")
    print("   Modo simulado activado.")


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


def extract_best_plate(results, strategy_name: str) -> Optional[dict]:
    """
    Extrae el texto de patente con mayor confianza promedio de los resultados ALPR.
    Lógica de confianza tomada directamente de fast-alpr/alpr.py (statistics.mean de char_probs).
    """
    if not results:
        return None

    best_text = None
    best_conf = -1.0

    for r in results:
        if r.ocr is None or not r.ocr.text:
            continue

        # Confianza exacta como la calcula fast-alpr internamente
        conf_raw = r.ocr.confidence
        if isinstance(conf_raw, list) and conf_raw:
            conf = statistics.mean(conf_raw)
        elif isinstance(conf_raw, (float, int)):
            conf = float(conf_raw)
        else:
            conf = 0.0

        # Limpieza básica: solo alfanumérico, mínimo 4 caracteres
        text = "".join(c for c in str(r.ocr.text).upper() if c.isalnum())
        if len(text) < 4:
            continue

        if conf > best_conf:
            best_conf = conf
            best_text = text

    if best_text:
        return {"plate": best_text, "confidence": best_conf, "strategy": strategy_name}
    return None


def run_multi_strategy(img: np.ndarray) -> Optional[dict]:
    """
    Ejecuta el pipeline de detección con todas las estrategias en orden.
    Retorna el primer resultado válido encontrado.
    Primera estrategia exitosa gana (fast path).
    Si ninguna estrategia funciona, retorna None.
    """
    reports = []
    for name, fn in STRATEGIES:
        try:
            processed = fn(img)
            results = alpr.predict(processed)
            candidate = extract_best_plate(results, name)
            if candidate:
                print(f"✅ Detectado con estrategia '{name}': {candidate['plate']} (conf={candidate['confidence']:.2f})")
                return candidate
            else:
                reports.append(f"  ❌ '{name}': sin resultado")
        except Exception as e:
            reports.append(f"  💥 '{name}': error — {e}")

    print("⚠️  Sin detección en todas las estrategias:")
    for r in reports:
        print(r)
    return None


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
async def get_history():
    import csv
    if not os.path.exists(HISTORY_FILE): return []
    rows = []
    with open(HISTORY_FILE, mode='r') as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip header
        for row in reader:
            if row: rows.append(row)
    return rows[-50:][::-1]


@app.post("/api/clear-history")
async def clear_history():
    import csv
    with open(HISTORY_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Plate", "Action", "Status", "Fee", "Confidence"])
    return {"status": "cleared"}


@app.get("/api/stats")
async def get_stats():
    import csv
    if not os.path.exists(HISTORY_FILE):
        return {"today_income": 0, "today_entries": 0, "today_exits": 0, "parked_now": len(load_db())}
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    income, entries, exits = 0, 0, 0
    with open(HISTORY_FILE, mode='r') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3 or not row[0].startswith(today): continue
            if row[2] == "ENTRY": entries += 1
            elif row[2] == "EXIT":
                exits += 1
                try: income += float(row[4])
                except: pass
    return {"today_income": income, "today_entries": entries, "today_exits": exits, "parked_now": len(load_db())}


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
    db = load_db()
    db[e.plate] = {
        "plate": e.plate,
        "entryTime": datetime.datetime.now().timestamp() * 1000,
        "isEvent": e.isEvent,
        "eventFee": e.eventFee,
    }
    save_db(db)
    log_to_csv(e.plate, "ENTRY")
    return db[e.plate]


@app.post("/api/exit/{plate}")
async def exit_car(plate: str, fee: float = 0):
    db = load_db()
    if plate in db:
        db.pop(plate)
        save_db(db)
        log_to_csv(plate, "EXIT", fee=fee)
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Plate not in parking")


@app.delete("/api/cars/{plate}")
async def delete_car(plate: str):
    db = load_db()
    if plate in db:
        del db[plate]
        save_db(db)
        log_to_csv(plate, "VOID")
    return {"status": "voided"}
