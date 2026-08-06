# Feature — Filtro de vehículo antes del pipeline ALPR

**Etapa Project 4:** `In review` (sin tarjeta en Project 4 — no se creó
issue, ver "Issues" abajo; el estado refleja el PR abierto para esta
feature técnica)
**HUs relacionadas:** ninguna — trabajo técnico/infra (AGENTS.md: "trabajo
puramente técnico... no se fuerza a una HU"), no atado a la historia de un
actor.
**Issues:** pendiente (no se crea salvo pedido explícito del usuario).

## Problema

`/ftp/revisar` acumula toda imagen o frame de video donde el pipeline ALPR
(12 estrategias) corrió y no encontró patente — 30G en 12 días medidos en
esta sesión. Una parte de esas capturas no tiene ningún vehículo (disparos
falsos: viento, sombra, cambio de luz); además del espacio, se gasta CPU
(VPS de 2 vCPU sin GPU) corriendo el pipeline completo de patente sobre
frames que nunca tuvieron chance de contener una.

## Resultado esperado

Un filtro barato de "¿hay un vehículo acá?" corre antes del pipeline de
patente. Cuando está activo y no detecta vehículo, no corre ALPR sobre esa
captura ni la archiva en `/ftp/revisar`.

## Alcance

- Modelo de detección general (COCO: `car`/`truck`/`bus`/`motorcycle`) vía
  `onnxruntime` — YOLOX-Nano (Apache 2.0), sin agregar `torch`/`ultralytics`
  al proyecto.
- Config con flags de apagado seguro (`enabled`, `shadow_mode`), mismo
  patrón que `DirectionSettings` (`api/core/config.py`).
- Enganche en `/api/ftp/image` (fotos) y `_process_video_task` (video, Tier
  2/3) en `api/ftp_handler.py` / `api/video_processor.py`.
- `shadow_mode` (auditar sin descartar) como paso obligatorio antes de
  activar el descarte real.

## No-alcance

- No se toca el frontend.
- No se hace backfill ni borrado de imágenes ya existentes en
  `/ftp/revisar`.
- No reemplaza ni ajusta el modelo de patente
  (`yolo-v9-t-384-license-plate-end2end`).
- No se activa (`enabled=true`) en el deploy inicial.
- No se crea issue/Project 4 salvo pedido explícito (no es una HU).

## Contratos

- `detection_log`, `staging_detections` y el contrato `DetectionEvent` no
  cambian — el filtro decide si una captura *entra* al pipeline, no cómo se
  registra una vez adentro.
- Backend consumido por el frontend sin cambios de API.

## Riesgos

- Falso negativo del filtro descarta evidencia real de un vehículo (ángulo
  raro, oclusión). Mitigado con `enabled=false` por defecto, `shadow_mode`
  primero, y umbral conservador calibrado contra datos reales antes de
  activar el descarte.
- Nueva dependencia binaria (archivo `.onnx` de ~3.6MB, descargado una vez,
  no commiteado al repo).

## Criterio de cierre

El filtro corre en `shadow_mode` contra tráfico real durante un período de
calibración, se documenta la tasa de falsos negativos observada contra
capturas con vehículo confirmado, y solo entonces se decide (con
autorización explícita) activar el descarte real en producción.

## Evidencia de implementación

- `api/vehicle_detector.py`, `api/core/config.py::VehicleFilterSettings`,
  enganche en `api/ftp_handler.py::ftp_image()` y
  `api/video_processor.py::_process_video_task()` (Tier 2.5), descarte en
  `watchdog_ftp.py::_handle_image()` cuando `error == "no_vehicle"`.
- Validación contra datos reales de este proyecto (no sintéticos): imágenes
  con vehículo confirmado (`VVHJ88`, `KXBH84`, 2026-08-06) puntuaron
  0.58–0.86; imágenes de `/ftp/revisar` (sin patente detectada) puntuaron
  mayormente 0.02–0.47 — separación razonable para el umbral por defecto
  (0.35), calibración fina pendiente del período en `shadow_mode`.
- Pruebas: `tests/test_vehicle_filter.py` (9 casos — settings, shadow mode,
  bloqueo activo, fail-open). Suite completa: 64/64 OK (unit +
  `RUN_DB_INTEGRATION_TESTS=1` contra Postgres real), sin regresión sobre
  los 55 tests previos.
- `py_compile`, `git diff --check` e import de `api.detect:app` (49 rutas)
  correctos. `VEHICLE_FILTER_SETTINGS.mode == "disabled"` por defecto
  confirmado — sin cambio de comportamiento hasta activación explícita.

- **Fix post-implementación (2026-08-06): `shadow_mode` activado en
  producción + cambio de modelo (YOLOX-Nano → YOLOX-Tiny) y umbral
  (0.35 → 0.20).** Con el filtro en `shadow_mode` real, se corrió un
  backtest offline contra 143 imágenes con vehículo confirmado + 535 sin
  detección del 2026-08-06. YOLOX-Nano falló en un caso claro (vehículo
  cerca, sin oclusión, score 0.11) por la cámara fisheye/gran angular muy
  cercana al vehículo — condición atípica para el dataset COCO. YOLOX-Tiny
  corrigió ese caso (0.11 → 0.70) sin perder discriminación en escenas
  vacías; con umbral 0.20 la tasa de falsos negativos sobre vehículos
  reales fue efectivamente 0% en el dataset (los únicos descartes fueron
  escenas nocturnas confirmadas sin vehículo, verificadas visualmente).
  Ver [ADR-004](../../decisiones/ADR-004-filtro-vehiculo-preclasificador-onnx.md#fix-2026-08-06-yolox-nano--yolox-tiny-umbral-035--020)
  para el detalle completo. `shadow_mode` sigue activo en producción — no
  se activó el descarte real.
