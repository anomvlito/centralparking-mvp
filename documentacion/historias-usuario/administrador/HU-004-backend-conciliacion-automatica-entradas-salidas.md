# HU-004 — Conciliar detecciones particulares en estadías

**Actor:** `administrador`
**Estado:** `en-progreso`
**Feature relacionada:** [Estadías conciliadas desde detecciones](../../features/in-progress/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#22](https://github.com/anomvlito/centralparking-mvp/issues/22)
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In progress` / `In Progress`
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

Esta HU reemplaza el modelo conceptual `ParkedCar → tres columnas` por:

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

- [ ] Cada detección válida genera un `DetectionEvent` con ID, texto detectado,
  normalización, confianza, timestamp, fuente e imagen, aunque quede sin match.
- [ ] Una detección incierta no abre, cierra, cobra ni sanciona automáticamente.
- [ ] La dirección vertical es evidencia secundaria; `UNKNOWN` es válido y no
  impide conservar ni conciliar manualmente una detección.
- [ ] El texto/confianza originales nunca se sobrescriben por una corrección o
  match posterior.
- [ ] Dos detecciones pueden conciliarse manualmente aunque las patentes no
  sean idénticas; queda `match_type=MANUAL` y una patente resuelta explícita.
- [ ] La salida debe ser posterior a la entrada; IDs inexistentes, iguales,
  ya consumidos o temporalmente incoherentes se rechazan de forma atómica.
- [ ] Una detección sólo puede ocupar un rol en una estadía no anulada.
- [ ] `duration_minutes` se calcula en backend únicamente para estadías
  completas y nunca es negativa.
- [ ] Un match exacto/difuso puede proponer una conciliación, pero los casos
  bajo el umbral permanecen `UNMATCHED` para revisión.
- [ ] Descartar no borra evidencia ni imágenes.
- [ ] Los endpoints requieren la autenticación vigente y no exponen rutas
  internas de filesystem.
- [ ] `CarsResponse` conserva literalmente `Record<string, ParkedCar>` con
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
sobre sesiones. Historial, Excel, auth, FTP y el dashboard anterior deben
seguir disponibles durante la transición.

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

- Commit/PR: pendiente.
- Deploy y smoke: pendientes.
