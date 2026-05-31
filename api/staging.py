"""
staging.py — Central Parking MVP
Buffer de staging con deduplicación y quality scoring.

Flujo:
  FTP image → calculate_quality() → staging_submit() → [2 min TTL]
           → background loop promueve 'pending' expirados → ENTRY en parking

El EXIT sigue siendo inmediato (bypass staging).
Frontend no requiere cambios: /api/history y /api/cars solo ven datos aprobados.
"""

import asyncio
import json
import datetime
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from api.database import _db, now_cl, upsert_vehicle, vehicle_exists, log_to_db

router = APIRouter()

STAGING_TTL_SECONDS = 120


# ─────────────────────── Quality scoring ────────────────────────────────────

def calculate_quality_score(img: np.ndarray, plate: str, confidence: float) -> dict:
    """
    Calcula métricas de calidad de imagen.
    Fórmula: (sharpness×0.4) + (contrast×0.3) + (brightness×0.2) + (ocr_clarity×0.1)
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

    # Sharpness: varianza del Laplaciano (1000 ≈ imagen muy nítida)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness = min(lap_var / 1000.0, 1.0)

    # Contrast: desviación estándar de píxeles (80 ≈ buen contraste)
    _, std = cv2.meanStdDev(gray)
    contrast = min(float(std[0][0]) / 80.0, 1.0)

    # Brightness: qué tan cerca del punto medio (128/255 ≈ exposición ideal)
    mean_val = float(cv2.mean(gray)[0]) / 255.0
    brightness = 1.0 - abs(mean_val - 0.5) * 2.0

    # OCR clarity: proxy via validez de la cadena + confianza
    clean = plate.replace("-", "").replace(" ", "")
    valid_plate = len(clean) >= 5 and clean.isalnum()
    ocr_clarity = min(confidence * (1.2 if valid_plate else 0.7), 1.0)

    quality_score = (
        sharpness    * 0.4 +
        contrast     * 0.3 +
        brightness   * 0.2 +
        ocr_clarity  * 0.1
    )
    combined_score = confidence * 0.7 + quality_score * 0.3

    return {
        "quality_score":    round(quality_score,    4),
        "combined_score":   round(combined_score,   4),
        "sharpness":        round(sharpness,         4),
        "contrast_score":   round(contrast,          4),
        "brightness_score": round(brightness,        4),
        "ocr_clarity":      round(ocr_clarity,       4),
    }


# ─────────────────────── Core deduplication ─────────────────────────────────

def staging_submit(plate: str, confidence: float, quality: dict,
                   strategy: Optional[str] = None) -> dict:
    """
    Ingresa una detección al buffer.
    Retorna: {status: 'pending'|'rejected', action_taken, combined_score}
    """
    combined = quality["combined_score"]
    expires_at = now_cl() + datetime.timedelta(seconds=STAGING_TTL_SECONDS)

    with _db() as conn:
        with conn.cursor() as cur:
            # Buscar 'pending' activo para esta patente en la ventana
            cur.execute("""
                SELECT id, combined_score FROM staging_detections
                WHERE plate = %s AND status = 'pending' AND expires_at > now()
                ORDER BY combined_score DESC
                LIMIT 1
            """, (plate,))
            existing = cur.fetchone()

            if existing:
                if combined > float(existing["combined_score"]):
                    # Nuevo es mejor: rechazar el existente, insertar nuevo
                    cur.execute("""
                        UPDATE staging_detections
                        SET status = 'rejected',
                            rejection_reason = 'superseded_by_better_quality'
                        WHERE id = %s
                    """, (existing["id"],))
                    cur.execute("""
                        INSERT INTO staging_detections
                            (plate, confidence, quality_score, combined_score,
                             sharpness, contrast_score, brightness_score, ocr_clarity,
                             strategy, status, expires_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
                    """, (plate, confidence, quality["quality_score"], combined,
                          quality["sharpness"], quality["contrast_score"],
                          quality["brightness_score"], quality["ocr_clarity"],
                          strategy, expires_at))
                    _audit(plate, "SUPERSEDED",
                           {"old_score": float(existing["combined_score"]),
                            "new_score": combined})
                    return {"status": "pending", "action": "replaced_inferior",
                            "combined_score": combined}
                else:
                    # Nuevo es peor: rechazarlo
                    cur.execute("""
                        INSERT INTO staging_detections
                            (plate, confidence, quality_score, combined_score,
                             sharpness, contrast_score, brightness_score, ocr_clarity,
                             strategy, status, rejection_reason, expires_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'rejected','inferior_quality',%s)
                    """, (plate, confidence, quality["quality_score"], combined,
                          quality["sharpness"], quality["contrast_score"],
                          quality["brightness_score"], quality["ocr_clarity"],
                          strategy, expires_at))
                    return {"status": "rejected", "action": "inferior_quality",
                            "combined_score": combined,
                            "best_score": float(existing["combined_score"])}
            else:
                # Primera detección en la ventana: insertar como pending
                cur.execute("""
                    INSERT INTO staging_detections
                        (plate, confidence, quality_score, combined_score,
                         sharpness, contrast_score, brightness_score, ocr_clarity,
                         strategy, status, expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
                """, (plate, confidence, quality["quality_score"], combined,
                      quality["sharpness"], quality["contrast_score"],
                      quality["brightness_score"], quality["ocr_clarity"],
                      strategy, expires_at))
                return {"status": "pending", "action": "first_in_window",
                        "combined_score": combined}


def staging_promote_expired():
    """
    Promueve entradas 'pending' expiradas → ENTRY en parking.
    Se llama periódicamente desde el background loop.
    """
    promoted = 0
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, plate, confidence, combined_score, strategy, image_path
                FROM staging_detections
                WHERE status = 'pending' AND expires_at <= now()
            """)
            expired = cur.fetchall()

            for row in expired:
                plate = row["plate"]
                cur.execute(
                    "UPDATE staging_detections SET status = 'approved' WHERE id = %s",
                    (row["id"],)
                )

                if vehicle_exists(plate):
                    _audit(plate, "PROMOTED_SKIP", {"reason": "already_in_parking"})
                    continue

                upsert_vehicle(plate, now_cl().timestamp() * 1000)
                log_to_db(plate, "ENTRY", status="STAGING_AUTO",
                          conf=float(row["combined_score"]),
                          image_path=row["image_path"])
                _audit(plate, "PROMOTED",
                       {"combined_score": float(row["combined_score"]),
                        "strategy": row["strategy"]})
                promoted += 1

    return promoted


def staging_cleanup_old():
    """Elimina registros de staging con más de 24h para no acumular basura."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM staging_detections
                WHERE detected_at < now() - INTERVAL '24 hours'
            """)


def _audit(plate: Optional[str], event_type: str, details: dict):
    """Registra un evento en audit_log dentro de la misma sesión."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_log (plate, event_type, details)
                VALUES (%s, %s, %s)
            """, (plate, event_type, json.dumps(details)))


# ─────────────────────── Background loop ────────────────────────────────────

async def staging_loop():
    """Corre indefinidamente, promoviendo staging expirado cada 30 segundos."""
    while True:
        await asyncio.sleep(30)
        try:
            promoted = staging_promote_expired()
            if promoted:
                print(f"[staging] Promovidos {promoted} vehículo(s) a ENTRY")
            staging_cleanup_old()
        except Exception as e:
            print(f"[staging] Error en loop: {e}")


# ─────────────────────── Endpoints ──────────────────────────────────────────

class DeduplicateRequest(BaseModel):
    plate: str
    confidence: float
    strategy: Optional[str] = None
    quality_score: Optional[float] = None
    sharpness: Optional[float] = None
    contrast_score: Optional[float] = None
    brightness_score: Optional[float] = None
    ocr_clarity: Optional[float] = None


@router.post("/api/staging/deduplicate")
async def api_staging_deduplicate(req: DeduplicateRequest):
    """Procesa una detección contra el buffer de staging."""
    quality = {
        "quality_score":    req.quality_score    or req.confidence,
        "combined_score":   round(req.confidence * 0.7 + (req.quality_score or req.confidence) * 0.3, 4),
        "sharpness":        req.sharpness        or 0.5,
        "contrast_score":   req.contrast_score   or 0.5,
        "brightness_score": req.brightness_score or 0.5,
        "ocr_clarity":      req.ocr_clarity      or req.confidence,
    }
    return staging_submit(req.plate, req.confidence, quality, req.strategy)


@router.get("/api/staging/status")
async def api_staging_status(plate: str):
    """Estado actual de una patente en el buffer de staging."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, status, combined_score, detected_at, expires_at,
                       rejection_reason
                FROM staging_detections
                WHERE plate = %s
                ORDER BY detected_at DESC
                LIMIT 5
            """, (plate,))
            rows = cur.fetchall()
    return {
        "plate": plate,
        "entries": [
            {
                "id":               r["id"],
                "status":           r["status"],
                "combined_score":   float(r["combined_score"]),
                "detected_at":      r["detected_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at":       r["expires_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "rejection_reason": r["rejection_reason"],
            }
            for r in rows
        ],
    }


class SetImageRequest(BaseModel):
    plate: str
    image_path: str


@router.post("/api/staging/set-image")
async def api_staging_set_image(req: SetImageRequest):
    """Vincula la imagen archivada al registro de staging más reciente de la patente."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE staging_detections SET image_path = %s
                WHERE plate = %s AND status = 'pending'
                  AND expires_at > now()
                ORDER BY detected_at DESC
                LIMIT 1
            """, (req.image_path, req.plate))
    return {"status": "ok"}


class FeedbackRequest(BaseModel):
    plate: str
    issue: str
    details: Optional[str] = None


@router.post("/api/audit/feedback")
async def api_audit_feedback(req: FeedbackRequest):
    """Frontend reporta un problema con una detección."""
    _audit(req.plate, "FEEDBACK", {"issue": req.issue, "details": req.details})
    return {"status": "ok"}


@router.get("/api/audit/log")
async def api_audit_log(date: str = None, limit: int = 100):
    """Historial de eventos de staging y feedback."""
    with _db() as conn:
        with conn.cursor() as cur:
            if date:
                cur.execute("""
                    SELECT logged_at, plate, event_type, details
                    FROM audit_log
                    WHERE logged_at::date = %s::date
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (date, limit))
            else:
                cur.execute("""
                    SELECT logged_at, plate, event_type, details
                    FROM audit_log
                    ORDER BY logged_at DESC
                    LIMIT %s
                """, (limit,))
            rows = cur.fetchall()
    return {
        "events": [
            {
                "logged_at":  r["logged_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "plate":      r["plate"],
                "event_type": r["event_type"],
                "details":    r["details"],
            }
            for r in rows
        ]
    }
