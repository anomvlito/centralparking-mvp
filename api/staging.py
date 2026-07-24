"""
staging.py — Central Parking MVP
Buffer de staging con deduplicación y quality scoring.

Flujo:
  FTP image → calculate_quality() → staging_submit() → [2 min TTL]
           → background loop promueve 'pending' expirados → avistamiento
             logueado (detection_log, acción 'DETECTED')

2026-07-17: se desconectó la distinción automática entrada/salida
(DirectionTracker no era confiable — generaba tanto salidas falsas como
duplicados). Por ahora toda detección de patente pasa por el mismo buffer,
compite por la mejor foto dentro de una ventana corta, y se loguea como un
avistamiento plano — sin abrir ni cerrar parking_sessions. Esa apertura/
cierre sigue siendo manual (/api/entry, /api/exit). Ver
ftp_handler._handle_auto_detection para el detalle.
Frontend no requiere cambios: /api/history y /api/cars solo ven datos de
parking_sessions (entradas/salidas manuales), no de detection_log.
"""

import asyncio
import json
import os
import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from api.database import _db, now_cl, log_to_db, get_sightings
from api.services.direction import direction_service

_CL = ZoneInfo("America/Santiago")

router = APIRouter()

STAGING_TTL_SECONDS = 120
FTP_ARCHIVE_DIR = os.environ.get("FTP_ARCHIVE_DIR", "/ftp/historico")


# ─────────────────────── Persistencia de imagen ─────────────────────────────

def _save_detection_image(img: np.ndarray, plate: str) -> str:
    """Guarda la imagen en /ftp/historico solo para la detección que se conserva."""
    now_dt = now_cl()
    date_str = now_dt.strftime("%Y-%m-%d")
    time_str = now_dt.strftime("%H-%M-%S")
    folder = os.path.join(FTP_ARCHIVE_DIR, date_str)
    os.makedirs(folder, exist_ok=True)
    filename = f"{time_str}_{plate}_{date_str}.jpg"
    cv2.imwrite(os.path.join(folder, filename), img)
    return f"historico/{date_str}/{filename}"


def _delete_ftp_image(rel_path: str):
    """
    Borra una imagen previamente guardada al ser superada por una de mejor calidad.
    image_path siempre se guarda relativo a /ftp (mismo criterio que
    database.correct_session_plate y ftp_handler.serve_ftp_file).
    """
    full_path = os.path.realpath(os.path.join("/ftp", rel_path))
    if not full_path.startswith("/ftp" + os.sep):
        return
    try:
        os.remove(full_path)
    except OSError:
        pass


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
                   strategy: Optional[str] = None, img: Optional[np.ndarray] = None) -> dict:
    """
    Ingresa una detección al buffer.
    Solo se escribe una imagen a disco por patente/ventana: la de mejor
    combined_score vigente. Las detecciones inferiores nunca tocan el disco,
    y si una nueva mejor reemplaza a la guardada, la anterior se borra.
    Retorna: {status: 'pending'|'rejected', action_taken, combined_score, image_path}
    """
    combined = quality["combined_score"]
    expires_at = now_cl() + datetime.timedelta(seconds=STAGING_TTL_SECONDS)
    old_image_to_delete = None

    with _db() as conn:
        with conn.cursor() as cur:
            # Buscar 'pending' activo para esta patente en la ventana
            cur.execute("""
                SELECT id, combined_score, image_path FROM staging_detections
                WHERE plate = %s AND status = 'pending' AND expires_at > now()
                ORDER BY combined_score DESC
                LIMIT 1
            """, (plate,))
            existing = cur.fetchone()

            if existing:
                if combined > float(existing["combined_score"]):
                    # Nuevo es mejor: rechazar el existente, insertar nuevo
                    image_path = _save_detection_image(img, plate) if img is not None else None
                    old_image_to_delete = existing["image_path"]
                    cur.execute("""
                        UPDATE staging_detections
                        SET status = 'rejected',
                            rejection_reason = 'superseded_by_better_quality',
                            image_path = NULL
                        WHERE id = %s
                    """, (existing["id"],))
                    cur.execute("""
                        INSERT INTO staging_detections
                            (plate, confidence, quality_score, combined_score,
                             sharpness, contrast_score, brightness_score, ocr_clarity,
                             strategy, status, expires_at, image_path)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s)
                    """, (plate, confidence, quality["quality_score"], combined,
                          quality["sharpness"], quality["contrast_score"],
                          quality["brightness_score"], quality["ocr_clarity"],
                          strategy, expires_at, image_path))
                    _audit(plate, "SUPERSEDED",
                           {"old_score": float(existing["combined_score"]),
                            "new_score": combined})
                    result = {"status": "pending", "action": "replaced_inferior",
                              "combined_score": combined, "image_path": image_path}
                else:
                    # Nuevo es peor: rechazarlo, nunca se guarda en disco
                    cur.execute("""
                        INSERT INTO staging_detections
                            (plate, confidence, quality_score, combined_score,
                             sharpness, contrast_score, brightness_score, ocr_clarity,
                             strategy, status, rejection_reason, expires_at, image_path)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'rejected','inferior_quality',%s,NULL)
                    """, (plate, confidence, quality["quality_score"], combined,
                          quality["sharpness"], quality["contrast_score"],
                          quality["brightness_score"], quality["ocr_clarity"],
                          strategy, expires_at))
                    result = {"status": "rejected", "action": "inferior_quality",
                              "combined_score": combined,
                              "best_score": float(existing["combined_score"]),
                              "image_path": None}
            else:
                # Primera detección en la ventana: insertar como pending
                image_path = _save_detection_image(img, plate) if img is not None else None
                cur.execute("""
                    INSERT INTO staging_detections
                        (plate, confidence, quality_score, combined_score,
                         sharpness, contrast_score, brightness_score, ocr_clarity,
                         strategy, status, expires_at, image_path)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s)
                """, (plate, confidence, quality["quality_score"], combined,
                      quality["sharpness"], quality["contrast_score"],
                      quality["brightness_score"], quality["ocr_clarity"],
                      strategy, expires_at, image_path))
                result = {"status": "pending", "action": "first_in_window",
                          "combined_score": combined, "image_path": image_path}

    if old_image_to_delete:
        _delete_ftp_image(old_image_to_delete)
    return result


def staging_promote_expired():
    """
    Promueve entradas 'pending' expiradas a un avistamiento logueado
    (detection_log, acción 'DETECTED') — no decide automáticamente si es
    entrada o salida (ver nota al principio del archivo). No toca
    parking_sessions: esa apertura/cierre sigue siendo manual.
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

                # direction_service acumula una evaluación por patente en
                # memoria (misma clave usada al observar en
                # _handle_auto_detection); se consulta la última conocida en
                # vez de recalcular, ya que la ventana temporal del
                # clasificador (segundos) es independiente del TTL de
                # staging (minutos). Con DIRECTION_ENABLED=false o sin
                # evaluación previa, cae al mismo default 'UNKNOWN' de hoy.
                evaluation = direction_service.tracker.latest(plate)
                direction = evaluation.direction if evaluation else "UNKNOWN"

                log_to_db(plate, "DETECTED", status="STAGING_AUTO",
                          conf=float(row["combined_score"]),
                          image_path=row["image_path"],
                          direction=direction)
                _audit(plate, "DETECTED",
                       {"combined_score": float(row["combined_score"]),
                        "strategy": row["strategy"]})
                promoted += 1

    return promoted


def staging_cleanup_old():
    """Limpia staging viejo y cierra sesiones de parking abiertas > 20h."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM staging_detections
                WHERE detected_at < now() - INTERVAL '24 hours'
            """)
            # Cierre automático de sesiones que llevan más de 20h abiertas
            cur.execute("""
                UPDATE parking_sessions
                SET exit_time = entry_time + INTERVAL '20 hours',
                    status = 'AUTO_CLOSED',
                    updated_at = now()
                WHERE exit_time IS NULL
                  AND status NOT IN ('VOID', 'AUTO_CLOSED')
                  AND entry_time < now() - INTERVAL '20 hours'
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
                print(f"[staging] {promoted} avistamiento(s) registrado(s)")
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
                "detected_at":      r["detected_at"].astimezone(_CL).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at":       r["expires_at"].astimezone(_CL).strftime("%Y-%m-%d %H:%M:%S"),
                "rejection_reason": r["rejection_reason"],
            }
            for r in rows
        ],
    }


@router.get("/api/sightings")
async def api_sightings(limit: int = 50, date: str = None):
    """
    Feed de avistamientos: el más reciente por cada patente. Con `date`
    ("YYYY-MM-DD"), acotado a esa fecha (para el Historial por día).
    """
    return {"sightings": get_sightings(limit=min(limit, 500), date=date)}


@router.get("/api/sightings/{plate}")
async def api_sightings_by_plate(plate: str, limit: int = 20, near: str = None,
                                  window_minutes: int = 30, date: str = None):
    """
    Fotos de avistamientos de una patente puntual. Con `near` ("YYYY-MM-DD
    HH:MM:SS", hora de Chile), acota a fotos cercanas a ese momento. Con
    `date` ("YYYY-MM-DD"), acota a fotos de ese día. Sin ninguno, trae las
    más recientes sin acotar.
    """
    return {"sightings": get_sightings(limit=min(limit, 100), plate=plate,
                                        near=near, window_minutes=window_minutes, date=date)}


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
                "logged_at":  r["logged_at"].astimezone(_CL).strftime("%Y-%m-%d %H:%M:%S"),
                "plate":      r["plate"],
                "event_type": r["event_type"],
                "details":    r["details"],
            }
            for r in rows
        ]
    }
