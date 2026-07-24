# ADR-002 — Arquitectura modular e incremental del backend

**Estado:** `aceptada`  
**Fecha:** 2026-07-24  
**Creado por:** Codex, a solicitud del usuario  
**HUs relacionadas:** [HU-006 — Modularizar el backend preservando sus contratos y comportamiento](../historias-usuario/administrador/HU-006-modularizar-backend-sin-regresiones.md)

## Contexto

`api/detect.py` es hoy simultáneamente:

- punto de creación de la aplicación `FastAPI`;
- dueño del `lifespan`, CORS y middleware de autenticación;
- inicializador global de `fast-alpr` (YOLOv9 + CCT-XS);
- contenedor de preprocesamiento, validación y consenso ALPR;
- definición de schemas Pydantic;
- implementación de endpoints de detección, vehículos, entradas/salidas,
  historial, revisión y estadísticas;
- punto de registro de los routers de video, FTP, staging, Excel y auth.

`api/ftp_handler.py` y `api/video_processor.py` importan funciones y estado
global desde `api.detect`. Reutilizar ALPR también importa la composición HTTP
e intenta inicializar dependencias de ejecución. `api/database.py`, a su vez,
concentra persistencia de sesiones, avistamientos, staging, auditoría,
correcciones y estadísticas.

La estructura funciona, pero amplía el impacto de cada cambio y dificulta
probar ALPR sin FastAPI/PostgreSQL, probar casos de uso sin cargar modelos y
reemplazar una etapa manteniendo intactos sus consumidores.

## Decisión

El backend evolucionará incrementalmente hacia módulos por dominio y capas:

```text
routers HTTP
    ↓
servicios/casos de uso
    ↓
dominio ALPR y repositorios
    ↓
adaptadores externos (fast-alpr, PostgreSQL, filesystem)
```

FastAPI solo compondrá la aplicación, middleware, ciclo de vida y routers.
Cada endpoint será delgado: validará transporte, invocará un servicio y
traducirá el resultado a HTTP. La detección, estacionamiento, staging,
evidencia y persistencia no vivirán en handlers.

La separación será por dominio, no un archivo por endpoint. Se respetarán:

1. `api/alpr/` no importa FastAPI, routers, PostgreSQL ni FTP.
2. `api/repositories/` no importa FastAPI ni conoce respuestas HTTP.
3. `api/services/` coordina casos de uso mediante contratos explícitos.
4. `api/routers/` no ejecuta SQL ni contiene reglas ALPR.
5. `api/main.py` no contiene reglas de negocio.
6. El modelo ALPR se inicializa una sola vez por proceso y se inyecta.
7. Los módulos antiguos pueden conservar fachadas compatibles solo durante la
   migración.

## Estrategia de migración

1. Capturar el comportamiento mediante pruebas, OpenAPI y fixtures sintéticas.
2. Extraer funciones sin cambiar algoritmos, umbrales, rutas ni payloads.
3. Mantener temporalmente firmas como `run_multi_strategy(img)`.
4. Conectar un dominio por vez a los nuevos módulos.
5. Comparar OpenAPI, respuestas y efectos persistidos.
6. Retirar wrappers solo cuando búsquedas, pruebas y smoke checks confirmen que
   no quedan consumidores.
7. Mantener cada tanda desplegable y con rollback.

Los cambios funcionales, incluido el clasificador vertical, se implementarán
en HUs separadas. No se modificarán algoritmos mientras se mueve código.

## Contratos protegidos

- rutas, métodos, parámetros, payloads y respuestas actuales;
- códigos y cuerpos de error observados;
- JWT/API key, roles y rutas públicas;
- inicialización de base de datos, admin y loop de staging;
- formatos, estrategias, confianza y `no_detection`;
- staging de 120 segundos y selección de evidencia;
- trazabilidad imagen–avistamiento–sesión–corrección;
- timestamps `America/Santiago`;
- watchdog con `/api/ftp/image` y `/api/ftp/video`;
- entrypoint utilizado por `centralparking.service`.

## Alternativas consideradas

1. **Reescritura completa:** descartada por su alto riesgo y rollback difícil.
2. **Un archivo por endpoint:** descartada por fragmentar sin separar reglas.
3. **Solo mover routers:** insuficiente; mantendría reglas acopladas.
4. **Cambiar ALPR durante la extracción:** descartada porque impediría aislar
   la causa de regresiones.
5. **Mantener `detect.py` central:** admisible solo como fachada temporal.

## Consecuencias

- Habrá más entregas pequeñas, pruebas contractuales y wrappers temporales.
- ALPR, casos de uso y persistencia podrán probarse aisladamente.
- Las dependencias se inyectarán en lugar de importarse como globales.
- Compilar no demostrará equivalencia: se requiere regresión HTTP, datos, FTP,
  evidencia y smoke.

## Estructura objetivo orientativa

```text
api/
├── main.py
├── core/{config,lifespan,security,exceptions}.py
├── schemas/{detection,parking,history,review}.py
├── routers/{detection,parking,history,statistics,ftp,video,staging,excel,auth}.py
├── services/{detection,parking,history,ftp_ingestion,video,staging}_service.py
├── alpr/{engine,preprocessing,validation,consensus,models,direction_tracker}.py
└── repositories/{parking,detection,staging,audit}_repository.py
```

## Referencias

- `api/detect.py`
- `api/database.py`
- `api/ftp_handler.py`
- `api/video_processor.py`
- `api/staging.py`
- `watchdog_ftp.py`
- `documentacion/guias/matriz-regresion.md`
