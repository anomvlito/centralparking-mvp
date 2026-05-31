# Hoja de ruta: Detección de dirección vehicular con modelo ML

**Estado actual:** Implementado — `DirectionTracker` en `api/ftp_handler.py`  
usando heurística de crecimiento de bounding box (Opción A).

**Este documento:** Plan para migrar a modelo ML si la heurística no alcanza.

---

## Por qué la heurística puede no ser suficiente

La heurística de bbox_width funciona bien cuando:
- La cámara está alineada con el eje de entrada/salida
- Hay ≥2 capturas de la misma ráfaga FTP (< 15s entre fotos)
- El auto pasa relativamente lento

Falla cuando:
- Solo llega 1 foto por auto (sin referencia anterior)
- El auto pasa muy rápido (cambio imperceptible entre fotos)
- La cámara está en ángulo oblicuo al eje de movimiento

---

## Opción C: Clasificador front/rear con YOLOv8 + ResNet

### Arquitectura propuesta

```
FTP Image
    ↓
[Stage 1] YOLOv8n vehicle detection
    → bounding box del vehículo completo (no solo la patente)
    → crop del vehículo de la imagen
    ↓
[Stage 2] Orientation classifier (ResNet18 fine-tuned)
    → clases: FRONT | REAR | SIDE_L | SIDE_R
    → confianza por clase
    ↓
direction_signal: APPROACHING (FRONT) | DEPARTING (REAR) | UNKNOWN (SIDE)
```

### Modelos pre-entrenados disponibles

#### 1. VehicleNet (recomendado para primer intento)
- **Repo:** https://github.com/zheng-lab-ece/VehicleNet
- **Dataset:** VeRi-776 + VehicleID (ground-level, múltiples ángulos)
- **Output:** embeddings de orientación + clasificación front/rear/side
- **Formato:** PyTorch → exportable a ONNX
- **Licencia:** MIT

#### 2. OpenVINO Vehicle Attribute Recognition
- **Repo:** https://github.com/openvinotoolkit/open_model_zoo
- **Modelo:** `vehicle-attributes-recognition-barrier-0042`
- **Output:** tipo (car/van/truck) + color + orientación (4 ángulos: front/side/rear)
- **Formato:** ONNX, mismo pipeline que fast-alpr
- **Descarga:**
  ```bash
  omz_downloader --name vehicle-attributes-recognition-barrier-0042
  ```
- **Licencia:** Apache 2.0

#### 3. CLIP zero-shot (sin fine-tuning)
- **Repo:** https://github.com/openai/CLIP
- **Uso:**
  ```python
  import clip
  model, preprocess = clip.load("ViT-B/32")
  texts = clip.tokenize(["front view of car", "rear view of car", "side view of car"])
  with torch.no_grad():
      image_features = model.encode_image(preprocessed_crop)
      text_features  = model.encode_text(texts)
      similarity = (image_features @ text_features.T).softmax(dim=-1)
  direction = ["FRONT", "REAR", "SIDE"][similarity.argmax()]
  ```
- **Ventaja:** sin fine-tuning, funciona out-of-the-box
- **Desventaja:** más pesado (~150MB), latencia mayor

### Fine-tuning con datos propios (mejor resultado a largo plazo)

Con ~200 fotos etiquetadas de las capturas del estacionamiento:

```bash
# 1. Etiquetar fotos con Label Studio o Roboflow
#    Clases: front / rear / side

# 2. Fine-tune ResNet18 (liviano, ~45MB)
pip install timm
python train_orientation.py \
  --data ./labeled_photos \
  --model resnet18 \
  --epochs 20 \
  --output orientation_model.pt

# 3. Exportar a ONNX
python export_onnx.py --model orientation_model.pt
```

El pipeline de inferencia quedaría:
```python
# En ftp_handler.py, reemplaza DirectionTracker
class OrientationClassifier:
    def __init__(self, onnx_path: str):
        self.session = onnxruntime.InferenceSession(onnx_path)

    def predict(self, vehicle_crop: np.ndarray) -> tuple[str, float]:
        # preprocess → run → return (direction, confidence)
        ...
```

### Integración en el pipeline

El cambio en `_handle_auto_detection` sería mínimo:

```python
# Reemplazar:
direction = _direction.record(plate, bbox_width)

# Por:
vehicle_crop = _crop_vehicle(img, vehicle_bbox)  # necesita Stage 1
direction, dir_conf = _orientation_model.predict(vehicle_crop)
if dir_conf < 0.7:
    direction = "UNKNOWN"  # no confiar si la confianza es baja
```

### Métricas de evaluación

Para decidir si el modelo es mejor que la heurística:

| Métrica | Heurística bbox | Meta con modelo |
|---------|----------------|----------------|
| Precisión APPROACHING | ~70%* | >90% |
| Precisión DEPARTING | ~65%* | >85% |
| Cobertura (no UNKNOWN) | ~40%* | >80% |
| Latencia por imagen | <1ms | <50ms |

*Estimado — validar con datos reales del estacionamiento.

### Cuándo migrar

Migrar de heurística a modelo cuando:
1. El porcentaje de `SKIP_DEPARTING` en audit_log sea > 20% (muchos falsos negativos)
2. O las salidas fantasmas (EXIT inmediato de sesiones stale) sigan siendo frecuentes
3. O cuando tengan ≥200 fotos etiquetadas del propio estacionamiento

---

## Código de referencia para Stage 1 (detección vehicular)

```python
# Agregar en detect.py o ftp_handler.py
from ultralytics import YOLO

_vehicle_detector = None

def get_vehicle_detector():
    global _vehicle_detector
    if _vehicle_detector is None:
        _vehicle_detector = YOLO("yolov8n.pt")  # ~6MB, detecta autos, camiones, etc.
    return _vehicle_detector

def detect_vehicle_bbox(img: np.ndarray) -> Optional[tuple[int,int,int,int]]:
    """
    Retorna (x1, y1, x2, y2) del vehículo más prominente en la imagen.
    Clases COCO que nos interesan: 2=car, 5=bus, 7=truck
    """
    model = get_vehicle_detector()
    results = model(img, classes=[2, 5, 7], conf=0.4, verbose=False)
    boxes = results[0].boxes
    if not len(boxes):
        return None
    # Tomar el box con mayor área (más cercano / más visible)
    areas = [(b.xyxy[0][2]-b.xyxy[0][0]) * (b.xyxy[0][3]-b.xyxy[0][1]) for b in boxes]
    best_idx = int(np.argmax(areas))
    x1, y1, x2, y2 = boxes[best_idx].xyxy[0].int().tolist()
    return x1, y1, x2, y2
```

---

_Documento creado: 2026-05-31_  
_Implementación actual: `api/ftp_handler.py::DirectionTracker`_
