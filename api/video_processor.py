import os
import cv2
import csv
import datetime
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from api.database import now_cl
from typing import Dict, List, Optional
import shutil

# Importing from the existing detecting module
from api.detect import alpr, HAS_ML, extract_best_plate, strategy_clahe

router = APIRouter()

# --- Configuration ---
VIDEO_UPLOAD_DIR = "uploaded_videos"
VIDEO_RESULTS_DIR = "video_results"
PROCESS_EVERY_N_FRAMES = 10  # Process 1 frame every 10 frames (~3fps for 30fps video)
CONSECUTIVE_FRAMES_FOR_CONFIRMATION = 2 # Plate must be seen X times to be valid

for directory in [VIDEO_UPLOAD_DIR, VIDEO_RESULTS_DIR]:
    os.makedirs(directory, exist_ok=True)


def _process_video_task(video_path: str, result_csv_path: str):
    """
    Background task to process a video, extract frames, skip them, 
    and run the optimized ALPR pipeline.
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
    detected_plates_history = []  # Log every valid detection
    recent_plates_buffer = {}     # To track consecutive detections (Plate -> Count)
    
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
        
        # If less than 2% of the pixels moved, assume it is empty or static
        if motion_ratio < 0.02:
            continue

        # Tier 3: Fast ALPR Detection
        try:
            # We use a fast strategy first (clahe is good for parking lighting)
            processed_frame = strategy_clahe(frame)
            results = alpr.predict(processed_frame)
            
            # Extract plate
            candidate = extract_best_plate(results, strategy_name="video_clahe")
            
            if candidate:
                plate_text = candidate["plate"]
                confidence = candidate["confidence"]

                # Add to recent buffer
                recent_plates_buffer[plate_text] = recent_plates_buffer.get(plate_text, 0) + 1

                # If we've seen this plate enough times, log it
                if recent_plates_buffer[plate_text] == CONSECUTIVE_FRAMES_FOR_CONFIRMATION:
                    timestamp = now_cl().strftime("%Y-%m-%d %H:%M:%S")
                    detected_plates_history.append([timestamp, plate_text, f"{confidence:.2f}"])
                    print(f"video detection: {plate_text} conf={confidence:.2f}")
            else:
                # Decay the buffer if no plate found (helps "forget" ghost reads)
                for key in list(recent_plates_buffer.keys()):
                    recent_plates_buffer[key] = max(0, recent_plates_buffer[key] - 1)

        except Exception as e:
            print(f"Error processing frame {frame_count}: {e}")

    cap.release()
    print(f"video done: {len(detected_plates_history)} plates detected")

    # Write results to CSV
    with open(result_csv_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Plate", "Confidence"])
        writer.writerows(detected_plates_history)
        
    print(f"video results: {result_csv_path}")


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
