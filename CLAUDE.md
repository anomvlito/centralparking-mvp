# 🚗 Central Parking MVP — Bugs Resueltos

## Frontend (React/Vite)

### ✅ [RESUELTO] React Keys Anti-pattern (key={i})
**Problema:** El feed mostraba patentes duplicadas visualmente porque usaba índices como claves de React.

**Ubicación:** `src/app/page.tsx` líneas 282, 351, 469, 480, 496

**Causa:** Cuando React detecta cambios en arrays, usa la clave (`key`) para identificar qué elemento cambió. Si la clave es solo el índice (`key={i}`), React no puede distinguir entre un elemento que se movió vs. uno que cambió, causando re-renders incorrectos.

**Solución aplicada:**
- Dashboard: Cambié `key={i}` → `key={`${r.timestamp}-${r.plate}`}`
- Historial: Cambié `key={i}` → `key={`${r.timestamp}-${r.plate}`}`
- Reconciliación: Cambié `key={i}` → `key={`${section}_${r.plate}_${r.timestamp}`}`

**Por qué funciona:** Ahora React puede identificar cada entrada de forma única por su timestamp (único para cada segundo) + plate.

---

## Backend (FastAPI)

### ✅ [RESUELTO] CORS Headers No Heredados en FileResponse
**Problema:** Imágenes de fotos nuevas retornaban errores de CORS desde el frontend en Vercel.

**Ubicación:** `api/ftp_handler.py` línea 408

**Causa:** `FileResponse` de FastAPI NO hereda automáticamente los headers CORS del middleware. Aunque el middleware estuviera configurado, las imágenes servidas por `FileResponse` no incluían los headers CORS, causando `OpaqueResponseBlocking` en el navegador.

**Solución aplicada:**
```python
response = FileResponse(full_path, media_type="image/jpeg")
response.headers["Access-Control-Allow-Origin"] = "*"
response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
response.headers["Access-Control-Allow-Headers"] = "Content-Type"
response.headers["Cache-Control"] = "public, max-age=86400"
return response
```

---

### ✅ [RESUELTO] URLs Relativas Resolvían Contra origen Incorrecto
**Problema:** Fotos nuevas no cargaban porque las URLs relativas (`/api/monitor/file/...`) se resolvían contra Vercel, no contra el backend Cloudflare.

**Ubicación:** `api/ftp_handler.py` líneas 359, 384

**Causa:** Cuando el frontend (en vercel.app) hacía `fetch(/api/monitor/file/...)`, el navegador resolvía esto contra `vercel.app/api/monitor/file/...` en lugar de contra el backend real.

**Solución aplicada:**
```python
backend_url = os.environ.get("BACKEND_URL", "https://efforts-belts-mountain-tile.trycloudflare.com")
meta["url"] = f"{backend_url}/api/monitor/file/historico/{date}/{fname}"
```

**Por qué funciona:** URLs absolutas especifican exactamente dónde buscar la imagen, evitando confusión de orígenes.

---

### ✅ [RESUELTO] Endpoint `/api/ftp/` Retornaba 401 Antes de Autenticación
**Problema:** El endpoint FTP fallaba cuando se hacía upload de imágenes antes de login.

**Ubicación:** `api/detect.py` rutas públicas

**Causa:** El endpoint `/api/ftp/image` estaba protegido por autenticación, pero la cámara Reolink no enviaba credenciales.

**Solución aplicada:**
- Agregué `/api/ftp/` a `_PUBLIC_PATH_PREFIXES` en `api/detect.py`
- Ahora la cámara puede subir imágenes sin autenticación

---

### ✅ [RESUELTO] Fotos No Se Guardaban en Base de Datos
**Problema:** Las fotos se guardaban en disco (`/ftp/historico/`) pero `image_path` no se pasaba a través del pipeline.

**Ubicación:** `api/ftp_handler.py` línea 281-288

**Causa:** Al crear la respuesta de detección, no se incluía el `image_path` generado, por lo que la BD no tenía referencia a las fotos.

**Solución aplicada:**
```python
detect_result = _handle_auto_detection(
    plate, "image", result["confidence"], result["strategy"],
    img=img, bbox_width=result.get("bbox_width", 0), image_path=image_path,  # ← Agregar image_path
)
detect_result["image_path"] = image_path
```

---

### ✅ [RESUELTO] Pipeline de image_path Roto: No se Guardaban Rutas en BD
**Problema:** Fotos se guardaban en disco pero `entry_image_path` y `exit_image_path` quedaban NULL en `parking_sessions`. Frontend mostraba `image_url: null` para todas las fotos.

**Ubicación:** `api/staging.py:76`, `api/ftp_handler.py:218`, `api/database.py:38`

**Causa:** Múltiples puntos de ruptura:
1. `staging_submit()` no tenía parámetro `image_path` → no guardaba rutas en `staging_detections`
2. Tabla `staging_detections` no se creaba en `init_db()` → INSERT fallaba silenciosamente
3. `detection_log` no tenía columna `image_path` para auditoría
4. `_handle_auto_detection()` no pasaba `image_path` a `staging_submit()`
5. `remove_vehicle()` no recibía `image_path` para guardar exits

**Solución aplicada:**
- Agregar `image_path` parámetro a `staging_submit(plate, confidence, quality, strategy, image_path)`
- Insertar `image_path` en todas las inserciones a `staging_detections`
- Crear tabla `staging_detections` en `init_db()` con columna `image_path VARCHAR(255)`
- Agregar columna `image_path` a `detection_log` para auditoría
- Pasar `image_path` desde `_handle_auto_detection()` → `staging_submit()`
- Pasar `image_path` a `remove_vehicle()` para guardar fotos de salida
- Agregar índices en `staging_detections(plate, status)` y `staging_detections(expires_at)`

**Por qué funciona:** Ahora el flujo completo es atómico:
```
Foto capturada
  ↓ image_path = f"historico/{date}/{filename}"
  ↓ _handle_auto_detection(..., image_path=image_path)
  ↓ staging_submit(..., image_path=image_path)
  ↓ INSERT INTO staging_detections(..., image_path=%s)
  ↓ [30s después] staging_promote_expired() selecciona row["image_path"]
  ↓ upsert_vehicle(..., image_path=row["image_path"])
  ↓ entry_image_path se guarda en parking_sessions
  ↓ /api/history retorna image_url con URL completa
```

---

### ✅ [RESUELTO] Fotos Históricas Sin Rutas en BD (Backfill)
**Problema:** 192 fotos existentes en `/ftp/historico/2026-06-02/` no tenían rutas guardadas en `parking_sessions`.

**Ubicación:** Historial de BD anterior al fix de image_path

**Causa:** Antes del fix anterior, el pipeline no guardaba `image_path` → fotos en disco huérfanas de referencias en BD.

**Solución aplicada:**
- Script Python `/tmp/backfill_images.py` que:
  1. Parsea 192 archivos con formato `HH-MM-SS_PLATE_YYYY-MM-DD[_tag].jpg`
  2. Busca sesión en `parking_sessions` para esa placa
  3. Asigna foto a `entry_image_path` si timestamp está dentro de ±5 min de `entry_time`
  4. Asigna foto a `exit_image_path` si timestamp está dentro de ±5 min de `exit_time`
  5. **Solo actualiza si campo es NULL** (no sobrescribe fotos nuevas)
  6. Ejecuta: `/opt/services/centralparking-mvp/.venv/bin/python3 /tmp/backfill_images.py`

**Resultado:** 61 entries + 9 exits pobladas con rutas históricas. Backend seguro: solo actualiza NULL.

**Por qué funciona:** Conservador, idempotente, no rompe el pipeline nuevo.

---

### ✅ [RESUELTO] `logged_at` Reflejaba la Hora de Promoción, no la Hora Real de Detección

**Problema:** Varias detecciones mostraban una hora (`detected_at` en el dashboard) distinta —por minutos, a veces horas— de la hora del nombre del archivo y de la hora quemada en la imagen de la cámara.

**Ubicación:** `api/staging.py::staging_promote_expired()`, `api/database.py::log_to_db()`

**Causa:** Toda detección espera hasta 2 minutos en un buffer ("staging", compite por la mejor foto de la misma patente) antes de promoverse a `detection_log`. Al promoverla, `log_to_db()` no recibía la hora real en que se guardó la foto (`staging_detections.detected_at`, correcta) — dejaba que Postgres usara `DEFAULT now()`, es decir la hora de la promoción. Con datos reales (2000 detecciones) el desfase fue de 120 a 155s en casi el 100% de los casos, y si el backend estuvo caído, todo el backlog se promovía de golpe al reiniciar con `logged_at` = hora de reinicio (caso real: casi 2 horas de diferencia).

**Solución aplicada:**
```python
# database.py
def log_to_db(..., logged_at: datetime.datetime = None):
    cur.execute("""
        INSERT INTO detection_log (..., logged_at)
        VALUES (..., COALESCE(%s, now()))
    """, (..., logged_at))

# staging.py::staging_promote_expired()
log_to_db(plate, "DETECTED", ..., logged_at=row["detected_at"])
```

**Por qué funciona:** `staging_detections.detected_at` ya se capturaba correctamente al momento real de la detección; sólo faltaba propagarlo en vez de descartarlo al promover. `ENTRY`/`EXIT`/`VOID` manuales (los otros llamadores de `log_to_db`) no pasan `logged_at`, así que siguen usando `now()` sin cambios — ahí "ahora" sí es la hora real del evento.

---

### ✅ [RESUELTO] Video: `detected_at` Reflejaba la Hora de Fin de Procesamiento, no la Hora Real del Pase

**Problema:** Sesiones "completadas" con la misma patente registrada como entrada y salida, siendo en realidad el mismo pase real capturado dos veces. Confirmado visualmente (2026-08-06): 5 sesiones mostraban el mismo auto, en la misma posición frente a cámara, con 0-30s de diferencia real, pero separadas 3-7 minutos en `detection_log`.

**Ubicación:** `api/ftp_handler.py::_process_ftp_video_and_register()`, `api/staging.py::staging_submit()`

**Causa:** El fix anterior (`logged_at` real al promover desde staging) resolvió el desfase entre `detected_at` y `logged_at`, pero no cómo se fija `detected_at` para **video**. `staging_submit()` insertaba esa columna con `DEFAULT now()`, evaluado cuando `_process_ftp_video_and_register()` termina de procesar el `.mp4` completo detrás de un semáforo que serializa un video a la vez (`MAX_CONCURRENT_VIDEO_PROCESSING=1`) — si hay otros videos en cola, el delay puede ser de varios minutos, no la hora real del pase. La protección existente contra duplicados (`is_duplicate_duration()`, umbral 120s) no alcanzaba a actuar porque el timestamp inflado por la cola superaba el umbral.

**Solución aplicada:**
```python
# ftp_handler.py::_process_ftp_video_and_register()
detected_at = datetime.datetime.fromtimestamp(
    os.path.getmtime(video_path), tz=datetime.timezone.utc
)  # ANTES de entrar a _video_semaphore
...
result = _handle_auto_detection(..., detected_at=detected_at)

# staging.py::staging_submit()
def staging_submit(..., detected_at: Optional[datetime.datetime] = None):
    cur.execute("""
        INSERT INTO staging_detections (..., detected_at)
        VALUES (..., COALESCE(%s, now()))
    """, (..., detected_at))
```

**Por qué funciona:** El mtime del `.mp4` se lee antes de encolarse — el archivo ya llegó completo por FTP en ese punto, es el mejor proxy disponible a la hora real del pase sin analizar frame a frame. El flujo de fotos no pasa `detected_at` (sigue usando `now()`, correcto porque la subida es casi inmediata a la captura).

---

### ✅ [RESUELTO] Filtro de Vehículo: `event_type` Demasiado Largo Rompía `/api/ftp/image` con 500 (27+ horas en producción)

**Problema:** Desde el deploy del filtro de vehículo (2026-08-06 14:57 UTC), `/api/ftp/image` devolvía `500 Internal Server Error` cada vez que el filtro evaluaba "no hay vehículo" — sin importar `shadow_mode`. Impacto medido: **1652 requests fallidas en ~27 horas**. Cada imagen afectada quedó archivada como `_ERROR` en `/ftp/revisar` **sin pasar nunca por el pipeline de patente** (`run_multi_strategy` nunca se llamó) — incluyendo mientras el filtro estaba en `shadow_mode` (que debía auditar sin afectar el comportamiento, y en la práctica sí lo rompió).

**Ubicación:** `api/vehicle_detector.py::passes_vehicle_filter()`

**Causa:** `audit_log.event_type` es `VARCHAR(20)`. El código escribía `"VEHICLE_FILTER_EVALUATED"` (24 caracteres) → `psycopg2.errors.StringDataRightTruncation`. La excepción no estaba contenida, así que tumbaba la request completa en vez de solo fallar la auditoría.

**Solución aplicada:**
```python
# vehicle_detector.py::passes_vehicle_filter()
if not vehicle_present:
    try:
        log_audit_event(None, "VEHICLE_FILTER_EVAL", {  # 19 caracteres, cabe en VARCHAR(20)
            "score": round(score, 4),
            "threshold": settings.conf_threshold,
            "shadow_mode": settings.shadow_mode,
            "source": source,
        })
    except Exception:
        # La auditoría no puede romper el pipeline de detección real
        # (mismo criterio que DirectionService._audit_sink).
        pass
```

**Por qué funciona:** El nombre corto (19 caracteres, mismo patrón que `"DIRECTION_EVALUATED"`, 19 caracteres, ya usado en el proyecto) evita la causa puntual. El `try/except` es la corrección de fondo: cualquier fallo futuro en la auditoría —de esta causa o de otra— nunca vuelve a poder tumbar el pipeline real, igual que ya garantiza `DirectionService.observe()` para su propio audit_sink.

---

### ✅ [RESUELTO] Conciliación Automática Cerraba Estadías Falsas de Autos que Esperaban Cupo en la Entrada

**Problema:** Un auto que espera unos minutos frente a la cámara antes de poder estacionar (cupo ocupado) generaba dos avistamientos separados de la misma patente. `auto_reconcile_exact_matches` los tomó como una entrada+salida real ("EXACT"), cerrando una estadía de pocos minutos que nunca ocurrió — el auto seguía adentro. Caso real detectado por el usuario: `SHKV20`, 2026-08-10, sesión `parking_sessions.id = 6753` (entrada 09:42:04, "salida" falsa 09:44:34, 2m30s después). Corregido manualmente en producción: se reabrió la sesión y se revirtió la detección de salida a `UNMATCHED`.

**Ubicación:** `api/database.py::build_stay_proposals()`

**Causa:** El emparejamiento `EXACT` solo exigía patente idéntica, orden cronológico y una diferencia menor a `max_hours` (24h por defecto) — sin ningún mínimo de tiempo. El buffer de staging (`STAGING_TTL_SECONDS = 120s`) solo fusiona detecciones dentro de una ventana de 2 minutos; un auto que demora más que eso en encontrar cupo genera un segundo avistamiento fuera de esa ventana, indistinguible para el emparejador de una salida real.

**Solución aplicada:**
```python
# database.py
STAY_MIN_DURATION_SECONDS = int(os.environ.get("STAY_MIN_DURATION_SECONDS", "300"))

def add_pairs(max_distance: int, match_type: str, min_seconds: int = 0) -> None:
    ...
    if seconds <= 0 or seconds > max_seconds or seconds < min_seconds:
        continue
    ...

add_pairs(0, "EXACT", min_seconds=STAY_MIN_DURATION_SECONDS)
add_pairs(1, "FUZZY")
```

**Por qué funciona:** Un par que antes calificaba como `EXACT` con menos de 5 minutos de diferencia ahora cae a `FUZZY` (mismo par, sin `used` marcado por el primer paso). `auto_reconcile_exact_matches` solo reconcilia automáticamente `FUZZY` cuando dura ≤ 1 minuto (duplicado de re-lectura), así que un caso como este queda disponible en `/api/stay-proposals` para revisión manual en vez de auto-cerrarse como una estadía real. El umbral (5 min) está alineado con `PLATE_FUZZY_WINDOW_MIN`, ya usado en este archivo con el mismo criterio de "misma visita".

---

## Patrón para Agregar Bugs Futuros

Al resolver un nuevo bug, agregá aquí:
1. Título: `[RESUELTO] Descripción corta`
2. Problema: qué pasaba
3. Ubicación: archivo + línea
4. Causa: por qué pasaba
5. Solución: qué código cambió
6. Por qué funciona: explicación técnica breve

---

## 🔧 [2026-06-13 21:00] Optimización: Estrategia Híbrida FOTOS + VIDEOS

**Cambios aplicados:**
1. **Video processing mejorado:**
   - Frame skipping: 10 → 5 frames (cobertura de ~6fps en lugar de 3fps)
   - Motion threshold: 2% → 1% (detecta movimientos más pequeños)
   - Estrategia: CLAHE solo → RUN_MULTI_STRATEGY (usa 12 estrategias como fotos)
   - Confirmación: 2 frames → 1 frame (menos restrictivo)

2. **Deduplicación respetada:**
   - Videos ahora registran en BD automáticamente
   - Pero SOLO si no existe sesión activa (vehicle_exists check)
   - Evita duplicados: Tier 1 (fotos) + Tier 2 (videos backup)
   - Si foto detectó AABB11 → video no re-registra AABB11

3. **Resultado esperado:**
   - Fotos: 70-80% tasa de detección (multi-strategy completa)
   - Videos: Backup para casos donde fotos fallan
   - Sin duplicados por deduplicación

---

## Estado General

✅ **Sistema 100% OPERACIONAL:**
- Dashboard funciona con autenticación JWT ✓
- Fotos de hoy + históricas se cargan en el feed ✓
- BD registra eventos con ACID consistency ✓
- Cero duplicados por diseño (parking_sessions como source of truth) ✓
- Pipeline de image_path: FTP → staging → parking_sessions → /api/history ✓
- Frontend muestra `<PhotoThumb>` para cada entrada/salida ✓

⏳ **Mejoras futuras opcionales:**
- Consolidar lógica de dirección (DirectionTracker) con regresión lineal robusto
- Agregar índices adicionales para queries de filtrado por fecha/placa
- Implementar deduplicación automática de detecciones duplicadas en staging
- Exposición de estadísticas de calidad por estrategia de ALPR
