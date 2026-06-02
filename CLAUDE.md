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

## Patrón para Agregar Bugs Futuros

Al resolver un nuevo bug, agregá aquí:
1. Título: `[RESUELTO] Descripción corta`
2. Problema: qué pasaba
3. Ubicación: archivo + línea
4. Causa: por qué pasaba
5. Solución: qué código cambió
6. Por qué funciona: explicación técnica breve

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
