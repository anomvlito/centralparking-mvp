import json
import os
import datetime
import random
import cv2
import numpy as np
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

DB_FILE = "parking_db.json"
HISTORY_FILE = "history.csv"

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

# ML Engine
HAS_ML = False
alpr = None
try:
    from fast_alpr import ALPR
    alpr = ALPR(detector_model="yolo-v9-t-384-license-plate-end2end", ocr_model="cct-xs-v2-global-model")
    HAS_ML = True
    print("AI Ready")
except Exception as e:
    print(f"AI Offline: {e}")

class CarEntry(BaseModel):
    plate: str
    isEvent: bool = False
    eventFee: Optional[float] = None

@app.get("/api/cars")
async def get_cars(): return load_db()

@app.get("/api/history")
async def get_history():
    import csv
    if not os.path.exists(HISTORY_FILE): return []
    rows = []
    with open(HISTORY_FILE, mode='r') as f:
        reader = csv.reader(f)
        next(reader, None) # Skip header
        for row in reader:
            if row: rows.append(row)
    return rows[-50:][::-1]

@app.post("/api/clear-history")
async def clear_history():
    with open(HISTORY_FILE, mode='w', newline='') as f:
        import csv
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Plate", "Action", "Status", "Fee", "Confidence"])
    return {"status": "history cleared"}

@app.get("/api/stats")
async def get_stats():
    import csv
    if not os.path.exists(HISTORY_FILE): return {"today_income": 0, "today_entries": 0, "today_exits": 0, "parked_now": len(load_db())}
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    income, entries, exits = 0, 0, 0
    with open(HISTORY_FILE, mode='r') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3 or not row[0].startswith(today): continue
            action = row[2]
            if action == "ENTRY": entries += 1
            elif action == "EXIT":
                exits += 1
                try: income += float(row[4])
                except: pass
    return {"today_income": income, "today_entries": entries, "today_exits": exits, "parked_now": len(load_db())}

@app.post("/api/detect")
async def detect(image: UploadFile = File(...)):
    if not HAS_ML:
        plate = f"SIM-{random.randint(1000,9999)}"
        log_to_csv(plate, "DETECTION", "MOCKED")
        return {"plate": plate, "mocked": True, "confidence": 0.9}
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        results = alpr.predict(img)
        if not results:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            results = alpr.predict(cv2.cvtColor(cv2.merge((clahe.apply(l),a,b)), cv2.COLOR_LAB2BGR))
        if not results: return {"plate": None}
        best = results[0]
        p_text = getattr(best, 'ocr', str(best))
        if hasattr(p_text, 'text'): p_text = p_text.text
        conf = getattr(best, 'confidence', 1.0)
        log_to_csv(str(p_text), "DETECTION", "REAL", conf=conf)
        return {"plate": str(p_text), "confidence": conf, "mocked": False}
    except: return {"plate": None}

@app.post("/api/entry")
async def entry(e: CarEntry):
    db = load_db()
    db[e.plate] = {"plate": e.plate, "entryTime": datetime.datetime.now().timestamp() * 1000, "isEvent": e.isEvent, "eventFee": e.eventFee}
    save_db(db)
    log_to_csv(e.plate, "ENTRY")
    return db[e.plate]

@app.post("/api/exit/{plate}")
async def exit_car(plate: str, fee: float = 0):
    db = load_db()
    if plate in db:
        car = db.pop(plate)
        save_db(db)
        log_to_csv(plate, "EXIT", fee=fee)
        return {"status": "ok"}
    raise HTTPException(status_code=404)

@app.delete("/api/cars/{plate}")
async def delete_car(plate: str):
    db = load_db()
    if plate in db:
        del db[car := plate]
        save_db(db)
        log_to_csv(plate, "VOID")
    return {"status": "voided"}
