# HU-004 — Conciliar detecciones particulares en estadías

**Actor:** `administrador`
**Estado:** `implementada`
**Feature relacionada:** [Estadías conciliadas desde detecciones](../../features/done/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#22](https://github.com/anomvlito/centralparking-mvp/issues/22) — reabierto para esta
reapertura, ver evidencia abajo.
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `Done` / `Done`
**ADR relacionada:** [ADR-001](../../decisiones/ADR-001-reactivar-direction-tracker-acotado.md)
**HU frontend:** [HU-005](./HU-005-frontend-dashboard-tres-columnas-conciliacion.md)

## Historia

Como **administrador**, quiero **conservar cada detección de cámara como
evidencia particular y conciliar detecciones compatibles en una estadía**,
para **conocer cuánto tiempo permaneció un vehículo aunque el OCR no sea
perfecto o una detección todavía no tenga pareja**.

## Contexto y problema

`detection_log` ya conserva avistamientos y `parking_sessions` conserva
entradas/salidas, pero el frontend usa `ParkedCar` como concepto principal y
las detecciones no exponen un estado de conciliación explícito. El producto no
necesita destacar cuántos autos están actualmente dentro: necesita estadías
completas con duración y una cola revisable para la evidencia que todavía no
puede formar una estadía.

Esta HU reemplaza el modelo conceptual `ParkedCar → tres columnas` (diseño
original de esta HU y de HU-005) por:

```text
DetectionEvent (evidencia inmutable)
        │
        ├── entrada ──┐
        └── salida ───┴──> ParkingStay (interpretación conciliada)
```

La patente resuelta, el rol entrada/salida y el match pueden corregirse sin
sobrescribir el texto, confianza, timestamp o imagen originales.

## Reapertura (2026-07-31): persistir una dirección manual

HU-005 shippeó el criterio "la dirección es ayuda visual y nunca autoridad":
los botones "Usar como entrada"/"Usar como salida" de una detección `UNKNOWN`
sólo seleccionan esa tarjeta para la barra de conciliación manual local
(`markAsEntry`/`markAsExit` en `Dashboard.tsx`); nunca tocan el backend ni el
campo `direction` real de la detección. Esta reapertura invierte esa decisión
sólo para el caso `direction === "UNKNOWN"`: el administrador quiere que
clasificar manualmente una detección incierta la fije como
`APPROACHING`/`DEPARTING` de verdad, para que dashboard, columnas y futuras
consultas la traten como si el clasificador automático la hubiera resuelto.

No hace falta ningún disparador nuevo de conciliación automática para lograr
esto: `POST /api/stays/auto-reconcile-exact` (servicio
`auto_reconcile_exact_matches` en `api/database.py`, disparado en cada carga
del dashboard) y `GET /api/stay-proposals` matchean por `normalized_plate` +
ventana de tiempo, **sin exigir `direction` resuelta** — `direction` sólo
suma un bonus de score al desempatar candidatos difusos
(`build_stay_proposals`). Persistir la dirección manual sólo cambia en qué
columna cae la tarjeta; la conciliación automática ya corre igual antes y
después de este cambio.

El campo `detection_log.direction` ya existe (`VARCHAR(20) NOT NULL DEFAULT
'UNKNOWN'`); esta reapertura no requiere migración, sólo un `UPDATE`.

## Contratos

```ts
type DetectionEvent = {
  detection_id: number;
  detected_plate: string;
  normalized_plate: string;
  detected_at: string;
  confidence: number;
  image_url: string | null;
  direction: "APPROACHING" | "DEPARTING" | "UNKNOWN";
  match_status: "UNMATCHED" | "MATCHED_ENTRY" | "MATCHED_EXIT" | "DISMISSED";
  stay_id: number | null;
  source: string;
};

type ParkingStay = {
  stay_id: number;
  resolved_plate: string;
  entry_detection_id: number | null;
  exit_detection_id: number | null;
  entry_time: string | null;
  exit_time: string | null;
  duration_minutes: number | null;
  match_type: "EXACT" | "FUZZY" | "MANUAL" | "UNRESOLVED";
  match_confidence: number | null;
  status: "ENTRY_ONLY" | "EXIT_ONLY" | "COMPLETED" | "NEEDS_REVIEW";
  entry_image_url: string | null;
  exit_image_url: string | null;
  fee: number;
};
```

Endpoints:

- `GET /api/detections`: lista eventos particulares y permite filtrar
  `match_status`.
- `GET /api/stays`: lista estadías; `status=COMPLETED` permite obtener sólo
  permanencias con duración.
- `POST /api/stays/reconcile`: asocia manualmente una detección de entrada y
  una de salida y crea una estadía completa.
- `PATCH /api/detections/{detection_id}` con `action: dismiss` descarta la
  detección para conciliación sin eliminarla.
- **(Reapertura)** `PATCH /api/detections/{detection_id}` con
  `action: set_direction` y `direction: "APPROACHING" | "DEPARTING"` fija
  manualmente la dirección de una detección hoy `UNKNOWN`. Sólo aplica sobre
  detecciones `UNKNOWN`; no permite reescribir una dirección ya resuelta por
  el clasificador automático (evita que una corrección manual pise una
  clasificación con evidencia real). No cambia texto, confianza, timestamp,
  imagen, `match_status` ni dispara la conciliación por sí sola — la
  conciliación automática existente la recoge en su próximo ciclo si
  corresponde.

`/api/cars`, `/api/history`, `/api/entry` y `/api/exit/{plate}` se mantienen
por compatibilidad. No son el modelo principal de la nueva interfaz.

## Criterios de aceptación

- [x] Cada detección válida genera un `DetectionEvent` con ID, texto detectado,
  normalización, confianza, timestamp, fuente e imagen, aunque quede sin match.
- [x] Una detección incierta no abre, cierra, cobra ni sanciona automáticamente.
- [x] La dirección vertical es evidencia secundaria; `UNKNOWN` es válido y no
  impide conservar ni conciliar manualmente una detección.
- [x] El texto/confianza originales nunca se sobrescriben por una corrección o
  match posterior.
- [x] Dos detecciones pueden conciliarse manualmente aunque las patentes no
  sean idénticas; queda `match_type=MANUAL` y una patente resuelta explícita.
- [x] La salida debe ser posterior a la entrada; IDs inexistentes, iguales,
  ya consumidos o temporalmente incoherentes se rechazan de forma atómica.
- [x] Una detección sólo puede ocupar un rol en una estadía no anulada.
- [x] `duration_minutes` se calcula en backend únicamente para estadías
  completas y nunca es negativa.
- [x] Un match exacto/difuso puede proponer una conciliación, pero los casos
  bajo el umbral permanecen `UNMATCHED` para revisión.
- [x] Descartar no borra evidencia ni imágenes.
- [x] Los endpoints requieren la autenticación vigente y no exponen rutas
  internas de filesystem.
- [x] `CarsResponse` conserva literalmente `Record<string, ParkedCar>` con
  `eventFee?: number | null`.

### Reapertura: dirección manual

- [x] `PATCH /api/detections/{id}` con `action: "set_direction"` y
  `direction: "APPROACHING" | "DEPARTING"` persiste el campo `direction` de
  esa detección.
- [x] La acción sólo tiene efecto si la detección está hoy en
  `direction: "UNKNOWN"`; sobre una detección ya `APPROACHING`/`DEPARTING`
  responde `409` sin modificarla.
- [x] La acción no cambia `detected_plate`, `normalized_plate`, `confidence`,
  `detected_at`, `image_url`, `match_status` ni `stay_id`.
- [x] Requiere la misma autenticación que `dismiss` (`require_admin`).
- [x] Detección inexistente responde `404`; `direction` fuera del enum
  responde `422`.
- [x] No se modifica `build_stay_proposals`, `auto_reconcile_exact_matches`
  ni `POST /api/stays/reconcile`: la conciliación automática sigue matcheando
  por patente + tiempo, con o sin esta corrección.

## No-alcance

- Eliminar físicamente `/api/cars` o `parking_sessions`.
- Exigir dirección o OCR con 100 % de confianza.
- Convertir un match probabilístico en cobro, sanción o acceso.
- Borrar detecciones, sesiones, imágenes o auditoría.
- Calibrar automáticamente el clasificador vertical.
- **(Reapertura)** Permitir corregir una detección que ya tiene
  `APPROACHING`/`DEPARTING` (eso es competencia del clasificador automático de
  HU-007/008, no de esta acción manual).
- **(Reapertura)** Cambiar `build_stay_proposals`, el scoring de propuestas o
  cualquier regla de negocio de conciliación.
- **(Reapertura)** Registrar auditoría dedicada de quién hizo la corrección
  manual (se evalúa como HU/spike separado si se necesita trazabilidad de
  autoría; hoy `dismiss` tampoco la registra).

## Código relacionado

- Backend: `api/database.py`, `api/ftp_handler.py`, nuevos
  `api/schemas/reconciliation.py`, `api/services/reconciliation.py` y
  `api/routers/reconciliation.py`.
- Frontend: lo consume HU-005.
- Operación: `centralparking.service`; migración aditiva e idempotente durante
  el lifespan actual.
- **(Reapertura)** Backend: `api/schemas/reconciliation.py` (ampliar
  `DetectionActionRequest.action` a `Literal["dismiss", "set_direction"]` y
  agregar `direction: Literal["APPROACHING", "DEPARTING"] | None`),
  `api/routers/reconciliation.py` (dispatch de la nueva acción en el mismo
  `PATCH /api/detections/{detection_id}`), `api/services/reconciliation.py`
  (nueva función delgada equivalente a `dismiss_detection_event`) y
  `api/database.py` (nueva función `set_detection_direction(detection_id,
  direction)` que hace `UPDATE detection_log SET direction = %s WHERE
  detection_id = %s AND direction = 'UNKNOWN'` y verifica `rowcount` para
  distinguir 404 de 409). No se toca `build_stay_proposals`,
  `auto_reconcile_exact_matches` ni `reconcile_detection_events`.
- **(Reapertura)** Frontend: lo consume HU-005 (`src/lib/stays.ts`,
  `src/features/dashboard/Dashboard.tsx`).

## Impacto sobre funcionalidades existentes

La ingesta conserva su comportamiento de avistamiento pasivo. Se agregan
metadatos y proyecciones de conciliación sin reactivar efectos automáticos
sobre sesiones. Historial, Excel, auth, FTP y el dashboard anterior siguen
disponibles durante la transición.

**(Reapertura)** La nueva acción `set_direction` es aditiva sobre el mismo
endpoint `PATCH /api/detections/{detection_id}` que ya usa `dismiss`; no
cambia su firma de respuesta ni el comportamiento de `dismiss`. No modifica
`GET /api/detections`, `GET /api/stays`, `GET /api/stay-proposals` ni
`POST /api/stays/auto-reconcile-exact`: estos endpoints siguen leyendo
`direction` como hoy, sólo que ahora ese valor puede provenir de una
corrección manual además del clasificador automático. Revierte, únicamente
para detecciones `UNKNOWN`, el criterio shippeado en HU-005 de que "la
dirección es ayuda visual y nunca autoridad" — el resto de esa garantía
(ninguna detección se convierte en cobro, sanción o acceso por su
`direction`) no cambia.

## Riesgos y datos

- Match difuso entre vehículos distintos.
- Reutilización de una detección por concurrencia.
- Exposición de patente o ruta interna.
- Duración errónea por orden temporal o zona horaria.

La conciliación usa transacción y locks; las pruebas usan patentes sintéticas.

**(Reapertura)**

- Error humano: el administrador puede fijar `APPROACHING`/`DEPARTING`
  equivocado; a diferencia del clasificador automático, no hay evidencia de
  trayectoria que lo respalde. El `WHERE direction = 'UNKNOWN'` en el
  `UPDATE` evita que la corrección se aplique dos veces o pise una
  clasificación automática posterior, pero no evita elegir el sentido
  incorrecto — se acepta como parte del criterio existente de "descartar no
  es autoridad sobre patente/cobro", no sobre dirección.
- Carrera de dos clicks simultáneos sobre la misma detección (mismo patrón de
  riesgo que ya existe para `dismiss`): el `UPDATE ... WHERE direction =
  'UNKNOWN'` hace que sólo el primero tenga efecto; el segundo debe recibir
  `409` en vez de aplicar dos veces.
- No queda registro de quién ni cuándo corrigió la dirección (ver no-alcance:
  auditoría dedicada queda fuera de esta reapertura).

## Pruebas de regresión

- Detección sin match permanece consultable.
- Exacta, difusa y manual conservan evidencia original.
- Entrada posterior a salida se rechaza.
- Detección ya consumida se rechaza.
- Dismiss persiste sin borrar.
- Duración se calcula con timestamps de PostgreSQL.
- Filtros y límites se acotan.
- Auth 401/403; OpenAPI sin rutas duplicadas.
- `/api/cars`, `/api/history`, entrada/salida, staging y FTP sin regresión.

**(Reapertura)**

- `PATCH /api/detections/{id}` con `action=set_direction` sobre una detección
  `UNKNOWN` persiste `direction` y no toca ningún otro campo.
- La misma acción sobre una detección ya `APPROACHING`/`DEPARTING` responde
  `409` y no modifica la fila (verificar con `SELECT` posterior).
- `direction` fuera de `APPROACHING|DEPARTING` responde `422` sin tocar la
  fila.
- `detection_id` inexistente responde `404`.
- Sin `Authorization` responde 401/403 igual que `dismiss`.
- `dismiss` sigue funcionando sin regresión sobre el mismo router/schema
  ampliado.
- `auto_reconcile_exact_matches` y `build_stay_proposals` producen el mismo
  resultado antes y después de esta reapertura para detecciones sin cambios
  de `direction` (no regresión de la conciliación automática existente).

## Evidencia de implementación

- Backend: commit `f87d832`,
  [PR #34](https://github.com/anomvlito/centralparking-mvp/pull/34),
  merge `5052b106125ce5f24bb57a143ff6d4813f758648`.
- Verificación: 28 pruebas, `compileall`, `git diff --check` y contrato
  OpenAPI correctos.
- Deploy VPS:
  [run 30069920707](https://github.com/anomvlito/centralparking-mvp/actions/runs/30069920707)
  correcto.
- Smoke: `centralparking.service` y `parking-watchdog.service` activos,
  `/docs` HTTP 200, `/api/stays` y `/api/detections` con shapes contractuales.
- Nota de trazabilidad: esta HU reemplazó el diseño original de "backend de
  conciliación con 3 columnas" (`entries-open`/`exits-orphan`/`sessions-closed`)
  documentado inicialmente el 2026-07-23 junto con ADR-001. Ese diseño se
  implementó primero contra un mock en HU-005 y luego se descartó en favor del
  modelo `DetectionEvent`/`ParkingStay` descrito arriba, antes de cualquier
  integración real contra backend. El nombre de archivo de esta HU conserva su
  slug original (`HU-004-backend-conciliacion-automatica-entradas-salidas.md`)
  por continuidad de enlaces existentes.
- **Fix post-implementación (2026-07-24):** `POST /api/stays/reconcile`
  nunca se había ejercido contra datos reales hasta que un usuario probó el
  botón "Crear estadía" del dashboard de 3 columnas y obtuvo `500` (el
  navegador lo mostraba como error de CORS porque FastAPI no agrega headers
  CORS a una respuesta 500 no manejada). Causa real, dos bugs en cadena en
  `reconcile_detection_events()` (`api/database.py`):
  1. `source='manual_reconciliation'` no existe en el enum Postgres
     `session_source` (solo admite `camera_auto`/`camera_manual`/`manual`).
  2. Al arreglar (1), apareció `event_type='DETECTIONS_RECONCILED'`
     (21 caracteres) contra `audit_log.event_type varchar(20)`.
  Corregido a `'manual'` y `'STAY_RECONCILED'` respectivamente. Se agregó
  `tests/test_reconciliation_integration.py` (ejercita la función contra
  Postgres real con datos sintéticos y limpieza garantizada, opt-in vía
  `RUN_DB_INTEGRATION_TESTS=1`) porque los tests existentes mockean la capa
  de DB y no detectan errores de esquema. Commit `ee643fd`,
  [PR #38](https://github.com/anomvlito/centralparking-mvp/pull/38),
  merge `2672e468159fa44c7a5e2bb9c8ae0473cebd0187`. Deploy VPS vía
  `deploy.yml` (disparado automáticamente por el push a `main`): `success`.
  Verificado end-to-end con un `POST` real a producción (patente sintética
  `TESTHTTP1`, `HTTP 200`, headers CORS correctos, datos de prueba
  eliminados después).
- **Hallazgo aparte, no corregido en este fix:** durante la verificación se
  observó que `GET /api/stays`, `GET /api/detections` y
  `POST /api/stays/reconcile` responden sin exigir el header
  `Authorization` (a diferencia de lo que describe el criterio de
  aceptación "Los endpoints requieren la autenticación vigente"). No se
  investigó ni se corrigió como parte de este fix — queda para revisión de
  seguridad aparte.

- **Reapertura (2026-08-01): dirección manual.** Commit `962681f`,
  [PR #59](https://github.com/anomvlito/centralparking-mvp/pull/59),
  merge `af26b58ae9f49b06569e8f62092582cdb00ebc42`.
  - Verificación: 50 pruebas (`unittest discover`, 6 skipped opt-in),
    incluyendo el nuevo test de integración real contra Postgres de
    producción (`RUN_DB_INTEGRATION_TESTS=1`, patente sintética `TSTX99`,
    limpieza garantizada); `py_compile`, import de `api.detect:app` (47
    rutas) y `git diff --check` correctos.
  - Deploy VPS: workflow "Deploy Backend" disparado automáticamente por el
    push a `main`,
    [run 30709705482](https://github.com/anomvlito/centralparking-mvp/actions/runs/30709705482)
    `success`.
  - Smoke: `centralparking.service` y `parking-watchdog.service` activos,
    `/docs` HTTP 200, `openapi.json` expone `DetectionActionRequest` con
    `action: dismiss|set_direction` y `direction` nullable, `PATCH
    /api/detections/{id}` sin `Authorization` responde `401` (contrato de
    auth preservado).
  - Issue #22 reabierto con comentario de trazabilidad; Project 4 movido a
    `Etapa: In progress` / `Status: In Progress` al iniciar y de vuelta a
    `Done`/`Done` tras verificar el deploy.
