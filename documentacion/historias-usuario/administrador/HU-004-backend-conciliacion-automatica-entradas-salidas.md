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

## Reapertura (2026-08-05): corregir o revertir una dirección ya resuelta

La reapertura anterior (2026-07-31) sólo permitía `UNKNOWN → APPROACHING` o
`UNKNOWN → DEPARTING`, una única vez (`WHERE direction = 'UNKNOWN'`). En
producción esto significaba que una detección mal clasificada — por el
clasificador automático o por un clic erróneo del administrador — quedaba
atascada de forma permanente en la columna equivocada (Entradas o Salidas
pendientes), sin ninguna forma de moverla ni de devolverla a "sin dirección
clara".

Esta reapertura relaja esa restricción: mientras la detección siga pendiente
de conciliación (`match_status = 'UNMATCHED'`), su `direction` puede
corregirse las veces que haga falta, incluyendo revertirla explícitamente a
`UNKNOWN`. Una vez que la detección fue consumida por una conciliación
(`match_status` pasa a `MATCHED_ENTRY`/`MATCHED_EXIT`/`DISMISSED`), la acción
se rechaza con `409` — corregir la dirección de una detección ya conciliada
en una estadía queda fuera de alcance (sería una corrección sobre la estadía,
no sobre la detección).

Esto también **reemplaza** el no-alcance que había fijado la reapertura
anterior ("permitir corregir una detección que ya tiene
`APPROACHING`/`DEPARTING` … no es competencia de esta acción manual"): con
esta reapertura sí lo es, siempre que la detección siga `UNMATCHED`.

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
- **(Reapertura 2026-07-31, ampliada 2026-08-05)** `PATCH
  /api/detections/{detection_id}` con `action: set_direction` y
  `direction: "APPROACHING" | "DEPARTING" | "UNKNOWN"` fija o corrige la
  dirección de una detección mientras siga `match_status = 'UNMATCHED'`,
  incluyendo revertirla a `UNKNOWN`. Responde `409` si la detección ya fue
  conciliada (`match_status != 'UNMATCHED'`). No cambia texto, confianza,
  timestamp, imagen ni `match_status`, y no dispara la conciliación por sí
  sola — la conciliación automática existente la recoge en su próximo ciclo
  si corresponde.

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

### Reapertura: dirección manual (2026-07-31)

- [x] `PATCH /api/detections/{id}` con `action: "set_direction"` y
  `direction: "APPROACHING" | "DEPARTING"` persiste el campo `direction` de
  esa detección.
- [x] La acción no cambia `detected_plate`, `normalized_plate`, `confidence`,
  `detected_at`, `image_url`, `match_status` ni `stay_id`.
- [x] Requiere la misma autenticación que `dismiss` (`require_admin`).
- [x] Detección inexistente responde `404`; `direction` fuera del enum
  responde `422`.
- [x] No se modifica `build_stay_proposals`, `auto_reconcile_exact_matches`
  ni `POST /api/stays/reconcile`: la conciliación automática sigue matcheando
  por patente + tiempo, con o sin esta corrección.

> El criterio "sólo tiene efecto sobre `UNKNOWN`; ya resuelta responde `409`"
> de esta sección quedó **superado** por la reapertura del 2026-08-05, ver
> abajo.

### Reapertura: corregir o revertir dirección (2026-08-05)

- [x] La acción tiene efecto mientras `match_status = 'UNMATCHED'`,
  sin importar el valor actual de `direction` (permite `APPROACHING →
  DEPARTING`, `DEPARTING → APPROACHING` y cualquier valor `→ UNKNOWN`).
- [x] `direction: "UNKNOWN"` es un valor válido del payload (reversión
  explícita a "sin dirección clara").
- [x] Una vez que `match_status != 'UNMATCHED'` (detección ya conciliada), la
  acción responde `409` con mensaje "ya fue conciliada" y no modifica la fila.
- [x] No se modifica `build_stay_proposals`, `auto_reconcile_exact_matches`
  ni `POST /api/stays/reconcile`.

## No-alcance

- Eliminar físicamente `/api/cars` o `parking_sessions`.
- Exigir dirección o OCR con 100 % de confianza.
- Convertir un match probabilístico en cobro, sanción o acceso.
- Borrar detecciones, sesiones, imágenes o auditoría.
- Calibrar automáticamente el clasificador vertical.
- **(Reapertura 2026-08-05)** Corregir la dirección de una detección ya
  conciliada en una estadía (`match_status != 'UNMATCHED'`) — eso requeriría
  deshacer la estadía, no sólo actualizar `direction`.
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
- **(Reapertura 2026-07-31)** Backend: `api/schemas/reconciliation.py`
  (ampliar `DetectionActionRequest.action` a
  `Literal["dismiss", "set_direction"]` y agregar
  `direction: Literal["APPROACHING", "DEPARTING"] | None`),
  `api/routers/reconciliation.py` (dispatch de la nueva acción en el mismo
  `PATCH /api/detections/{detection_id}`), `api/services/reconciliation.py`
  (nueva función delgada equivalente a `dismiss_detection_event`) y
  `api/database.py::set_detection_direction(detection_id, direction)`, que
  originalmente hacía `UPDATE detection_log SET direction = %s WHERE id = %s
  AND direction = 'UNKNOWN'`. No se toca `build_stay_proposals`,
  `auto_reconcile_exact_matches` ni `reconcile_detection_events`.
- **(Reapertura 2026-08-05)** `api/schemas/reconciliation.py` (agregar
  `"UNKNOWN"` al `Literal` de `direction`) y
  `api/database.py::set_detection_direction` (el `WHERE` pasa de
  `direction = 'UNKNOWN'` a `match_status = 'UNMATCHED'`; el mensaje del
  `ValueError` en el 409 pasa de "ya tiene una dirección resuelta" a "ya fue
  conciliada y no admite corrección de dirección"). Frontend:
  `src/lib/stays.ts::setDetectionDirection` (tipo ampliado a incluir
  `"UNKNOWN"`) y `src/features/dashboard/Dashboard.tsx`
  (`markAsEntry`/`markAsExit` persisten siempre que la dirección cambie en
  vez de sólo desde `UNKNOWN`; nuevo botón "Quitar dirección" en
  `DetectionCard` y función `resetDirection`).
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

**(Reapertura 2026-07-31, revisado 2026-08-05)**

- Error humano: el administrador puede fijar `APPROACHING`/`DEPARTING`
  equivocado; a diferencia del clasificador automático, no hay evidencia de
  trayectoria que lo respalde. Desde la reapertura del 2026-08-05 esto ya no
  es irreversible: mientras la detección siga `UNMATCHED`, puede corregirse
  o revertirse a `UNKNOWN` las veces que haga falta — se acepta como parte
  del criterio existente de "descartar no es autoridad sobre patente/cobro",
  no sobre dirección.
- Carrera de dos correcciones simultáneas sobre la misma detección (mismo
  patrón de riesgo que ya existe para `dismiss`): el `UPDATE ... WHERE
  match_status = 'UNMATCHED'` sigue acotando el efecto a detecciones
  pendientes; si la detección se concilia justo entre dos clicks, el segundo
  recibe `409` en vez de aplicar sobre una fila ya consumida. El clasificador
  automático no vuelve a evaluar `direction` después de la ingesta (no hay
  job recurrente que la reprocese), así que no compite con la corrección
  manual una vez hecha.
- No queda registro de quién ni cuándo corrigió la dirección, ni cuántas
  veces se corrigió (ver no-alcance: auditoría dedicada queda fuera de esta
  reapertura).

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

**(Reapertura 2026-08-05)**

- Una detección `UNMATCHED` admite corregir `direction` repetidamente
  (`APPROACHING → DEPARTING → UNKNOWN`), sin perder `detected_plate`,
  `confidence`, `detected_at`, `image_url` ni `match_status`.
- Tras `dismiss` (o cualquier transición que saque `match_status` de
  `UNMATCHED`), `set_direction` responde `409` y no modifica la fila.
- `detection_id` inexistente sigue respondiendo `404`.
- `dismiss` y el resto de acciones del router siguen sin regresión sobre el
  mismo schema ampliado.

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

- **Reapertura (2026-08-05): corregir o revertir dirección.** Commit
  `a754adf`, [PR #61](https://github.com/anomvlito/centralparking-mvp/pull/61),
  merge `78020f72fd46269e9d195d4ff0b901d66a0f59c7`.
  - Verificación: `unittest discover` 51 pruebas (7 skipped opt-in);
    `RUN_DB_INTEGRATION_TESTS=1` contra Postgres real con patente sintética
    `TSTX99` — corrección repetida `APPROACHING → DEPARTING → UNKNOWN` sobre
    la misma detección y rechazo `409` tras conciliarla (`dismiss`);
    `py_compile` y import de `api.detect:app` (49 rutas) correctos.
  - Deploy VPS: workflow "Deploy Backend" — el primer intento
    ([run 31039837652](https://github.com/anomvlito/centralparking-mvp/actions/runs/31039837652))
    falló por `dial tcp ***:22: i/o timeout` (timeout de SSH del runner hacia
    el VPS, no relacionado con el cambio; ya había un antecedente de la misma
    falla transitoria el 2026-08-03). El reintento (`gh run rerun --failed`)
    completó en 8s con `success`.
  - Smoke: `centralparking.service` y `parking-watchdog.service` activos,
    `/docs` HTTP 200, `openapi.json` expone `direction` con
    `enum: [APPROACHING, DEPARTING, UNKNOWN]` en `DetectionActionRequest`,
    `PATCH /api/detections/{id}` sin `Authorization` responde `401`.
  - Issue #22 reabierto con comentario de trazabilidad; Project 4 movido a
    `Etapa: In progress` / `Status: In Progress` al iniciar.

- **Fix post-implementación (2026-08-05): `logged_at` real al promover desde
  staging.** El administrador reportó desfases de minutos entre la hora que
  muestra el sistema, el nombre del archivo y la hora quemada en la imagen.
  Causa: `staging_promote_expired()` (`api/staging.py`) insertaba en
  `detection_log` vía `log_to_db()` sin pasar la hora real — la columna
  `logged_at` quedaba con el `DEFAULT now()` de Postgres, evaluado en el
  momento de la promoción (hasta ~150s después de la detección real, por el
  TTL de staging de 2 minutos + polling cada 30s), no en el momento real en
  que se guardó la mejor foto (`staging_detections.detected_at`, que sí es
  correcta). Confirmado con datos reales de producción (2000 detecciones):
  desfase sistemático de 120 a 155s (mediana 134s) en prácticamente el 100%
  de las detecciones automáticas, más un caso extremo de casi 2 horas
  (patente `KPBJ28`, 2026-08-03) que coincide con una ventana de deploy
  fallido seguido de uno exitoso — mientras el backend estuvo caído, el
  backlog de staging quedó congelado y se promovió todo de una vez al
  reiniciar, con `logged_at` igual a la hora de reinicio.
  Solución: `log_to_db()` acepta `logged_at` opcional
  (`COALESCE(%s, now())`, preservando `now()` para `ENTRY`/`EXIT`/`VOID`
  manuales) y `staging_promote_expired()` le pasa
  `staging_detections.detected_at`. Commit `846f0e7`,
  [PR #63](https://github.com/anomvlito/centralparking-mvp/pull/63),
  merge `292aec419d5fdcf5bbf4cd5dd9e2b3e4f0483926`.
  - Verificación: `unittest discover` 53 pruebas sin regresión; nuevo
    `tests/test_staging_logged_at.py` contra Postgres real
    (`RUN_DB_INTEGRATION_TESTS=1`) — detección sintética "de hace 3 horas"
    con `expires_at` ya vencido, promovida con `logged_at` a menos de 5s de
    la hora real (no de "ahora"), y `log_to_db` sin `logged_at` explícito
    sigue usando `now()`; `py_compile` e import de `api.detect:app` (49
    rutas) correctos.
  - Deploy VPS: [run 31044346512](https://github.com/anomvlito/centralparking-mvp/actions/runs/31044346512)
    `success`.
  - Verificación en producción con tráfico real: la primera detección
    posterior al deploy (patente `VXVD37`, id `10366`,
    `historico/2026-08-05/16-31-27_VXVD37_2026-08-05.jpg`) quedó con
    `logged_at` a **0.53 segundos** del nombre del archivo, contra los
    ~120-150s que hubiera tenido antes del fix.
  - Alcance: sólo detecciones futuras; no se hizo backfill del histórico ya
    promovido con timestamp incorrecto (se evalúa aparte si hace falta).
  - No se tocó Kanban/Project 4 para este fix (mismo criterio que el fix
    post-implementación del 2026-07-24): es una corrección de un bug del
    contrato `detected_at`/`logged_at` de `DetectionEvent`, no un cambio de
    alcance de la HU.

- **Fix post-implementación (2026-08-06): `detected_at` real del video (no
  la hora de fin de procesamiento) en `staging_submit()`.** El administrador
  reportó una sesión "completada" (misma patente registrada como entrada y
  salida) que en realidad era el mismo pase real capturado dos veces.
  Confirmado visualmente contra las imágenes reales: 5 sesiones del
  2026-08-06 (`VVHJ88`, `KXBH84`, `GPHD26`, `LHRG10`, `CVTG23`) mostraban el
  mismo vehículo, en la misma posición frente a la cámara SALIDA, con 0-30s
  de diferencia real (hora quemada en la imagen), pero separadas por 3-7
  minutos en `detection_log`.
  Causa: el fix del 2026-08-05 (arriba) resolvió el desfase entre
  `detected_at` (staging) y `logged_at` (promoción), pero no tocó cómo se
  fija `detected_at` para detecciones de **video**. `staging_submit()`
  insertaba esa columna con `DEFAULT now()` de Postgres, evaluado cuando se
  ejecuta — para video, eso es cuando `_process_ftp_video_and_register()`
  termina de procesar el `.mp4` completo (cientos de frames, ALPR
  multi-estrategia) detrás de un semáforo que serializa un video a la vez
  (`MAX_CONCURRENT_VIDEO_PROCESSING=1`). Si hay otros videos en cola, ese
  delay puede ser de varios minutos — no la hora real del pase. El sistema
  ya tenía una protección contra duplicados (`is_duplicate_duration()`,
  umbral de 120s) que debería haber descartado estos pares, pero el
  timestamp inflado por la cola superó el umbral y `auto_reconcile_exact_matches()`
  los concilió como una entrada+salida real. Confirmado con
  `journalctl -u centralparking.service`: el video que contenía la segunda
  detección de `VVHJ88` esperó detrás de otro video en la cola antes de
  procesarse.
  Solución: `_process_ftp_video_and_register()` captura el mtime del `.mp4`
  **antes** de entrar a la cola (el archivo ya llegó completo por FTP en ese
  punto — mejor proxy disponible a la hora real sin analizar frame a frame)
  y lo propaga como `detected_at` a través de `_handle_auto_detection()` →
  `staging_submit()` → `staging_detections` (`COALESCE(%s, now())`, mismo
  patrón que el fix anterior). El flujo de fotos no pasa `detected_at` — la
  subida es casi inmediata a la captura, sigue usando `now()`.
  Commit `ffa2c04`, [PR #65](https://github.com/anomvlito/centralparking-mvp/pull/65),
  merge `365577997341231bf07eb806d647a1ff6263ccab`.
  - Verificación: `unittest discover` 55 pruebas sin regresión (unit +
    `RUN_DB_INTEGRATION_TESTS=1` contra Postgres real); nuevo
    `tests/test_video_detected_at.py` — `staging_submit(detected_at=...)`
    preserva la hora explícita, sin `detected_at` sigue usando `now()`;
    `py_compile`, `git diff --check` e import de `api.detect:app` (49
    rutas) correctos.
  - Deploy VPS: [run 31108973883](https://github.com/anomvlito/centralparking-mvp/actions/runs/31108973883)
    `success`; `centralparking.service`/`parking-watchdog.service` activos,
    `/docs` HTTP 200, código desplegado en
    `/opt/services/centralparking/deploy/backend` confirmado en el commit
    del merge.
  - Corrección de datos: las 5 sesiones confirmadas del 2026-08-06 se
    marcaron `DUPLICATE`/`VOID` vía `review_session()` (mismo mecanismo
    auditado que usa un administrador desde el dashboard, `reviewed_by`
    asociado a la cuenta del administrador que autorizó la corrección) —
    ids `6631`, `6626`, `6646`, `6645`, `6651`. No se borró evidencia ni
    fotos; las sesiones quedan visibles con `status=VOID`.
  - Alcance: cubre el flujo FTP de video
    (`/api/ftp/video` → `_process_ftp_video_and_register`). Fuera de
    alcance: endpoint standalone `/api/video/upload`
    (`auto_register=True`, no pasa por staging); backfill del histórico
    previo a este fix más allá de las 5 sesiones confirmadas
    visualmente (no se asumió que las ~30 sesiones restantes con patrón
    similar detectadas en el barrido de 2-10 min fueran todas duplicados
    del mismo bug, sin confirmación visual).
  - No se tocó Kanban/Project 4 para este fix (mismo criterio que los dos
    fixes post-implementación anteriores).
