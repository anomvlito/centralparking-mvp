from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import io
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HAS_ML = False
alpr = None

try:
    from fast_alpr import ALPR
    import cv2
    import numpy as np
    # Initialize the ALPR
    alpr = ALPR(
        detector_model="yolo-v9-t-384-license-plate-end2end",
        ocr_model="cct-xs-v2-global-model",
    )
    HAS_ML = True
except Exception as e:
    print(f"Machine learning dependencies not available or failed to load: {e}")

@app.post("/api/detect")
async def detect(image: UploadFile = File(...)):
    if not HAS_ML:
        # Mock detection
        num = random.randint(1000, 9999)
        return {"plate": f"SIM-{num}", "confidence": 0.95, "mocked": True}
        
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        results = alpr.predict(img)
        
        if not results or len(results) == 0:
            return {"error": "No plate detected", "plate": None}
            
        # Extract the highest confidence plate or the first one
        best_plate = results[-1]
        
        plate_text = getattr(best_plate, 'ocr', None)
        if hasattr(plate_text, 'text'):
            plate_text = plate_text.text
        elif hasattr(best_plate, 'text'):
            plate_text = best_plate.text
        else:
            # Fallback string manipulation if standard fails
            plate_text = str(best_plate)
            
        return {
            "plate": str(plate_text),
            "confidence": getattr(best_plate, 'confidence', 1.0),
            "mocked": False
        }
    except Exception as e:
        return {"error": str(e), "plate": None, "mocked": False}
