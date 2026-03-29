import json
import os
import datetime
import random
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistence Files
DB_FILE = "parking_db.json"
HISTORY_FILE = "history.csv"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def log_to_csv(plate, action, status="REAL"):
    import csv
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, plate, action, status])

# ML Loading
HAS_ML = False
alpr = None
try:
    from fast_alpr import ALPR
    import cv2
    import numpy as np
    alpr = ALPR(
        detector_model="yolo-v9-t-384-license-plate-end2end",
        ocr_model="cct-xs-v2-global-model",
    )
    HAS_ML = True
    print("ML Models loaded successfully")
except Exception as e:
    print(f"Machine learning dependencies not available: {e}")

class CarEntry(BaseModel):
    plate: str
    isEvent: bool = False
    eventFee: Optional[float] = None

@app.get("/api/cars")
async def get_cars():
    return load_db()

@app.post("/api/detect")
async def detect(image: UploadFile = File(...)):
    if not HAS_ML:
        num = random.randint(1000, 9999)
        plate = f"SIM-{num}"
        log_to_csv(plate, "DETECTION", "MOCKED")
        return {"plate": plate, "confidence": 0.95, "mocked": True}
        
    try:
        contents = await image.read()
        import numpy as np
        import cv2
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        results = alpr.predict(img)
        
        if not results:
            return {"error": "No plate detected", "plate": None}
            
        best_plate = results[-1]
        plate_text = getattr(best_plate, 'ocr', str(best_plate))
        if hasattr(plate_text, 'text'):
            plate_text = plate_text.text
            
        log_to_csv(str(plate_text), "DETECTION", "REAL")
        return {
            "plate": str(plate_text),
            "confidence": getattr(best_plate, 'confidence', 1.0),
            "mocked": False
        }
    except Exception as e:
        return {"error": str(e), "plate": None}

@app.post("/api/entry")
async def register_entry(entry: CarEntry):
    db = load_db()
    if entry.plate in db:
        raise HTTPException(status_code=400, detail="Car already in parking")
    
    db[entry.plate] = {
        "plate": entry.plate,
        "entryTime": datetime.datetime.now().timestamp() * 1000,
        "isEvent": entry.isEvent,
        "eventFee": entry.eventFee
    }
    save_db(db)
    log_to_csv(entry.plate, "ENTRY")
    return db[entry.plate]

@app.post("/api/exit/{plate}")
async def register_exit(plate: str):
    db = load_db()
    if plate not in db:
        raise HTTPException(status_code=404, detail="Car not found")
    
    car = db.pop(plate)
    save_db(db)
    log_to_csv(plate, "EXIT")
    return {"message": "Exit registered", "car": car}
