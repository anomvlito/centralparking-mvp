# ADR-004 — Filtro de vehículo con modelo COCO genérico (YOLOX-Nano, ONNX), apagado por defecto

**Estado:** `aceptada`
**Fecha:** 2026-08-06
**Creado por:** Francisco (vía sesión asistida)
**HUs relacionadas:** ninguna — feature técnica, ver
[filtro-vehiculo-pre-alpr.md](../features/backlog/filtro-vehiculo-pre-alpr.md)

## Contexto

`/ftp/revisar` acumula toda imagen o frame de video donde el pipeline ALPR
(`api/detect.py::run_multi_strategy`, 12 estrategias con
`yolo-v9-t-384-license-plate-end2end`) corrió y no encontró patente — 30G en
12 días medidos en esta sesión. Parte de esas capturas no contiene ningún
vehículo (disparos falsos de la cámara). Se busca un filtro barato que
corra antes del pipeline de patente y descarte esos casos, sin agregar
dependencias pesadas (el VPS de producción tiene 2 vCPU, sin GPU).

## Decisión

Usar **YOLOX-Nano** (Megvii-BaseDetection, Apache 2.0), exportado a ONNX
oficial (`yolox_nano.onnx`, release `0.1.1rc0`, ~3.6MB), corrido con
`onnxruntime` — dependencia que **ya está instalada** en el proyecto (la usa
`fast-alpr`/`open-image-models` para el modelo de patente). Detección de
vehículo simplificada a `objectness × score de clase` (sin decodificar cajas
ni NMS) para las clases COCO `car`(2)/`motorcycle`(3)/`bus`(5)/`truck`(7),
suficiente para la decisión binaria "¿hay vehículo?" que este filtro
necesita.

Rollout con flags de apagado seguro, mismo patrón que ADR-001 usó para
`DirectionTracker` (`api/core/config.py::DirectionSettings`):
`VehicleFilterSettings(enabled, shadow_mode, conf_threshold)`. Arranca
`enabled=false`; con `enabled=true` arranca además en `shadow_mode=true`
(audita la decisión, no descarta nada). Solo con `shadow_mode=false` el
filtro efectivamente evita correr ALPR y archivar en `/ftp/revisar`.

## Alternativas consideradas

1. **YOLO26n (Ultralytics, enero 2026)** — el más rápido en CPU según
   benchmarks propios de Ultralytics (~43% más rápido que YOLO11n). Descartada
   por licencia: Ultralytics distribuye YOLO26 bajo AGPL-3.0, con licencia
   Enterprise de pago para uso comercial cerrado — no compatible con este
   producto sin esa licencia.
2. **Reusar `open_image_models.detection.core.yolo_v9`** (el wrapper que ya
   usa el modelo de patente). Descartada: ese wrapper está atado al formato
   de salida end2end específico del modelo de patente (decodificación e
   umbral propios), no a un detector COCO genérico — habría que reescribirlo
   igual, sin ganar nada sobre un wrapper propio directo con
   `onnxruntime.InferenceSession`.
3. **No filtrar, solo confiar en el gate de movimiento existente en video**
   (`cv2.createBackgroundSubtractorMOG2`). Descartada como solución
   suficiente: "algo se movió" no es "hay un vehículo" (viento, sombra,
   personas), y no cubre el flujo de fotos, que no tiene ningún gate hoy.

## Consecuencias

- Nueva dependencia binaria: un archivo `.onnx` de ~3.6MB, descargado una
  vez desde el release oficial del repo (Apache 2.0), no commiteado al
  repositorio — cacheado en disco igual que el patrón ya usado por
  `open_image_models`.
- Riesgo real de falso negativo (vehículo real no detectado, evidencia
  descartada silenciosamente) si se activa el descarte sin calibrar. Se
  mitiga arrancando en `shadow_mode` y exigiendo autorización explícita
  antes de pasar a descarte real — ver "Trabajo futuro".
- No cambia el contrato de `DetectionEvent`/`detection_log`/
  `staging_detections`: el filtro decide si una captura entra al pipeline,
  no cómo se registra una vez adentro.
- No reemplaza ni ajusta el modelo de patente.

## Trabajo futuro

- Correr en `shadow_mode` contra tráfico real y medir la tasa de falsos
  negativos (vehículos confirmados que el filtro hubiera descartado) antes
  de autorizar `shadow_mode=false` en producción.
- Si la tasa de acierto es alta y sostenida, evaluar aplicar el mismo
  filtro también como señal de calidad dentro de `staging_submit()` (hoy
  solo decide sí/no antes de ALPR).

Cualquier ampliación de alcance más allá de lo decidido acá requiere su
propia HU o una revisión explícita de esta ADR.

## Referencias

- `api/vehicle_detector.py` — wrapper ONNX del filtro.
- `api/core/config.py::VehicleFilterSettings` — configuración y flags.
- `api/ftp_handler.py::ftp_image()`, `api/video_processor.py::_process_video_task()` —
  puntos de integración.
- [ADR-001 — Reactivar DirectionTracker acotado](./ADR-001-reactivar-direction-tracker-acotado.md) —
  mismo patrón de rollout seguro (flag apagado + modo observación primero)
  para un clasificador probabilístico nuevo.
