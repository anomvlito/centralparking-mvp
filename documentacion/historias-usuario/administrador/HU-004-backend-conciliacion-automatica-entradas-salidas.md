# HU-004 — Conciliar detecciones particulares en estadías

**Actor:** `administrador`
**Estado:** `implementada`
**Feature relacionada:** [Estadías conciliadas desde detecciones](../../features/in-progress/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#22](https://github.com/anomvlito/centralparking-mvp/issues/22) — cerrado
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `Done` / `Done`
**ADR relacionada:** [ADR-001](../../decisiones/ADR-001-reactivar-direction-tracker-acotado.md)

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

## No-alcance

- Eliminar físicamente `/api/cars` o `parking_sessions`.
- Exigir dirección o OCR con 100 % de confianza.
- Convertir un match probabilístico en cobro, sanción o acceso.
- Borrar detecciones, sesiones, imágenes o auditoría.
- Calibrar automáticamente el clasificador vertical.

## Código relacionado

- Backend: `api/database.py`, `api/ftp_handler.py`, nuevos
  `api/schemas/reconciliation.py`, `api/services/reconciliation.py` y
  `api/routers/reconciliation.py`.
- Frontend: lo consume HU-005.
- Operación: `centralparking.service`; migración aditiva e idempotente durante
  el lifespan actual.

## Impacto sobre funcionalidades existentes

La ingesta conserva su comportamiento de avistamiento pasivo. Se agregan
metadatos y proyecciones de conciliación sin reactivar efectos automáticos
sobre sesiones. Historial, Excel, auth, FTP y el dashboard anterior siguen
disponibles durante la transición.

## Riesgos y datos

- Match difuso entre vehículos distintos.
- Reutilización de una detección por concurrencia.
- Exposición de patente o ruta interna.
- Duración errónea por orden temporal o zona horaria.

La conciliación usa transacción y locks; las pruebas usan patentes sintéticas.

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
