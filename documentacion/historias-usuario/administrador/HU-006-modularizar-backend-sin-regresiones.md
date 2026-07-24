# HU-006 — Modularizar el backend preservando sus contratos y comportamiento

**Actor:** `administrador`  
**Estado:** `en-progreso`  
**Feature relacionada:** [Modularización segura del backend](../../features/in-progress/modularizacion-segura-backend.md)  
**Issue:** [#24](https://github.com/anomvlito/centralparking-mvp/issues/24)  
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In progress` / `In Progress`  
**Creado por:** Codex, a solicitud del usuario  
**ADR relacionada:** [ADR-002 — Arquitectura modular e incremental del backend](../../decisiones/ADR-002-arquitectura-modular-backend.md)

## Historia

Como **administrador**, quiero **que el backend esté separado en módulos
cohesivos de composición HTTP, casos de uso, ALPR y persistencia**, para
**modificar una etapa de detección u operación con menor riesgo y sin perder
ninguna capacidad que Central Parking utiliza hoy**.

## Contexto y problema

`api/detect.py` crea FastAPI, configura seguridad/CORS/lifespan, inicializa
YOLOv9 y CCT-XS, contiene doce estrategias de imagen, valida patentes, ejecuta
consenso, define schemas y expone endpoints de detección, estacionamiento,
historial, revisión y estadísticas. Al final registra routers externos.

`api/ftp_handler.py` y `api/video_processor.py` importan desde `api.detect`;
por tanto, pedir detección también depende implícitamente de la aplicación
HTTP. `api/database.py` agrupa consultas y transacciones de sesiones,
avistamientos, staging, auditoría, corrección y estadísticas.

La modularización es un cambio estructural de alto alcance. Debe quedar
protegida por una línea base antes de mover código y entregarse en tandas
pequeñas. Esta HU no cambia qué detecta el sistema ni cómo decide: crea
fronteras para que las HUs posteriores puedan hacerlo aisladamente.

## Criterios de aceptación

### Línea base y contratos

- [ ] Existe un inventario versionado de todos los endpoints actuales con
  método, path, autenticación, parámetros, request, response y errores.
- [ ] Se captura el OpenAPI anterior a la extracción y una comparación
  automatizada detecta rutas eliminadas, duplicadas o incompatibles.
- [ ] Se identifican consumidores reales: frontend productivo,
  `watchdog_ftp.py`, procesamiento de video, scripts operativos y servicios.
- [ ] Existen pruebas de caracterización para ALPR, staging, FTP/watchdog,
  entradas/salidas, historial, evidencia, auth, Excel y estadísticas.
- [ ] Todas las fixtures usan imágenes, usuarios y patentes sintéticas o
  anonimizadas.

### Composición FastAPI

- [ ] La creación de `FastAPI`, middleware, CORS, lifespan e inclusión de
  routers queda separada de las reglas de detección y estacionamiento.
- [ ] `init_db`, `ensure_default_admin` y `staging_loop` se ejecutan una vez,
  en el mismo orden funcional y con cancelación limpia.
- [ ] El entrypoint de Uvicorn utilizado por `centralparking.service` se
  conserva o cuenta con transición compatible y rollback documentado.
- [ ] Ningún router se registra dos veces y `/openapi.json` conserva todos los
  paths.

### Routers, schemas y servicios

- [ ] Los endpoints se agrupan en routers por dominio; no se crea un archivo
  por endpoint sin justificación.
- [ ] Los handlers HTTP solo validan transporte, invocan un servicio y
  traducen resultados/excepciones a HTTP.
- [ ] Ningún handler ejecuta SQL, escribe directamente evidencia ni llama
  directamente a `alpr.predict`.
- [ ] Los schemas Pydantic están separados de la composición HTTP y mantienen
  nombres, opcionalidad y valores por defecto actuales.
- [ ] Los servicios pueden probarse sin levantar FastAPI.

### Motor ALPR

- [ ] Inicialización del modelo, preprocesamiento, validación, consenso y
  modelos de resultado poseen fronteras explícitas.
- [ ] El motor ALPR puede importarse y probarse sin inicializar FastAPI,
  PostgreSQL, FTP o el loop de staging.
- [ ] El modelo `fast-alpr` se inicializa una sola vez por proceso.
- [ ] Se conserva una fachada temporal compatible con
  `run_multi_strategy(img)` hasta migrar todos sus consumidores.
- [ ] La extracción no cambia modelos, estrategias, orden, formatos,
  confianza, umbral de una sola estrategia ni selección geométrica.

### Persistencia

- [ ] Las operaciones de sesiones, detecciones, staging y auditoría se
  exponen mediante repositorios o contratos equivalentes por dominio.
- [ ] Se preservan transacciones, locks y atomicidad de
  `upsert_vehicle`, `remove_vehicle`, correcciones y revisión.
- [ ] No se crean migraciones de datos como efecto incidental de mover código.
- [ ] Las funciones antiguas de `api.database` solo se retiran cuando no
  existan consumidores y la regresión sea correcta.

### Compatibilidad observable

- [ ] El frontend productivo funciona sin cambios obligatorios.
- [ ] `watchdog_ftp.py` procesa imagen, video, no detección y error de backend.
- [ ] `POST /api/detect` conserva éxito real/mock, `image decode failed`,
  `no_detection`, confianza, estrategia y status HTTP observado.
- [ ] Entradas, salidas, duplicados, corrección y revisión mantienen efectos.
- [ ] Staging conserva TTL, puntaje, reemplazo y mejor imagen.
- [ ] Historial, sightings, evidencia y timestamps de Chile no cambian.
- [ ] Auth mantiene JWT/API key, roles, rutas públicas y 401/403.
- [ ] Excel mantiene importación, reconciliación y errores.

### Entrega incremental

- [ ] Cada tanda tiene alcance, pruebas, commit y rollback independientes.
- [ ] No se mezcla movimiento estructural con el algoritmo vertical ni otra
  capacidad funcional.
- [ ] Los wrappers temporales tienen criterio de retiro verificable.
- [ ] El cierre incluye prueba de sintaxis/imports, suite, health y smoke
  contra los mecanismos reales, sin usar compilación como única evidencia.

## No-alcance

- Modificar YOLOv9, CCT-XS o dependencias de modelos.
- Cambiar estrategias, normalización, patrones o confianza ALPR.
- Reactivar `DirectionTracker` o clasificación automática.
- Crear, eliminar o versionar endpoints por conveniencia arquitectónica.
- Cambiar schemas públicos, tablas, estados o reglas de negocio.
- Modificar el frontend histórico en `centralparking-mvp/src/`.
- Refactorizar el frontend productivo; corresponde a HU-002.
- Cambiar secretos, credenciales, puertos o destinos de despliegue.
- Ejecutar una reescritura completa en una sola entrega.

## Código relacionado

- Backend:
  - `api/detect.py`: composición, ALPR y endpoints a extraer.
  - `api/database.py`: persistencia a separar por contratos.
  - `api/ftp_handler.py`: consumidor de detección y staging.
  - `api/video_processor.py`: consumidor ALPR por frame.
  - `api/staging.py`: servicio y router actualmente combinados.
  - `api/excel.py`, `api/auth.py`: routers existentes a preservar.
  - `api/direction_tracker.py`: mover sin cambiar comportamiento.
  - `watchdog_ftp.py`: consumidor externo por HTTP.
  - `tests/`: ampliar caracterización y contrato.
- Frontend:
  - `adyac-camaras-frontend/src/app/page.tsx`: consumidor contractual; no
    requiere cambios.
  - `adyac-camaras-frontend/src/proxy.ts`: contrato `/api/:path*`.
- Operación:
  - `centralparking.service`, puerto 8000.
  - `parking-watchdog.service`.
  - `start-backend.sh` y documentación operativa real.

## Contratos que deben preservarse

Como mínimo:

```text
GET    /api/cars
GET    /api/history
PATCH  /api/history/{session_id}/plate
PATCH  /api/history/{session_id}/review
POST   /api/clear-history
GET    /api/stats
POST   /api/detect
POST   /api/entry
POST   /api/exit/{plate}
DELETE /api/cars/{plate}
POST   /api/ftp/image
POST   /api/ftp/video
GET    /api/ftp/events
GET    /api/monitor/images
GET    /api/monitor/review
GET    /api/monitor/file/{folder}/{date}/{filename}
POST   /api/video/upload
GET    /api/video/results/{video_id}
POST   /api/staging/deduplicate
GET    /api/staging/status
GET    /api/sightings
GET    /api/sightings/{plate}
POST   /api/audit/feedback
GET    /api/audit/log
POST   /api/excel/upload
GET    /api/excel/reconcile
GET    /api/excel/imports
POST   /auth/login
GET    /auth/me
PATCH  /auth/password
POST   /auth/users
GET    /auth/users
PATCH  /auth/users/{user_id}
```

Se preservan métodos, paths, query parameters, límites, payloads, respuestas,
errores, autenticación, CORS, timestamps y efectos persistidos.

En particular, la extracción de routers, servicios, repositorios o etapas de
pipeline no puede alterar estos contratos congelados:

```ts
type ParkedCar = {
  plate: string;
  entryTime: number;
  isEvent: boolean;
  eventFee?: number | null;
};

type CarsResponse = Record<string, ParkedCar>;

type EntryOpen = {
  session_id: number;
  plate: string;
  entry_time: string;
  entry_image_url: string | null;
};

type ExitOrphan = {
  orphan_exit_id: number;
  plate: string;
  exit_time: string;
  exit_image_url: string | null;
  confidence: number;
  status: "PENDING" | "MATCHED" | "DISMISSED";
};

type SessionClosed = {
  session_id: number;
  plate: string;
  entry_time: string;
  entry_image_url: string | null;
  exit_time: string;
  exit_image_url: string | null;
  duration_minutes: number;
  fee: number;
};
```

`CarsResponse` representa el estado actual indexado por patente. Los otros
tres DTO representan proyecciones de conciliación y no pueden sustituirlo.
Asimismo, el clasificador direccional debe depender solo de
`record(plate, center_y, timestamp)` según HU-007/ADR-003; `UNKNOWN` no muta
sesiones ni salidas huérfanas.

## Impacto sobre funcionalidades existentes

Todo el backend está potencialmente afectado aunque el resultado esperado sea
equivalencia. Por eso la implementación se divide en tandas y comienza con
caracterización. El frontend no debería necesitar cambios, pero debe usarse
como consumidor de regresión. El watchdog requiere smoke explícito porque
funciona como proceso separado.

## Riesgos y datos

- Inicialización doble del modelo y agotamiento de memoria.
- Orden incorrecto del lifespan o loop de staging duplicado.
- Cambios silenciosos en errores y autenticación.
- Pérdida de atomicidad al dividir repositorios.
- Rutas de evidencia incorrectas al abstraer filesystem.
- Exposición accidental de patentes en snapshots o logs.
- Conflictos con cambios locales existentes en ambos repositorios.
- Eliminación prematura de fachadas aún usadas por video/FTP.

No se usarán datos reales identificables como fixtures. No se borrará
evidencia ni historia.

## Pruebas de regresión

- OpenAPI: igualdad de paths/métodos y schemas protegidos.
- Auth: login, `/auth/me`, admin, expiración, API key, 401/403.
- ALPR: válida, sin detección, decode fallido, incierta y mock.
- Staging: primera, inferior, reemplazo, expiración y evidencia.
- FTP: imagen, video, backend caído, error, reinicio y archivo estable.
- Estacionamiento: entrada, duplicado, salida, 404, void y auto-close vigente.
- Historial: hoy, fecha histórica, límites, corrección y revisión auditada.
- Evidencia: existente, faltante y ruta no autorizada.
- Excel: válido, inválido, duplicado y sin match.
- Frontend: login, polling, entrada/salida, historial, sightings y Excel.
- Operación: import del entrypoint, health y smoke sin reinicios incidentales.

## Propuesta técnica por tandas

### Tanda 1 — Caracterización

Inventariar OpenAPI/consumidores y crear pruebas sin mover código.

### Tanda 2 — Composición

Extraer `main`, `core/config`, `core/security` y `core/lifespan`, manteniendo un
alias compatible para el entrypoint actual.

### Tanda 3 — ALPR

Extraer engine, preprocessing, validation, consensus y modelos. Mantener
`detect.run_multi_strategy` como fachada delegante.

### Tanda 4 — HTTP

Extraer routers/schemas de detección, parking, historial y estadísticas.
Conservar los routers existentes mientras se adelgazan.

### Tanda 5 — Servicios

Introducir casos de uso y mover coordinación fuera de handlers sin modificar
resultados.

### Tanda 6 — Repositorios

Separar persistencia por dominio conservando transacciones y fachadas.

### Tanda 7 — Cierre

Eliminar imports circulares y wrappers sin consumidores; ejecutar regresión,
smoke, deploy controlado y rollback verificado.

## Dependencias

- Precede a HU-007 como frontera recomendada, pero no la habilita.
- No depende de cambios frontend.
- Requiere coordinarse con HU-004 para no mover y cambiar simultáneamente el
  mismo flujo de ingesta.

## Evidencia de implementación

- Commit/PR: pendiente.
- OpenAPI base/final: pendiente.
- Verificaciones: pendientes.
- Deploy/rollback: pendientes.
