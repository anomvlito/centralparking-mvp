#!/usr/bin/env python3
"""
test_plates.py — Tester de la API de detección con imágenes reales
====================================================================
Descarga fotos de autos de fuentes públicas y testea la API de detección.

Uso:
    python3 test_plates.py                    # Usa imágenes del repo local
    python3 test_plates.py --api http://...   # Apunta a otra URL de API
    python3 test_plates.py --download         # Descarga datasets adicionales
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import requests

API_URL = "http://localhost:8000"

# ─── Imágenes de prueba ya disponibles localmente ─────────────────────────────
LOCAL_IMAGES = [
    {
        "path": "../repos/fast-alpr/assets/test_image.png",
        "expected": "5AU5341",
        "description": "Škoda (vista trasera, patente checa) — foto de auto completo",
    },
    {
        "path": "../repos/ParkingAPP/Images/parking.jpg",
        "expected": None,  # vista aérea, puede o no detectar
        "description": "Estacionamiento aéreo — múltiples autos",
    },
    {
        "path": "../repos/ParkingAPP/img.jpg",
        "expected": None,
        "description": "Imagen extra ParkingAPP",
    },
]

# ─── Fuentes de imágenes de autos gratuitas ───────────────────────────────────
# Todas son Creative Commons / dominio público
ONLINE_SOURCES = [
    # Wikimedia Commons: autos con patentes visibles (CC BY-SA)
    {
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/27/Parked_cars.jpg/1280px-Parked_cars.jpg",
        "name": "wikimedia_parked_cars.jpg",
        "description": "Autos estacionados (UK)",
    },
    {
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/320px-Camponotus_flavomarginatus_ant.jpg",
        "name": "skip",  # no es auto, skip
        "description": "skip",
    },
    # Roboflow Universe — muestra pública (no requiere login para preview)
    {
        "url": "https://storage.googleapis.com/openimages/web/images/open_images_validation_2016_45k_examples.tar.gz",
        "name": "skip",
        "description": "skip",
    },
]

# ─── El test real ─────────────────────────────────────────────────────────────

def test_image_file(image_path: str, expected: str | None, description: str) -> dict:
    """Envía una imagen al endpoint /api/detect y muestra el resultado."""
    path = Path(image_path)
    if not path.exists():
        print(f"  ⚠️  Archivo no encontrado: {image_path}")
        return {"status": "missing"}

    print(f"\n📸 {description}")
    print(f"   Archivo: {path.name} ({path.stat().st_size // 1024}KB)")

    # Leer con OpenCV para validar que es una imagen real
    img = cv2.imread(str(path))
    if img is None:
        print(f"   ❌ No se pudo decodificar como imagen")
        return {"status": "decode_error"}

    print(f"   Resolución: {img.shape[1]}x{img.shape[0]}px")

    # Enviar a la API
    t0 = time.time()
    with open(path, "rb") as f:
        resp = requests.post(f"{API_URL}/api/detect", files={"image": (path.name, f, "image/jpeg")})
    elapsed = time.time() - t0

    if not resp.ok:
        print(f"   ❌ API Error {resp.status_code}: {resp.text[:200]}")
        return {"status": "api_error", "code": resp.status_code}

    data = resp.json()
    plate = data.get("plate")
    conf = data.get("confidence", 0)
    strategy = data.get("strategy", "?")
    mocked = data.get("mocked", False)

    print(f"   🔍 Resultado: {plate or 'SIN DETECCIÓN'}")
    if plate:
        print(f"   ✅ Confianza: {conf:.2%}")
        print(f"   🧠 Estrategia: {strategy}")
    if mocked:
        print(f"   ⚠️  (Modo simulado — IA offline)")
    print(f"   ⏱️  Tiempo: {elapsed:.2f}s")

    # Comparar con resultado esperado si lo sabemos
    if expected and plate:
        match = expected.upper().replace("-", "") == str(plate).upper().replace("-", "")
        print(f"   {'✅ CORRECTO' if match else '❌ INCORRECTO'} (esperado: {expected})")
    elif expected and not plate:
        print(f"   ❌ FALLO — esperado: {expected}, no detectó nada")

    return {"plate": plate, "confidence": conf, "strategy": strategy, "time_s": elapsed}


def download_image(url: str, dest: str) -> bool:
    """Descarga una imagen de URL."""
    try:
        r = requests.get(url, timeout=15, stream=True)
        if r.ok and "image" in r.headers.get("content-type", ""):
            with open(dest, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            print(f"   ✅ Descargado: {dest}")
            return True
    except Exception as e:
        print(f"   ⚠️  Error descargando {url}: {e}")
    return False


def check_api():
    """Verifica que la API esté viva."""
    try:
        r = requests.get(f"{API_URL}/api/stats", timeout=3)
        if r.ok:
            print(f"✅ API viva en {API_URL}")
            return True
    except:
        pass
    print(f"❌ API no responde en {API_URL}")
    print(f"   ¿Está corriendo uvicorn? → uvicorn api.detect:app --port 8000")
    return False


def main():
    global API_URL
    parser = argparse.ArgumentParser(description="Tester de detección de patentes")
    parser.add_argument("--api", default=API_URL, help="URL base de la API")
    parser.add_argument("--download", action="store_true", help="Descarga imágenes extra de internet")
    parser.add_argument("--dir", help="Directorio con imágenes propias a testear")
    args = parser.parse_args()

    API_URL = args.api

    print("\n" + "="*60)
    print("  CParking — Tester de Detección de Patentes")
    print("="*60)

    # Verificar API
    if not check_api():
        sys.exit(1)

    results = []
    test_dir = Path(__file__).parent

    # ── Test 1: Imágenes locales del repo ─────────────────────────────────────
    print("\n─── Imágenes del Repositorio ─────────────────────────────────")
    for item in LOCAL_IMAGES:
        full_path = str(test_dir / item["path"])
        r = test_image_file(full_path, item.get("expected"), item["description"])
        results.append({**r, "source": "local", "description": item["description"]})

    # ── Test 2: Directorio personalizado ──────────────────────────────────────
    if args.dir:
        custom_dir = Path(args.dir)
        print(f"\n─── Imágenes de {custom_dir} ─────────────────────────────────")
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
            for img_path in sorted(custom_dir.glob(ext)):
                r = test_image_file(str(img_path), None, img_path.name)
                results.append({**r, "source": "custom", "description": img_path.name})

    # ── Test 3: Descarga desde internet (opcional) ────────────────────────────
    if args.download:
        print("\n─── Descargando imágenes de prueba desde internet ────────────")
        
        # Fuentes reales de autos con patentes visibles (Wikimedia CC BY)
        real_sources = [
            ("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d6/Roter_Komet.jpg/1280px-Roter_Komet.jpg", "test_car_german.jpg", "Auto alemán con patente"),
            ("https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=1280", "test_car_front.jpg", "Auto frontal"),
            ("https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=1280", "test_car_back.jpg", "Auto trasero"),
        ]
        
        download_dir = test_dir / "test_images"
        download_dir.mkdir(exist_ok=True)
        
        for url, filename, desc in real_sources:
            dest = str(download_dir / filename)
            print(f"\n📥 {desc}")
            if download_image(url, dest):
                r = test_image_file(dest, None, desc)
                results.append({**r, "source": "download", "description": desc})
            time.sleep(0.5)

    # ── Resumen Final ──────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  RESUMEN")
    print("="*60)

    total = len(results)
    detected = sum(1 for r in results if r.get("plate"))
    mocked = sum(1 for r in results if r.get("strategy") == "mock")
    avg_time = sum(r.get("time_s", 0) for r in results) / total if total else 0
    avg_conf = sum(r.get("confidence", 0) for r in results if r.get("confidence")) / max(detected, 1)

    print(f"\n  Total imágenes: {total}")
    print(f"  Detectadas:     {detected} ({detected/total*100:.0f}% tasa de éxito)")
    print(f"  Tiempo promedio: {avg_time:.2f}s por imagen")
    if detected: print(f"  Confianza promedio: {avg_conf:.2%}")
    if mocked:   print(f"  ⚠️  {mocked} en modo simulado (IA offline)")

    # Guardar resultados como JSON
    out = test_dir / "test_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Resultados guardados en: {out}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
