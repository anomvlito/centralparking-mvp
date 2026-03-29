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

def log_to_csv(plate, action, status="REAL", fee=0):
    import csv
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, plate, action, status, fee])

# ML Loading
HAS_ML = False
alpr = None
try:
    from fast_alpr import ALPR
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
async def register_exit(plate: str, fee: float = 0):
    db = load_db()
    if plate not in db:
        raise HTTPException(status_code=404, detail="Car not found")
    
    car = db.pop(plate)
    save_db(db)
    log_to_csv(plate, "EXIT", fee=fee)
    return {"message": "Exit registered", "car": car}

@app.delete("/api/cars/{plate}")
async def delete_car(plate: str):
    db = load_db()
    if plate not in db:
        raise HTTPException(status_code=404, detail="Car not found")
    
    del db[plate]
    save_db(db)
    log_to_csv(plate, "VOID")
    return {"message": "Car record removed (Voided)"}

@app.get("/api/stats")
async def get_stats():
    import csv
    if not os.path.exists(HISTORY_FILE):
        return {"today_income": 0, "today_entries": 0, "today_exits": 0, "parked_now": len(load_db())}
    
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    income = 0
    entries = 0
    exits = 0
    
    with open(HISTORY_FILE, mode='r') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3: continue
            ts, plate, action = row[0], row[1], row[2]
            if ts.startswith(today):
                if action == "ENTRY": entries += 1
                elif action == "EXIT": 
                    exits += 1
                    if len(row) >= 5:
                        try: income += float(row[4])
                        except: pass
    
    return {
        "today_income": income,
        "today_entries": entries,
        "today_exits": exits,
        "parked_now": len(load_db())
    }
