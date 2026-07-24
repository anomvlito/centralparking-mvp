"""Caso de uso de detección conservando la fachada ALPR existente."""

import random

import cv2
import numpy as np

from api.database import log_to_db


def detect_image(contents: bytes) -> dict:
    # Import tardío: la fachada se conserva hasta completar la extracción del
    # motor ALPR, sin hacer que este servicio dependa de FastAPI.
    from api.detect import HAS_ML, run_multi_strategy

    if not HAS_ML:
        plate = f"SIM{random.randint(1000, 9999)}"
        log_to_db(plate, "DETECTION", "MOCKED")
        return {
            "plate": plate,
            "mocked": True,
            "confidence": 0.9,
            "strategy": "mock",
        }

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return {"plate": None, "error": "image decode failed"}

    result = run_multi_strategy(img)
    if not result:
        return {"plate": None, "error": "no_detection"}

    log_to_db(
        result["plate"],
        "DETECTION",
        "REAL",
        conf=result["confidence"],
    )
    return {
        "plate": result["plate"],
        "confidence": result["confidence"],
        "strategy": result["strategy"],
        "mocked": False,
    }
