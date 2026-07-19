import os
import cv2
import csv
import datetime
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from api.database import now_cl, _levenshtein
from typing import Dict, List, Optional
import shutil

# Importing from the existing detecting module
from api.detect import alpr, HAS_ML, extract_best_plate, strategy_clahe

router = APIRouter()

# --- Configuration ---
VIDEO_UPLOAD_DIR = "uploaded_videos"
VIDEO_RESULTS_DIR = "video_results"
PROCESS_EVERY_N_FRAMES = 5   # Process 1 frame every 5 frames (~6fps for 30fps video)
# Umbral de fusión propio del clustering intra-video: más laxo que
# database.PLATE_FUZZY_MAX_DISTANCE (2, pensado para corregir 1 dígito mal
# leído contra una sesión YA activa). Acá el ruido es peor — el mismo plate
# físico puede leerse con 3+ caracteres distintos entre frames consecutivos
# de un mismo auto (visto en producción: 17 variantes de una sola patente
# real en un video de salida). distance=3 fusiona esas 17 en 1 sin fusionar
# una lectura real no relacionada (probado contra el caso real).
VIDEO_CLUSTER_MAX_DISTANCE = int(os.environ.get("VIDEO_CLUSTER_MAX_DISTANCE", "3"))

for directory in [VIDEO_UPLOAD_DIR, VIDEO_RESULTS_DIR]:
    os.makedirs(directory, exist_ok=True)


def _process_video_task(video_path: str, result_csv_path: str, auto_register: bool = True):
    """
    Background task to process a video, extract frames, skip them,
    and run the optimized ALPR pipeline.

    auto_register=False (usado por el flujo FTP) evita registrar el vehículo
    directamente acá y en cambio persiste el frame confirmado a disco para que
    el llamador lo pase por _handle_auto_detection y compita por mejor calidad
    en staging (igual que las fotos). auto_register=True (endpoint standalone
    /api/video/upload) mantiene el comportamiento previo.
    """
    if not HAS_ML:
        print("video skipped: AI offline")
        return

    print(f"video start: {video_path}")
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"video error: cannot open {video_path}")
        return

    frame_count = 0
    # Un video contiene muchos frames del mismo vehículo, y el ángulo/blur/luz
    # cambia frame a frame — el OCR no falla "limpio", lee texto ligeramente
    # distinto en casi cada frame (ej. HHB224, HBZ24, KHBZ2, MHBZ24... todas
    # la misma patente física). Comparar por texto exacto trataba cada
    # variante como un vehículo nuevo y generaba una ENTRY por variante.
    # Acá se agrupan por distancia de edición (mismo criterio que
    # database.find_similar_active_session) y solo se emite un representante
    # por cluster: la lectura de mayor confianza.
    clusters: List[dict] = []  # [{"plate", "confidence", "frame"}]

    # Motion detection background subtractor (Tier 2 filtering)
    back_sub = cv2.createBackgroundSubtractorMOG2(history=50, varThreshold=50, detectShadows=False)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        # Tier 1: Skip frames aggressively to save CPU/GPU
        if frame_count % PROCESS_EVERY_N_FRAMES != 0:
            continue

        # Tier 2: Motion Detection (Is there a car moving?)
        fg_mask = back_sub.apply(frame)
        motion_ratio = cv2.countNonZero(fg_mask) / (frame.shape[0] * frame.shape[1])

        # If less than 1% of the pixels moved, assume it is empty or static
        if motion_ratio < 0.01:
            continue

        # Tier 3: Multi-Strategy ALPR Detection (same as photos)
        try:
            # Import and use multi-strategy like photos do
            from api.detect import run_multi_strategy
            candidate = run_multi_strategy(frame)

            if not candidate:
                continue

            plate_text = candidate["plate"]
            confidence = candidate["confidence"]

            best_cluster = None
            best_dist = VIDEO_CLUSTER_MAX_DISTANCE + 1
            for cluster in clusters:
                dist = _levenshtein(plate_text, cluster["plate"])
                if dist <= VIDEO_CLUSTER_MAX_DISTANCE and dist < best_dist:
                    best_cluster, best_dist = cluster, dist

            if best_cluster is None:
                clusters.append({"plate": plate_text, "confidence": confidence, "frame": frame.copy()})
                print(f"video candidate: {plate_text} conf={confidence:.2f} (cluster nuevo)")
            elif confidence > best_cluster["confidence"]:
                best_cluster["plate"] = plate_text
                best_cluster["confidence"] = confidence
                best_cluster["frame"] = frame.copy()

        except Exception as e:
            print(f"Error processing frame {frame_count}: {e}")

    cap.release()
    print(f"video done: {len(clusters)} vehículo(s) detectado(s) (de {frame_count} frames)")

    detected_plates_history = []  # One row per cluster (vehículo real)
    for cluster in clusters:
        timestamp = now_cl().strftime("%Y-%m-%d %H:%M:%S")
        plate_text = cluster["plate"]
        frame_path = ""
        if not auto_register:
            # Persistir el frame para que compita por calidad en
            # staging — solo cuando el llamador se hace cargo del
            # registro (si no, quedaría huérfano en disco).
            candidate_path = f"{result_csv_path}.{plate_text}.jpg"
            try:
                cv2.imwrite(candidate_path, cluster["frame"])
                frame_path = candidate_path
            except Exception:
                frame_path = ""
        detected_plates_history.append(
            [timestamp, plate_text, f"{cluster['confidence']:.2f}", frame_path]
        )

    # Register detections in BD (respecting deduplication) — solo si nadie más
    # se hace cargo del registro (ver auto_register en el docstring).
    registered = 0
    if auto_register:
        from api.database import upsert_vehicle
        for timestamp_str, plate_text, conf_str, _frame_path in detected_plates_history:
            try:
                # upsert_vehicle deduplica de forma atómica incluso si dos workers
                # procesan la misma patente al mismo tiempo.
                from datetime import datetime
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                entry_ms = dt.timestamp() * 1000
                if upsert_vehicle(plate_text, entry_ms, source='video_auto'):
                    registered += 1
                    print(f"video registered: {plate_text} (source: video)")
                else:
                    print(f"video skipped: {plate_text} (already registered)")
            except Exception as e:
                print(f"video error registering {plate_text}: {e}")

    # Write results to CSV
    with open(result_csv_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Plate", "Confidence", "FramePath"])
        writer.writerows(detected_plates_history)

    print(f"video results: {result_csv_path} — registered {registered}/{len(detected_plates_history)}")


@router.post("/api/video/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Uploads a video and schedules it for background processing.
    """
    if not file.filename.endswith(('.mp4', '.avi', '.mov')):
        raise HTTPException(status_code=400, detail="Invalid video format.")

    timestamp = now_cl().strftime("%Y%md_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
    
    video_path = os.path.join(VIDEO_UPLOAD_DIR, safe_filename)
    result_csv_path = os.path.join(VIDEO_RESULTS_DIR, f"{safe_filename}.csv")

    # Save the uploaded file
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Add processing to background tasks
    background_tasks.add_task(_process_video_task, video_path, result_csv_path)

    return {
        "status": "processing",
        "video_id": safe_filename,
        "message": "Video uploaded successfully. Processing in background."
    }

@router.get("/api/video/results/{video_id}")
async def get_video_results(video_id: str):
    """
    Fetch the results of a processed video.
    """
    result_csv_path = os.path.join(VIDEO_RESULTS_DIR, f"{video_id}.csv")
    
    if not os.path.exists(result_csv_path):
        # Check if the video is still processing (exists in upload dir but no result yet)
        video_path = os.path.join(VIDEO_UPLOAD_DIR, video_id)
        if os.path.exists(video_path):
            return {"status": "processing", "data": []}
        raise HTTPException(status_code=404, detail="Results not found.")

    results = []
    with open(result_csv_path, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
            
    return {"status": "completed", "data": results}
