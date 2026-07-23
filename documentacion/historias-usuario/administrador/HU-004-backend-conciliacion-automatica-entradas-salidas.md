# HU-004 — Backend: conciliación automática de entradas y salidas

**Actor:** `administrador`
**Estado:** `backlog`
**Feature relacionada:** [Conciliación automática de entradas y salidas](../../features/backlog/conciliacion-automatica-entradas-salidas.md)
**Issue:** pendiente
**Project 4:** pendiente
**Creado por:** Francisco

## Historia

Como **administrador**, quiero **que el backend asocie automáticamente cada
detección de cámara con la sesión de estacionamiento correspondiente
(entrada o salida) y exponga por separado los casos que aún no logró
conciliar**, para **dejar de depender exclusivamente del registro manual del
operador y darle al frontend los datos necesarios para construir una vista de
conciliación** (ver [HU-005 — Frontend: dashboard de tres columnas](./HU-005-frontend-dashboard-tres-columnas-conciliacion.md)).

## Contexto y problema

Hoy la apertura y cierre de sesión es 100% manual: el operador presiona
"Registrar entrada" o "Registrar salida" (`RegisterActions`,
`adyac-camaras-frontend/src/app/page.tsx`) para cada avistamiento de cámara.
No existe hoy el concepto de "salida sin entrada asociada": `POST
/api/exit/{plate}` devuelve `404` si la patente no tiene una sesión abierta
(`vehicle_exists`), así que un avistamiento de salida sin entrada previa
simplemente no se puede registrar.

Además, la clasificación automática de dirección (`api/direction_tracker.py`,
`DirectionTracker`) existe en el código pero está desconectada desde
2026-07-17: usaba señal geométrica (posición/tamaño de la patente en 2-3
frames) para decidir entrada/salida de **cada** detección, y producía salidas
falsas (con la peor foto de la ráfaga) y duplicados. Esta HU la reactiva, pero
acotada solo al caso ambiguo — ver "Propuesta técnica".

Esta HU cubre exclusivamente el backend (algoritmo de matching + endpoints).
La vista de tres columnas que consume estos datos es una HU aparte para no
acoplar ambos repos en una sola entrega.

## Criterios de aceptación

- [ ] El backend intenta asociar automáticamente cada detección de salida con
  una sesión abierta (match exacto o difuso por patente, reutilizando
  `find_similar_active_session`) antes de considerarla "sin entrada".
- [ ] Cuando hay match, la sesión se cierra automáticamente
  (`remove_vehicle`, guarda `exit_image_path`).
- [ ] Cuando no hay sesión abierta que matchee, el backend usa
  `DirectionTracker` (reactivado, acotado a este caso ambiguo) para decidir
  si crea una entrada nueva (`APPROACHING`/`UNKNOWN`) o una salida sin entrada
  pendiente de revisión (`DEPARTING`), insertada en `orphan_exits`.
- [ ] Existen `GET /api/dashboard/entries-open`, `GET
  /api/dashboard/exits-orphan` (solo `status='PENDING'` por defecto) y `GET
  /api/dashboard/sessions-closed`, con los shapes definidos en "Propuesta
  técnica".
- [ ] Existe `PATCH /api/dashboard/exits-orphan/{id}` con `action: match`
  (cierra la sesión indicada de forma transaccional y marca el orphan como
  `MATCHED`) y `action: dismiss` (marca `DISMISSED` sin borrar la fila).
- [ ] Un `session_id` cerrado nunca vuelve a aparecer en
  `entries-open`; un `orphan_exit` `MATCHED`/`DISMISSED` nunca vuelve a
  aparecer en `exits-orphan` — ambos endpoints solo devuelven lo realmente
  pendiente de conciliar.
- [ ] Ninguna clasificación automática (`DEPARTING`/`APPROACHING`) cobra,
  cierra ni sanciona de forma autoritativa sin quedar disponible para
  revisión/corrección manual.

## No-alcance

- No incluye cambios de UI del Dashboard — eso es HU-005.
- No modificar `/api/stats`, Historial ni Reconciliación de Excel
  (`api/excel.py` — funcionalidad distinta, no confundir con esta
  conciliación automática de entradas/salidas).
- No reemplazar ni modificar el contrato de `/api/cars` ni de `/api/history`
  (se usan hoy en el frontend; se preservan sin cambios; los nuevos
  endpoints son adicionales).
- No borrar filas de `orphan_exits` al descartar (`dismiss`); solo se
  excluyen de la vista por defecto.
- No implementar cobro o sanción automática a partir de una clasificación
  `DEPARTING`/`APPROACHING` sin revisión humana.
- No tocar credenciales, servicios del VPS, ni desplegar como parte de esta
  etapa de creación de HU.

## Código relacionado

- Backend:
  - `api/ftp_handler.py::_handle_auto_detection` — pasa de solo loguear
    avistamiento a decidir y ejecutar entrada/salida automática según el
    algoritmo descrito en "Propuesta técnica".
  - `api/direction_tracker.py` — reactivar `DirectionTracker`, acotado a
    desempatar solo el caso sin sesión abierta que matchee (no decide
    dirección del 100% de las detecciones, a diferencia de su uso original).
  - `api/database.py` — nueva tabla `orphan_exits`; nuevas funciones de
    consulta para las 3 columnas y para fusionar entrada+salida de una
    sesión cerrada.
  - `api/detect.py` (o un nuevo router de dashboard) — nuevos endpoints
    `GET /api/dashboard/entries-open`, `GET /api/dashboard/exits-orphan`,
    `GET /api/dashboard/sessions-closed`,
    `PATCH /api/dashboard/exits-orphan/{id}`, y opcionalmente
    `GET /api/dashboard` combinado.
- Frontend: no requiere cambios en esta HU — ver HU-005.
- Operación: no requiere cambios.

## Contratos que deben preservarse

- `/api/cars` y su contrato actual (usado por `Historial` y `App` para el set
  de patentes parqueadas).
- `/api/history` sin cambios (Historial sigue funcionando igual);
  `/api/dashboard/sessions-closed` es adicional, no un reemplazo.
- `/api/entry` y `/api/exit/{plate}` mantienen su contrato manual actual como
  vía de respaldo para el operador.
- Trazabilidad imagen–avistamiento–sesión: ninguna fila de `orphan_exits` se
  borra al descartarse.

## Impacto sobre funcionalidades existentes

Cambia el comportamiento de ingesta de cámara: hoy toda detección queda como
avistamiento pasivo (`STAGED`) sin tocar `parking_sessions`; con esta HU, la
ingesta puede abrir/cerrar sesiones automáticamente. Esto afecta directamente
el pipeline FTP (`api/ftp_handler.py`) y por lo tanto todo el flujo de
detección en producción — no es un cambio aislado, requiere pruebas
controladas antes de habilitarlo contra la cámara real.

## Riesgos y datos

- **Riesgo alto:** `DirectionTracker` ya se desconectó una vez (2026-07-17)
  por generar salidas falsas y duplicados. Aunque esta HU acota su uso solo
  al caso ambiguo (sin sesión abierta que matchee) y sus resultados siempre
  quedan en cola de revisión (no cobran ni cierran autoritativamente), los
  umbrales (`DIRECTION_MIN_DISPLACEMENT`, `DIRECTION_MIN_CONSISTENCY`,
  `DIRECTION_AXIS`, `DIRECTION_ENTRY_SIGN`) deben re-validarse con
  fotos/video reales antes de confiar en la clasificación `DEPARTING`.
- Cambiar la ingesta automática de "solo avistamiento" a "abre/cierra
  sesión" es un cambio de comportamiento en producción con datos reales de
  patentes — requiere pruebas controladas antes de habilitarlo contra la
  cámara real.
- Sin implicancia de borrado de evidencia: `orphan_exits` nunca se borra,
  solo cambia de estado.

## Pruebas de regresión

- Historial: sigue mostrando el feed cronológico sin cambios, `/api/history`
  intacto.
- `/api/cars`: sigue devolviendo el mismo shape.
- Login, Reconciliación de Excel: sin cambios.
- Casos de prueba nuevos a definir con datos reales/sintéticos:
  - Entrada seguida de salida de la misma patente con sesión abierta → cierra
    automáticamente, aparece en `sessions-closed`, desaparece de
    `entries-open`.
  - Salida detectada sin sesión abierta y `DirectionTracker` = `DEPARTING` →
    aparece en `exits-orphan`, no crea entrada falsa.
  - Salida detectada sin sesión abierta y `DirectionTracker` =
    `APPROACHING`/`UNKNOWN` → abre entrada nueva, aparece en
    `entries-open`.
  - `PATCH .../match` → sesión se cierra, ambos desaparecen de sus endpoints
    de pendientes, el par aparece en `sessions-closed`.
  - `PATCH .../dismiss` → desaparece de `exits-orphan`, la fila persiste en
    BD con `status='DISMISSED'`.

## Propuesta técnica

1. Crear tabla `orphan_exits` (`id, plate, exit_time, exit_image_path,
   confidence, status ('PENDING'|'MATCHED'|'DISMISSED'), matched_session_id`
   FK nullable a `parking_sessions`, `created_at`).
2. Modificar `_handle_auto_detection` para ejecutar el algoritmo de match
   automático:
   - buscar sesión abierta para la patente (match exacto o difuso vía
     `find_similar_active_session`);
   - si hay match → cerrar esa sesión (`remove_vehicle`, guarda
     `exit_image_path`);
   - si no hay match → consultar `DirectionTracker.record(plate, center_x,
     center_y, size)` con las muestras de este pase de cámara:
     `APPROACHING`/`UNKNOWN` → abrir entrada nueva (`upsert_vehicle`);
     `DEPARTING` → insertar en `orphan_exits`.
3. Exponer los siguientes endpoints —

   `GET /api/dashboard/entries-open`:
   ```json
   [{ "session_id": 123, "plate": "ABCD12",
      "entry_time": "2026-07-23T10:15:00-04:00",
      "entry_image_url": "https://.../api/monitor/file/..." }]
   ```

   `GET /api/dashboard/exits-orphan` (por defecto solo `status='PENDING'`):
   ```json
   [{ "orphan_exit_id": 45, "plate": "XYZT99",
      "exit_time": "2026-07-23T11:02:00-04:00",
      "exit_image_url": "https://.../api/monitor/file/...",
      "confidence": 0.81, "status": "PENDING" }]
   ```

   `GET /api/dashboard/sessions-closed` (fusiona `parking_sessions` cerradas
   por `session_id` — hoy `/api/history` las devuelve como 2 filas separadas
   ENTRY+EXIT):
   ```json
   [{ "session_id": 118, "plate": "LMNQ34",
      "entry_time": "...", "entry_image_url": "...",
      "exit_time": "...", "exit_image_url": "...",
      "duration_minutes": 47, "fee": 1300 }]
   ```

   `PATCH /api/dashboard/exits-orphan/{orphan_exit_id}` (mismo patrón que
   `review_session`/`correct_session_plate`):
   ```json
   { "action": "match", "session_id": 118 }
   ```
   Efecto transaccional: cierra la sesión `118` con
   `exit_time`/`exit_image_path`/`confidence` del `orphan_exit` (equivalente
   a `remove_vehicle`); marca `orphan_exits.status='MATCHED'`,
   `matched_session_id=118`.
   ```json
   { "action": "dismiss" }
   ```
   Marca `status='DISMISSED'`; la fila no se borra.

   Evaluar un `GET /api/dashboard` combinado (las 3 listas en una sola
   llamada) para que el frontend pueda mantener un único polling de 15s sin
   triplicar requests.
4. Re-validar/afinar umbrales de `DirectionTracker` con datos reales antes
   de habilitarlo contra producción.
5. Probar localmente (casos de la sección de regresión), y sólo entonces
   evaluar publicar — fuera del alcance de esta etapa de creación de HU.

## Evidencia de implementación

- Commit/PR: pendiente.
- Verificaciones: pendientes.
