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

✅ **Sistema operativo** — Dashboard funciona, fotos de junio se cargan, BD registra eventos correctamente.

⏳ **Mejoras pendientes:**
- Consolidar lógica de dirección (DirectionTracker) con más datos históricos
- Agregar índices de BD para queries de filtrado por fecha
- Implementar deduplicación automática de detecciones duplicadas
