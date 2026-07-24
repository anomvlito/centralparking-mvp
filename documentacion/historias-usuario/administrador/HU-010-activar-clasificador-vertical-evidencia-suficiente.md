# HU-010 — Activar el clasificador vertical con evidencia suficiente

**Actor:** `administrador`
**Estado:** `implementada` — desplegada y verificada con tráfico real de producción
**Feature relacionada:** [Clasificación de entrada y salida por trayectoria vertical](../../features/in-review/clasificacion-vertical-entrada-salida.md) — paso 5 de "Dependencias y orden" ("Activación solo con regresión, observabilidad, revisión y rollback")
**Issue:** no creado — pendiente de autorización explícita del usuario
**Project 4:** no agregado — pendiente de autorización explícita del usuario
**HUs base:** [HU-007](./HU-007-clasificar-direccion-trayectoria-vertical.md), [HU-008](./HU-008-configurar-parametros-clasificador-vertical.md), [HU-009](../auditor/HU-009-observar-decisiones-clasificador-vertical.md)
**ADRs relacionadas:** [ADR-001](../../decisiones/ADR-001-reactivar-direction-tracker-acotado.md), [ADR-003](../../decisiones/ADR-003-clasificacion-direccion-trayectoria-vertical.md)

## Historia

Como **administrador**, quiero **que el clasificador vertical reciba
evidencia suficiente por patente y que su resultado llegue realmente al
campo `direction` que expone `GET /api/detections`**, para **que el dashboard
de 3 columnas (HU-005) pueda agrupar entradas/salidas pendientes por
dirección real, en vez de recibir siempre `UNKNOWN`**.

## Contexto y problema

HU-007/008/009 implementaron el algoritmo, su configuración y su auditoría,
pero deliberadamente en modo sombra (`effect=none`, "activación productiva
pendiente"). El servicio ya corre en producción con
`DIRECTION_ENABLED=true` y `DIRECTION_OBSERVATION_ONLY=true` desde hace
horas. Midiendo los datos reales acumulados (`audit_log`, evento
`DIRECTION_EVALUATED`) el 2026-07-24:

```
674 evaluaciones (07:24–21:35 UTC)
  UNKNOWN:     630 (93.5 %)
  APPROACHING:  29 (4.3 %)
  DEPARTING:    15 (2.2 %)

Motivos de UNKNOWN:
  insufficient_samples:      461 (73 %)  ← domina
  insufficient_displacement: 116 (18 %)
  insufficient_slope:         46 (7 %)
  insufficient_consistency:    7 (1 %)
```

Investigación de causa raíz — son **dos problemas independientes**, no uno:

1. **Los frames de video nunca alimentan el clasificador.**
   `_process_ftp_video_and_register()` (`api/ftp_handler.py`) llama a
   `_handle_auto_detection(plate, "video", confidence, "video_clahe",
   img=img)` **sin pasar `center_y`, `geometry_strategy` ni `timestamp`**.
   Solo las fotos sueltas (`POST /api/ftp/image`) aportan una muestra cada
   una. Con `DIRECTION_MIN_SAMPLES=3` y `DIRECTION_WINDOW_SEC=15`, si la
   cámara no manda ≥3 fotos de la misma patente en 15s, el algoritmo
   aborrece por diseño (correcto, no es un bug de lógica) — esto explica el
   73 % de `insufficient_samples`.
2. **Aunque el clasificador decidiera bien, el resultado no se persiste**
   donde el backend lo expone. `staging_promote_expired()`
   (`api/staging.py`) llama a `log_to_db(plate, "DETECTED",
   status="STAGING_AUTO", conf=..., image_path=...)` sin pasar `direction`
   — el default de `log_to_db` es `"UNKNOWN"`. La evaluación de
   `direction_service.observe()` que sí corre en `_handle_auto_detection`
   solo se audita en `audit_log`, nunca llega a `detection_log.direction`.

Arreglar solo (2) dejaría el `UNKNOWN` real en ~93 % igual, porque la mayoría
de las evaluaciones ya son `UNKNOWN` por falta de muestras. Arreglar solo (1)
no serviría de nada visible porque el resultado seguiría sin propagarse.
**Ambos son necesarios juntos.**

## Criterios de aceptación

### A — Frames de video alimentan el clasificador

- [ ] `_process_ftp_video_and_register()` (o el punto equivalente tras la
  modularización de HU-006) pasa `center_y`, `geometry_strategy` y
  `timestamp` reales de cada frame procesado a `_handle_auto_detection`,
  igual que ya hace el flujo de foto (`ftp_image`).
- [ ] Cada frame de un mismo video/patente contribuye como muestra separada
  al historial temporal de `direction_service` (mismo mecanismo que fotos,
  sin tabla ni historial paralelo).
- [ ] No cambia el resultado devuelto por `POST /api/video/upload`, el CSV
  de resultados, ni el registro de imagen/staging existente — solo se
  agregan muestras al tracker direccional.
- [ ] No se reintroduce X, tamaño ni zonas (mismas exclusiones de HU-007).

### B — El resultado llega a `detection_log.direction`

- [ ] `staging_detections` persiste el resultado de dirección evaluado
  (o los datos mínimos para recalcularlo) en el momento en que una
  detección gana la ventana de staging.
- [ ] `staging_promote_expired()` propaga ese valor a
  `log_to_db(..., direction=...)` en vez de omitirlo.
- [ ] Con `DIRECTION_ENABLED=false`, el comportamiento es idéntico al
  actual (`direction` sigue siendo `"UNKNOWN"` por default) — cambio
  inerte si el flag está apagado.
- [ ] `GET /api/detections` refleja `APPROACHING`/`DEPARTING`/`UNKNOWN`
  reales cuando el flag está prendido, sin cambiar el shape del contrato
  (`DetectionEvent` de HU-004 no cambia).

### C — Sigue sin efectos autoritativos

- [ ] No se abre ni cierra `parking_sessions` automáticamente a partir de
  `direction` — eso sigue siendo el "modo activo" separado de HU-004,
  gateado por ADR-001, fuera de alcance de esta HU.
- [ ] `direction` sigue siendo solo informativo para el dashboard manual
  (columnas 1/2/franja de triage de HU-005), tal como ya está construido.
- [ ] `UNKNOWN` sigue conservando el avistamiento para revisión sin mutar
  nada (sin cambios de comportamiento en ese caso).

### D — Medición antes/después

- [ ] Se registra la distribución de `direction` (vía
  `GET /api/audit/direction/metrics`, ya existente de HU-009) antes y
  después del cambio, para cuantificar cuánto bajó `insufficient_samples`.
- [ ] No se fija un umbral numérico de éxito arbitrario sin dataset
  representativo (mismo criterio que HU-008/HU-009): se reporta el dato
  real, no se afirma una meta inventada.

## No-alcance

- No activa apertura/cierre automático de sesiones a partir de `direction`
  (modo activo de HU-004) — sigue gateado por ADR-001, requiere su propia
  autorización y evidencia posterior.
- No cambia los umbrales de HU-008 (`DIRECTION_MIN_SAMPLES`,
  `DIRECTION_MIN_DISPLACEMENT`, `DIRECTION_MIN_SLOPE`,
  `DIRECTION_MIN_CONSISTENCY`) — esta HU solo aumenta la evidencia
  disponible; calibrar umbrales con más muestras es una decisión posterior,
  informada por el punto D.
- No modifica el frontend — `Dashboard.tsx` ya consume `direction` tal cual
  quedó en la reapertura de HU-005.
- No borra ni modifica `audit_log` histórico.
- No publica (commit/push/PR/merge/deploy) en la etapa de creación de esta
  HU — solo el documento. Implementación y verificación en etapa separada,
  con autorización explícita adicional.
- No crea el issue de GitHub ni lo agrega al Project 4 en esta etapa.

## Código relacionado

- Backend:
  - `api/ftp_handler.py::_process_ftp_video_and_register` /
    `api/video_processor.py::_process_video_task` — pasar geometría real
    por frame.
  - `api/staging.py::staging_submit` / `staging_promote_expired` — persistir
    y propagar `direction`.
  - `api/services/direction.py::DirectionService.observe` — consumidor sin
    cambios de firma esperados.
  - `api/database.py::log_to_db` — ya acepta `direction`, solo falta que se
    lo pasen desde staging.
- Frontend: sin cambios — consumidor de `GET /api/detections`.
- Operación: `centralparking.service`; sin cambios de variables de entorno
  nuevas (reutiliza `DIRECTION_ENABLED`/`DIRECTION_OBSERVATION_ONLY`
  existentes).

## Contratos que deben preservarse

- `DetectionEvent` (HU-004): shape sin cambios, solo el valor real de
  `direction`.
- `POST /api/video/upload`, `GET /api/video/results/{video_id}`: sin
  cambios de contrato.
- `direction_service.observe()`: firma y comportamiento sin cambios cuando
  `DIRECTION_ENABLED=false`.
- `audit_log`/`DIRECTION_EVALUATED`: se mantiene igual, es la fuente de la
  medición de D.

## Impacto sobre funcionalidades existentes

Toca el mismo pipeline de ingesta que causó el incidente de 2026-07-17
(salidas falsas/duplicados con el `DirectionTracker` anterior) y los
OOM-kills documentados en `CLAUDE.md` para procesamiento de video. A
diferencia de aquel incidente, este cambio:

- no decide entrada/salida por sí solo (sigue en modo sombra, `effect=none`
  a nivel de sesiones);
- no agrega carga de cómputo relevante (el bbox por frame ya se calcula en
  `run_multi_strategy`, solo se pasa el dato que ya existe);
- es reversible apagando `DIRECTION_ENABLED` sin tocar código.

Aun así, toca código de ingesta en producción con datos reales — requiere
pruebas controladas antes de considerar cerrado.

## Riesgos y datos

- **Riesgo alto heredado (ADR-001):** este es el mismo pipeline que ya
  rompió producción una vez. Aunque el cambio es aditivo y no autoritativo,
  cualquier excepción no controlada en `staging_promote_expired()` (que
  corre en un loop de background) podría interrumpir la promoción de
  avistamientos si no se maneja con cuidado.
- Persistir `direction` en `staging_detections` requiere una migración
  aditiva (nueva columna); no debe borrar ni alterar filas existentes.
- Pasar `center_y` por frame de video no debe cambiar qué frame gana la
  ventana de staging (la calidad de imagen sigue siendo el criterio de
  selección) ni introducir X/tamaño accidentalmente.
- Sin datos sensibles nuevos: se reutiliza la misma imagen/detección ya
  procesada, no se agregan patentes ni imágenes nuevas.

## Pruebas de regresión

- `DIRECTION_ENABLED=false`: comportamiento idéntico al actual (`direction`
  siempre `UNKNOWN`, sin cambios en staging/detection_log).
- Video: frames contribuyen muestras al tracker sin cambiar el resultado de
  `/api/video/upload` ni duplicar staging.
- Foto: sigue funcionando exactamente igual que hoy (ya pasa `center_y`).
- `staging_promote_expired()`: sigue promoviendo con el mismo TTL/quality
  score; ahora además propaga `direction`.
- `/api/detections`: shape sin cambios; `direction` refleja el valor real
  cuando el flag está prendido.
- Excel, Historial, `/api/cars`, login: sin regresión.
- Medición: `GET /api/audit/direction/metrics` antes/después documentada en
  la evidencia de implementación.

## Propuesta técnica (revisada durante implementación)

Al implementar se encontraron dos simplificaciones/hallazgos respecto al plan
original de arriba, documentados acá en vez de reescribir la sección previa:

1. **Sin migración de esquema.** `DirectionTracker` ya expone
   `latest(plate)` (última evaluación en memoria por patente, usada
   internamente por `_remember`). `staging_promote_expired()` puede
   consultarla directamente al momento de promover, sin persistir nada nuevo
   en `staging_detections`. Se elimina el paso de migración aditiva
   planeado — menos riesgo, ningún cambio de esquema.
2. **El pipeline de video no rastreaba trayectoria por frame.**
   `_process_video_task` (`api/video_processor.py`) agrupa frames por
   similitud de texto OCR (`clusters`) y solo conserva el frame de mejor
   confianza por cluster — no existía ningún historial `center_y` por frame
   antes de este cambio. Se agregó una lista `samples` por cluster que
   acumula `(video_seconds, center_y, geometry_strategy)` de cada frame con
   geometría disponible, reutilizando el mismo `run_multi_strategy(frame)`
   ya calculado (sin cómputo adicional).
3. Tras terminar de procesar el video, si `direction_service.settings.enabled`,
   cada cluster reproduce sus muestras: todas menos la última vía
   `tracker.record()` (sin auditar), y la última vía `direction_service.observe()`
   (sí audita) — un solo evento `DIRECTION_EVALUATED` por vehículo, no uno
   por frame, respetando la restricción explícita de HU-009.
4. `staging_promote_expired()`: consulta `direction_service.tracker.latest(plate)`
   y pasa `.direction` a `log_to_db(..., direction=...)`; sin evaluación
   previa o con `DIRECTION_ENABLED=false`, cae al mismo default `"UNKNOWN"`
   de siempre.
5. **Limitación conocida, no resuelta en esta entrega:** las muestras de
   video usan como tiempo la posición dentro del archivo
   (`cv2.CAP_PROP_POS_MSEC`, refleja la velocidad real del vehículo en la
   grabación), mientras que el flujo de fotos usa `time.monotonic()` del
   proceso al momento de la detección. Son bases de tiempo incompatibles: si
   la misma patente tuviera muestras de foto y de video en la misma ventana
   real, no se combinan (la resta de tiempos da negativa y el filtro de
   ventana las descarta) — cada fuente arma su propia trayectoria de forma
   aislada, correcta en sí misma, pero no fusionada entre fuentes. No se
   intenta reconciliar ambas bases sin datos reales para validar el
   resultado (mismo criterio de HU-008/009: no calibrar sin dataset
   representativo).
6. Probado localmente en worktree aislado (ver evidencia abajo). **No se
   pudo probar `_process_video_task` de punta a punta con un video real**:
   el motor ALPR está offline en este entorno de desarrollo ("modo
   simulado"), así que la cobertura de la parte de video es a nivel del
   patrón de replay (`tests/test_direction_video_wiring.py`,
   `VideoReplayPatternTests`), no una ejecución real del pipeline de video.
7. Medir `GET /api/audit/direction/metrics` antes y después del deploy real
   en el VPS, reportar el cambio observado en la proporción de `UNKNOWN` —
   sin prometer un número de antemano.
8. Publicación (commit/push/PR) y deploy: pendientes de autorización
   explícita adicional, dado el historial de incidentes de este mismo
   pipeline (ADR-001) y que la parte de video no se pudo probar end-to-end
   localmente.

## Dependencias

- Depende de HU-007/008/009 (ya implementadas, en modo sombra).
- HU-005 (dashboard de 3 columnas) es la consumidora directa del resultado.
- No depende de ni bloquea el fix de `PR #38` (bug de conciliación manual,
  ya resuelto y desplegado) — son problemas distintos en el mismo dominio.

## Evidencia de implementación

- Rama/worktree: `hu-010-activar-clasificador-vertical` en
  `.worktrees/hu-010-activar-clasificador-vertical`, basada en `origin/main`
  real (commit `2672e46`, incluye el fix de `PR #38`).
- Cambios: `api/staging.py` (`staging_promote_expired` consulta
  `direction_service.tracker.latest`), `api/video_processor.py` (muestras
  por cluster + replay hacia `direction_service`).
- Tests nuevos: `tests/test_direction_video_wiring.py` —
  `VideoReplayPatternTests` (patrón de replay, sin DB) y
  `StagingPromoteDirectionWiringTests` (wiring real contra Postgres,
  opt-in `RUN_DB_INTEGRATION_TESTS=1`, patente sintética `TESTVID9`,
  limpieza garantizada).
- `python -m compileall api tests`: correcto.
- `python -m unittest discover -s tests`: 35 pruebas, 3 skips esperados
  (los dos tests de integración de este cambio + el de HU-004 sin
  `RUN_DB_INTEGRATION_TESTS=1`), sin regresiones.
- `RUN_DB_INTEGRATION_TESTS=1 python -m unittest tests.test_direction_video_wiring tests.test_reconciliation_integration`:
  6 pruebas correctas contra Postgres real; verificado manualmente que no
  quedaron filas sintéticas (`TESTVID%`) tras correr.
- **No probado:** `_process_video_task` de punta a punta con un video real
  (ALPR offline en este entorno — "modo simulado"). La parte de video queda
  verificada solo a nivel de patrón (replay), no de ejecución real del
  pipeline.

## Resultado en producción (2026-07-24, tras publicar)

- Commit `07f3a58`, [PR #39](https://github.com/anomvlito/centralparking-mvp/pull/39),
  merge `ccfedc53e4823703ae1ceadf9a168872c5848a88`. Deploy VPS vía
  `deploy.yml`: `success`.
- Confirmado con tráfico real: video sí alimenta el clasificador en
  producción (evaluaciones con `source=video` y `sample_count` creciendo
  frame a frame, algo que nunca pasaba antes de esta HU).
- Wiring confirmado extremo a extremo: la última evaluación conocida de
  `direction_service.tracker` llega correctamente a `detection_log.direction`
  (verificado con casos reales, ej. `JTXY95`/`TLVX70`).
- **Calibración posterior:** con 228 evaluaciones reales acumuladas tras el
  deploy, se detectó que `DIRECTION_MIN_SLOPE=0.01` rechazaba por poco
  varios casos de alta confianza (desplazamiento y consistencia ya
  confirmados). Se bajó a `0.006` (ver
  [guía de configuración](../../guias/configuracion-clasificador-vertical.md),
  sección "Propuesta de calibración") — aplicado directo en el drop-in de
  systemd, `DIRECTION_OBSERVATION_ONLY=true` sin cambios. Confirmado con
  casos reales post-calibración (`JTXY84` llegó a `APPROACHING` y se
  promovió correctamente a `detection_log`).
- **Comportamiento observado, no resuelto:** la dirección puede cambiar
  mientras siguen llegando muestras dentro de la ventana de 15s
  (`DIRECTION_WINDOW_SEC`), y lo que se promueve a `detection_log` es la
  evaluación más reciente al momento del TTL de staging, no
  necesariamente la de mayor confianza (visto en vivo con `TLVX70`: llegó a
  `APPROACHING` con 3 muestras y volvió a `UNKNOWN` con una 4ª). Queda
  anotado para una revisión futura, fuera del alcance de esta HU.
- **Hallazgo aparte, no corregido:** `GET /api/stays`, `GET /api/detections`
  y `POST /api/stays/reconcile` responden sin exigir `Authorization` — igual
  nota ya dejada en HU-004.
- **Sin resolver, pre-existente:** `watchdog_ftp.py::_sweep_existing()`
  nunca reprocesa videos y excluye del barrido cualquier imagen fuera de la
  ventana de arranque — cada reinicio del servicio deja huérfanos en
  `/ftp/entrada` (causó una emergencia de disco el mismo día, resuelta
  manualmente borrando huérfanos de +14 días; la causa de fondo sigue sin
  arreglarse).
