# HU-005 — Dashboard de 3 columnas para conciliar entradas y salidas

**Actor:** `administrador`
**Estado:** `implementada`
**Feature relacionada:** [Estadías conciliadas desde detecciones](../../features/done/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#23](https://github.com/anomvlito/centralparking-mvp/issues/23) — reabierto para esta
reapertura, ver evidencia abajo.
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — cierre verificado después de producción
**HU backend:** [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)

## Historia

Como **administrador**, quiero **ver el Dashboard organizado en tres columnas
— entradas pendientes de salida, salidas pendientes de entrada y sesiones
completas — y poder resolver manualmente los casos que quedan ambiguos**,
para **tener una vista operativa clara de lo pendiente de conciliar, en vez de
una única tabla de estadías con una grilla plana de detecciones debajo**.

Además, quiero **seleccionar una fecha operativa que gobierne toda la vista**,
para **no mezclar pendientes de días distintos y encontrar las estadías que
estuvieron activas durante ese día**.

## Contexto y problema

Esta HU ya se implementó una vez (iteración "Estadías", ver evidencia abajo):
una tabla de estadías completas + una grilla única "Por conciliar" con botones
"Entrada"/"Salida"/"Descartar" por tarjeta. Esa iteración sigue funcionando y
se mantiene en producción sin cambios de contrato. Esta reapertura solo cambia
la **presentación** de esos mismos datos a un layout de 3 columnas, sin tocar
`src/lib/stays.ts` ni ningún endpoint backend.

Durante la investigación de esta reapertura se encontró un hallazgo
importante (ver "Riesgos y datos"): el campo `direction` de
`GET /api/detections` **siempre** vale `UNKNOWN` hoy en producción, porque
`api/staging.py::staging_promote_expired()` no propaga el resultado de
`direction_service.observe()` hacia `detection_log`. Esto significa que, hasta
que un spike de backend separado conecte ese wiring, las columnas 1 y 2 de
esta HU estarán casi siempre vacías y la franja de triage concentrará el
100% de la operación real — es un comportamiento esperado, no un bug de esta
HU.

La revisión operativa de 2026-07-28 detectó otra divergencia: el selector de
fecha comenzaba vacío, por lo que se mezclaban pendientes históricos, y
`GET /api/stays?date=...` asignaba una estadía completa exclusivamente al día
de salida mediante `COALESCE(exit_time, entry_time)`. Una estadía nocturna no
aparecía al revisar el día de entrada. La barra de conciliación quedaba al
final de la página y las columnas dirigidas ocultaban la acción contraria,
dificultando corregir manualmente una clasificación equivocada.

## Reapertura (2026-07-31): mover a pendientes al clasificar manualmente

**Reconciliación de un hallazgo ya resuelto:** la sección "Riesgos y datos"
de esta HU documenta que `direction` siempre valía `UNKNOWN` en producción
por un gap de wiring entre `staging.py` y `detection_log`. Ese gap está
resuelto desde el commit `07f3a58a` (2026-07-24, HU-010 "Activar el
clasificador vertical con evidencia suficiente", `implementada`): el
clasificador vertical automático ya escribe `direction` real cuando tiene
evidencia suficiente. En consecuencia, hoy columnas 1 y 2 sí reciben
detecciones reales y la franja de triage sólo concentra los casos donde el
clasificador automático no tuvo evidencia suficiente o la trayectoria fue
ambigua — ya no el 100% del tráfico. Esta reapertura actualiza esa sección
más abajo para reflejar el estado real.

**Nueva historia de esta reapertura:** Como **administrador**, quiero que al
resolver manualmente una detección de la franja de triage (`direction:
"UNKNOWN"`) con los botones `Entrada`/`Salida`, la tarjeta se mueva a
la columna de pendientes correspondiente (Entradas pendientes o Salidas
pendientes), para que la conciliación automática existente
(`auto_reconcile_exact_matches`, disparada en cada carga) la tome en su
próximo ciclo sin pasos adicionales.

Hoy esos mismos botones sobre una tarjeta de triage sólo la seleccionan para
la barra de conciliación manual local (`markAsEntry`/`markAsExit`); nunca
escriben `direction` en el backend. Con [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)
(reapertura, `PATCH /api/detections/{id}` con `action: "set_direction"`)
disponible, esta reapertura hace que esos mismos botones, **sólo cuando la
tarjeta es de triage (`direction === "UNKNOWN"`)**, además persistan la
dirección elegida antes o junto con la selección local. Esto invierte, sólo
para el caso `UNKNOWN`, el criterio shippeado más abajo "la dirección es
ayuda visual y nunca autoridad": a partir de esta reapertura, resolver
manualmente una detección incierta sí fija su `direction` real, tal como si
el clasificador automático la hubiera resuelto. El resto de esa garantía no
cambia — ninguna detección se convierte en cobro, sanción o acceso por su
`direction`, y sobre una tarjeta ya resuelta (columna 1 o 2) los botones
siguen comportándose exactamente igual que hoy (sólo selección local para la
barra de conciliación, sin escritura al backend — el propio backend
rechazaría con `409` un intento de sobrescribir una dirección ya resuelta).

## Reapertura (2026-08-05): corregir o revertir una tarjeta ya clasificada

La reapertura anterior (2026-07-31) sólo activaba `setDetectionDirection`
para tarjetas de triage (`direction === "UNKNOWN"`); sobre una tarjeta ya en
columna 1 o 2, los botones `Entrada`/`Salida` seguían siendo puramente
selección local. En producción esto significaba que una tarjeta mal
clasificada — por el clasificador automático o por un clic manual erróneo —
quedaba atascada en la columna equivocada sin ninguna forma de moverla ni de
devolverla a "Sin dirección clara".

Con el backend de esta misma reapertura en
[HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)
(`set_detection_direction` ahora acepta corregir mientras
`match_status = 'UNMATCHED'`, sin importar el valor actual, y admite
`"UNKNOWN"` como reversión), esta reapertura cambia el frontend para
aprovecharlo:

- `markAsEntry`/`markAsExit` ahora llaman a `setDetectionDirection` siempre
  que la tarjeta vaya a cambiar de dirección (no sólo desde `UNKNOWN`): un
  clic en `Salida` sobre una tarjeta de "Entradas pendientes" la mueve a
  "Salidas pendientes".
- Nuevo botón `Quitar dirección` en `DetectionCard`, visible únicamente en
  tarjetas ya clasificadas (columna 1 o 2), que llama a
  `setDetectionDirection(id, "UNKNOWN")` y devuelve la tarjeta a "Sin
  dirección clara".

Esto **reemplaza** el criterio y el no-alcance de la reapertura anterior que
decían que los botones sobre columnas 1/2 "no llaman al nuevo `PATCH`: sólo
actualizan la selección local" — eso ya no es así.

## Criterios de aceptación

- [x] Existe un único selector de fecha operativa, iniciado en la fecha actual
  de `America/Santiago`; al cambiarlo se recargan columnas, triage y sesiones
  completas con el mismo valor `YYYY-MM-DD`.
- [x] Junto al selector existen controles para avanzar o retroceder exactamente
  un día; el avance queda deshabilitado en la fecha operativa actual y el
  selector manual tampoco acepta fechas futuras.
- [x] Sin una acción explícita nunca se mezclan pendientes de todas las fechas.
- [x] Una estadía completa pertenece al día consultado cuando su intervalo
  `[entry_time, exit_time]` se solapa con cualquier instante de ese día en
  `America/Santiago`; una estadía nocturna puede aparecer en ambos días.
- [x] Una opción explícita permite incluir pendientes del día anterior para
  conciliar estadías nocturnas; se deduplican y no se cargan fechas anteriores.
- [x] El Dashboard muestra 3 columnas: (1) Entradas pendientes, (2) Salidas
  pendientes, (3) Sesiones completas.
- [x] Columna 1 y columna 2 se derivan client-side del mismo array que hoy
  trae `fetchUnmatchedDetections` (`GET /api/detections?match_status=UNMATCHED`):
  columna 1 = `direction === "APPROACHING"`, columna 2 = `direction === "DEPARTING"`.
- [x] Una franja de triage aparte (fuera de columnas 1 y 2) muestra las
  detecciones con `direction === "UNKNOWN"`, con ambos botones "Es entrada" /
  "Es salida" visibles — no se asignan por defecto a ninguna columna.
- [x] Toda detección ofrece `Usar como entrada`, `Usar como salida` y
  `Descartar`, incluso si `direction` sugiere un rol; la dirección es ayuda
  visual y nunca autoridad.
- [x] Columna 3 consume `GET /api/stays?status=COMPLETED` (`fetchStays`) y
  reutiliza el componente `StayEvidence` ya existente: evidencia de entrada a
  la izquierda, patente + duración al centro, evidencia de salida a la
  derecha.
- [x] Seleccionar una tarjeta como entrada (columna 1 o triage) y otra como
  salida (columna 2 o triage) habilita la barra de conciliación manual con
  patente resuelta editable → `POST /api/stays/reconcile` (sin cambios de
  lógica respecto a la iteración anterior).
- [x] La barra de conciliación permanece visible cerca de los filtros, permite
  limpiar la selección y explica por qué `Crear estadía` está deshabilitado.
- [x] Descartar una tarjeta (columna 1, 2 o triage) → `PATCH
  /api/detections/{id}` con `action: dismiss`, sin borrar el registro.
- [x] Tras conciliar o descartar, las 3 zonas se refrescan (mismo polling de
  `DASHBOARD_REFRESH_MS`, 15s).
- [x] El layout se adapta sin huecos ni columnas rotas en desktop y mobile
  (1 columna en mobile, 3 en desktop).

### Reapertura: mover a pendientes al clasificar manualmente (2026-07-31)

- [x] En la franja de triage, hacer clic en `Entrada` o `Salida` sobre
  una tarjeta `direction === "UNKNOWN"` llama a
  `PATCH /api/detections/{id}` con `action: "set_direction"` y la dirección
  correspondiente (`APPROACHING` para entrada, `DEPARTING` para salida),
  además de conservar la selección local existente para la barra de
  conciliación manual.
- [x] Tras una respuesta exitosa, la tarjeta refleja de inmediato (sin
  esperar el próximo polling) su nueva `direction` en el estado local y
  aparece en la columna de pendientes correspondiente (1 o 2) en vez de la
  franja de triage.
- [x] Si el `PATCH` falla (409, 404, error de red), la tarjeta permanece en
  la franja de triage, se muestra un error visible y la selección local para
  la barra de conciliación no se pierde.
- [x] `Descartar` sobre una tarjeta de triage sigue usando exclusivamente
  `action: "dismiss"`, sin relación con `set_direction`.
- [x] La barra de conciliación manual (`POST /api/stays/reconcile`) sigue
  funcionando igual que hoy para cualquier combinación de tarjetas
  seleccionadas, se haya persistido o no su `direction`.

> El criterio "sobre columna 1/2 los botones no llaman al `PATCH`" de esta
> sección quedó **superado** por la reapertura del 2026-08-05, ver abajo.

### Reapertura: corregir o revertir dirección (2026-08-05)

- [x] Sobre una tarjeta ya en columna 1 o 2, hacer clic en el botón contrario
  (`Salida` sobre una de "Entradas pendientes", o viceversa) llama a
  `setDetectionDirection` con la nueva dirección y mueve la tarjeta a la
  columna correcta de inmediato, sin esperar el polling.
- [x] Nuevo botón `Quitar dirección`, visible sólo cuando `direction !==
  "UNKNOWN"`, llama a `setDetectionDirection(id, "UNKNOWN")` y devuelve la
  tarjeta a "Sin dirección clara".
- [x] Hacer clic en el botón que ya coincide con la dirección actual de la
  tarjeta (ej. `Entrada` sobre una tarjeta ya `APPROACHING`) no dispara un
  `PATCH` redundante — sólo actualiza la selección local para la barra de
  conciliación manual.
- [x] Si el `PATCH` falla, la tarjeta permanece en su columna actual y se
  muestra un error visible.
- [x] `Descartar` no se ve afectado en ninguna columna.

## No-alcance

- No modifica `api/staging.py`, `api/ftp_handler.py` ni la tabla
  `staging_detections`; el gap de wiring de `direction` queda fuera.
- No agrega `GET /api/stays?status=ENTRY_ONLY` ni `EXIT_ONLY` en esta
  iteración — hoy no los llena ningún flujo activo; se evalúa sumarlos más
  adelante si empiezan a tener datos reales.
- No agrega un historial paralelo ni cambia los DTO `DetectionEvent` o
  `ParkingStay`.
- No modifica `/api/stats`, Historial ni Reconciliación de Excel.
- No mezcla automáticamente más de dos fechas de detecciones.
- **(Reapertura)** No dispara ningún llamado nuevo de conciliación; sigue
  dependiendo del mismo `POST /api/stays/auto-reconcile-exact` que ya corre
  en cada `load()` del Dashboard.
- **(Reapertura 2026-07-31, reemplazada 2026-08-05)** No agrega confirmación
  ni deshacer explícito para `set_direction`; el control de error es que una
  detección ya conciliada (`match_status != 'UNMATCHED'`) responde `409` y no
  se sobrescribe. El "deshacer" para detecciones aún pendientes ahora sí
  existe: es justamente `Quitar dirección` (ver reapertura 2026-08-05).
- **(Reapertura 2026-08-05)** No agrega un botón "Quitar dirección" en la
  franja de triage (no aplica: ya está en `UNKNOWN`).
- **(Reapertura)** No recalibra el clasificador vertical de HU-007/008/010 ni
  cambia sus umbrales; esta reapertura sólo cubre la corrección manual.
- **(Reapertura 2026-08-05)** No permite corregir la dirección de una
  detección ya conciliada en una estadía (`match_status != 'UNMATCHED'`);
  eso queda fuera de alcance también en el backend (ver HU-004).

## Código relacionado

- Frontend: `adyac-camaras-frontend/src/features/dashboard/Dashboard.tsx`,
  `src/lib/stays.ts` y pruebas relacionadas.
- Backend: `api/database.py`, `api/routers/reconciliation.py` y pruebas
  relacionadas; se preservan rutas y shapes.
- Operación: deploy habitual de `centralparking.service` y Vercel, sin mover
  datos runtime.
- **(Reapertura 2026-07-31)** Frontend: `src/lib/stays.ts` (nueva función
  `setDetectionDirection(id, direction)` que llama al `PATCH` de la
  reapertura de HU-004) y `Dashboard.tsx` (`markAsEntry`/`markAsExit`
  llamaban a `setDetectionDirection` sólo para tarjetas de triage — ver
  reapertura 2026-08-05 para el cambio posterior).
- **(Reapertura 2026-08-05)** Frontend: `src/lib/stays.ts`
  (`setDetectionDirection` amplía su tipo a incluir `"UNKNOWN"`) y
  `Dashboard.tsx` (`markAsEntry`/`markAsExit` ahora persisten siempre que la
  dirección cambie, sin importar el valor actual; nueva función
  `resetDirection` y botón `Quitar dirección` en `DetectionCard`, visible
  cuando `direction !== "UNKNOWN"`).
- **(Reapertura)** Backend: consume la reapertura de
  [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)
  (`PATCH /api/detections/{id}` con `action: "set_direction"`); no requiere
  cambios propios en `api/database.py` ni `api/routers/reconciliation.py`
  más allá de los ya descritos en esa HU.

## Contratos que deben preservarse

- `DetectionEvent` y `ParkingStay` definidos por
  [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md) —
  sin cambios, se consumen tal cual.
- `POST /api/stays/reconcile` y `PATCH /api/detections/{id}` conservan su
  contrato y comportamiento actuales.
- `GET /api/stays?date=YYYY-MM-DD` conserva query y respuesta; su semántica
  queda precisada como solapamiento del día en `America/Santiago`.
- Login, Historial, Sightings y Reconciliación de Excel sin cambios.
- **(Reapertura)** `PATCH /api/detections/{id}` con `action: "dismiss"`
  conserva exactamente su contrato y comportamiento actuales; la nueva
  acción `set_direction` es aditiva sobre el mismo endpoint.

## Impacto sobre funcionalidades existentes

Cambia la presentación y la semántica del filtro `date` de estadías. El resto
de la app (Historial, Sightings y Reconciliación Excel) no se ve afectado.

**(Reapertura 2026-07-31, ampliada 2026-08-05)** Cambia el efecto de los
botones `Entrada`/`Salida`: primero sólo para tarjetas de triage
(`direction === "UNKNOWN"`), y desde el 2026-08-05 también sobre tarjetas ya
en columna 1 o 2 — siempre que el clic vaya a cambiar la dirección actual,
persisten `direction` y mueven la tarjeta de columna. Se agrega el botón
`Quitar dirección` (columnas 1/2 → triage). No cambia `Descartar` en ningún
caso.

## Riesgos y datos

- **Hallazgo original (resuelto — ver Reapertura 2026-07-31):** esta sección
  documentaba que `api/staging.py::staging_promote_expired()` no propagaba
  `direction` a `detection_log`, dejando el 100% de las detecciones reales en
  `UNKNOWN`. Ese wiring se resolvió en el commit `07f3a58a` (2026-07-24,
  [HU-010](./HU-010-activar-clasificador-vertical-evidencia-suficiente.md),
  `implementada`): hoy `direction` refleja el resultado real del clasificador
  vertical cuando hay evidencia suficiente. La franja de triage ya no
  concentra el 100% de la operación — sólo los casos donde el clasificador
  automático no tuvo evidencia suficiente o la trayectoria fue ambigua, que
  es exactamente el escenario que esta reapertura busca resolver
  manualmente.
- Sin riesgo de datos nuevo en el resto de columnas 1/2/3: se reutilizan
  endpoints y componentes ya probados; no se cambia ninguna regla de negocio
  ni de cobro.

**(Reapertura)**

- Si el `PATCH /api/detections/{id}` (`set_direction`) falla después de que
  el administrador ya hizo clic, la tarjeta debe quedarse visiblemente en
  triage (no desaparecer ni migrar de columna) para no perder la detección de
  vista; ver criterio de aceptación correspondiente.
- Doble clic rápido sobre la misma tarjeta podría disparar dos `PATCH`
  concurrentes; el backend responde `409` al segundo (ver riesgos de
  concurrencia en la reapertura de HU-004) — el frontend debe deshabilitar el
  botón mientras la petición está en curso para reducir la probabilidad, sin
  depender de eso como única defensa.
- Error humano al clasificar manualmente ya era un riesgo aceptado por el
  diseño de la barra de conciliación manual; esta reapertura no lo
  incrementa, sólo hace que el error persista en `direction` además de en la
  selección local.

**(Reapertura 2026-08-05)**

- Antes de esta reapertura, un error de clasificación en columna 1/2 era
  irreversible desde la UI (el backend lo permitía sólo desde `UNKNOWN`).
  Ahora `Salida`/`Entrada`/`Quitar dirección` lo corrigen sin necesitar
  acceso directo a la base de datos.
- Clic redundante (ej. `Entrada` sobre una tarjeta ya `APPROACHING`) no debe
  generar tráfico de red innecesario ni parpadeo visual: se evita comparando
  `item.direction` contra la dirección destino antes de llamar al `PATCH`.
- Mismo riesgo de doble clic concurrente que la reapertura anterior; el
  backend sigue acotando el efecto por `match_status = 'UNMATCHED'`.

## Pruebas de regresión

- Login, Historial, Sightings y Reconciliación de Excel sin cambios.
- Fecha inicial corresponde a hoy en Chile y ambas lecturas incluyen la fecha.
- Cambio de fecha recarga estadías y pendientes sin datos de otros días.
- Estadía dentro del día y nocturna se incluyen por solapamiento; una estadía
  fuera del día queda excluida.
- Pendientes del día anterior sólo aparecen al activar la opción y se
  deduplican.
- Cualquier tarjeta permite seleccionar ambos roles; orden temporal inválido
  mantiene deshabilitada la conciliación.
- La conciliación manual (`POST /api/stays/reconcile`) y el descarte
  (`PATCH /api/detections/{id}`) siguen funcionando igual que en la
  iteración anterior, solo cambia desde qué columna/franja se disparan.
- Verificación visual de las 3 columnas + franja de triage en desktop y
  mobile, sin huecos ni overflow.
- `npm run lint`, `npx tsc --noEmit`, suite de tests existente, `npm run
  build` en worktree aislado.

**(Reapertura)**

- `Entrada`/`Salida` sobre triage llama a `setDetectionDirection` con
  el `id` y la dirección correcta; se verifica el body y método del `PATCH`.
- Tras éxito, la tarjeta aparece en columna 1 o 2 (según corresponda) y ya no
  en triage, sin esperar el polling de 15s.
- Tras error (`409`/`404`/red), la tarjeta permanece en triage, se muestra el
  error y la selección local no se pierde.
- `Descartar` no se ve afectado en ningún caso (triage, columna 1 o 2).
- La barra de conciliación manual sigue funcionando igual con cualquier
  combinación de tarjetas.
- `npm run lint`, `npx tsc --noEmit`, suite de tests existente y `npm run
  build` en worktree aislado, sin regresión sobre los casos ya cubiertos.

**(Reapertura 2026-08-05)**

- `Salida` sobre una tarjeta `APPROACHING` (columna 1) la mueve a columna 2;
  ya no aparece en columna 1.
- `Quitar dirección` sobre una tarjeta resuelta la devuelve a la franja de
  triage ("Sin dirección clara").
- El botón `Quitar dirección` no aparece en tarjetas de triage
  (`direction === "UNKNOWN"`).
- `npm run lint` (0 errores nuevos), `npx tsc --noEmit` (limpio), `npm test
  -- --run` (7 archivos, 22 pruebas — 3 nuevas: mover entre columnas, volver
  a triage, PATCH con `UNKNOWN` en `stays.test.ts`) y `npm run build` en
  worktree aislado.

## Propuesta técnica

1. Inicializar la fecha desde `Intl.DateTimeFormat` con zona
   `America/Santiago` y enviarla siempre a ambas lecturas.
2. Cambiar `get_parking_stays()` a límites `[inicio, día siguiente)` y
   solapamiento de intervalos.
3. Consultar el día anterior sólo cuando el administrador active la opción,
   combinar y deduplicar por `detection_id`.
4. Mantener las columnas por dirección como ayuda, pero ofrecer ambos roles en
   todas las tarjetas.
5. Mover la barra de selección antes de las columnas y mantenerla visible.
6. Probar contrato SQL, cliente HTTP, interacción, responsive, lint,
   TypeScript y build aislado.

**(Reapertura)**

1. Agregar `setDetectionDirection(id, direction)` a `src/lib/stays.ts`:
   `PATCH /api/detections/{id}` con body
   `{ action: "set_direction", direction }`, mismo manejo de errores que
   `dismissDetection`.
2. En `Dashboard.tsx`, diferenciar en `markAsEntry`/`markAsExit` si la
   tarjeta objetivo tiene `direction === "UNKNOWN"` (triage) o ya resuelta
   (columna 1/2): sólo en el primer caso, llamar a
   `setDetectionDirection` antes o junto con la selección local.
3. Actualizar optimistamente el estado local de detecciones (mismo array que
   alimenta `entradas`/`salidas`/`triage` vía `useMemo`) al recibir éxito del
   `PATCH`, para que la tarjeta cambie de columna sin esperar el próximo
   `load()`.
4. En caso de error, revertir el estado optimista (si se aplicó) y mostrar el
   error sin descartar la selección local ya hecha.
5. No tocar `auto_reconcile_exact_matches`, `build_stay_proposals` ni el
   polling de `DASHBOARD_REFRESH_MS`: siguen corriendo igual y son los que
   efectivamente conciliar la estadía una vez que ambas detecciones
   (entrada/salida) están en columnas 1/2 o ya fueron pareadas manualmente.
6. Probar cliente HTTP nuevo, interacción de triage vs. columnas resueltas,
   manejo de error, lint, TypeScript y build aislado.

## Evidencia de implementación

- **Reapertura (2026-08-05): corregir o revertir dirección.**
  - Frontend: commit `fe86f77`,
    [PR #14](https://github.com/anomvlito/adyac-camaras-frontend/pull/14),
    merge `0625ca199fd976698da4830ddf45cc7944b0cd8d`. Depende del backend de
    la reapertura de
    [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)
    (PR #61, ya desplegado).
  - `npm run lint`: 0 errores nuevos (1 error preexistente en
    `src/app/page.tsx`, no tocado; 4 advertencias preexistentes de
    `no-img-element`). `npx tsc --noEmit`: sin errores.
  - `npm test -- --run`: 7 archivos, 22 pruebas correctas — 3 nuevas: mover
    una tarjeta de "Entradas pendientes" a "Salidas pendientes" al hacer
    clic en `Salida`, devolver una tarjeta a "Sin dirección clara" con
    `Quitar dirección`, y el caso de `stays.test.ts` para
    `setDetectionDirection(id, "UNKNOWN")`.
  - `npm run build`: correcto en worktree aislado.
  - Vercel Production: `success` para el merge commit, smoke
    `https://centralparking-fiwm1nzyv-fas-projects-aa4f98ac.vercel.app`
    HTTP 200.
  - Issue #23 reabierto con comentario de trazabilidad; Project 4 movido a
    `Etapa: In progress` / `Status: In Progress` al iniciar.

- **Reapertura (2026-08-01): mover a pendientes al clasificar manualmente.**
  - Frontend: commit `ba4bf48`,
    [PR #13](https://github.com/anomvlito/adyac-camaras-frontend/pull/13),
    merge `b38c2de8e73d4bbbb11b429cf90c0648c72e39b7`. Depende del backend de
    la reapertura de
    [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)
    (PR #59, ya desplegado).
  - `npm run lint`: 0 errores, 4 advertencias preexistentes de
    `no-img-element`. `npx tsc --noEmit`: sin errores.
  - `npm test -- --run`: 7 archivos, 19 pruebas correctas — incluye el nuevo
    `Dashboard.test.tsx` (flujo triage → columna tras éxito del `PATCH`, y
    caso de error `409` que mantiene la tarjeta en triage) y el nuevo caso en
    `stays.test.ts` para `setDetectionDirection` (método, body y propagación
    de error).
  - `npm run build`: correcto en worktree aislado.
  - Vercel Production: `success` para el merge commit,
    smoke `https://centralparking-1ozua5kxi-fas-projects-aa4f98ac.vercel.app`
    HTTP 200.
  - Issue #23 reabierto con comentario de trazabilidad; Project 4 movido a
    `Etapa: In progress` / `Status: In Progress` al iniciar y de vuelta a
    cierre verificado tras el deploy.

- **Navegación diaria manual (2026-07-28):**
  - Frontend: PR
    [#12](https://github.com/anomvlito/adyac-camaras-frontend/pull/12),
    merge `fd120c3` y Vercel Production `success`.
  - Controles de día anterior/siguiente, límite en hoy de
    `America/Santiago` y `max` equivalente en el selector manual.
  - 15 pruebas Vitest, TypeScript, lint sin errores y build Next.js correctos.
  - Smoke de producción HTTP 200.

- **Reapertura por fecha operativa (2026-07-28):**
  - Backend/documentación: commits `f66a61b` y `f5ec9d0`,
    [PR #41](https://github.com/anomvlito/centralparking-mvp/pull/41),
    merge `e0af2eb36da301011fa6ccf58a0db5551e1c0ced`.
  - Frontend: commit `91e0245`,
    [PR #8](https://github.com/anomvlito/adyac-camaras-frontend/pull/8),
    merge `59c55e7cdb49eae616eacc1e4bdc5bdf6c685df5`.
  - Backend: 10 pruebas contractuales `unittest`, `compileall`, import de
    FastAPI y `git diff --check` correctos.
  - Frontend: 14 pruebas Vitest, lint sin errores (4 advertencias
    preexistentes de `<img>`), TypeScript, build Next.js y `git diff --check`
    correctos.
  - Deploy backend:
    [run 30392654410](https://github.com/anomvlito/centralparking-mvp/actions/runs/30392654410)
    correcto; `centralparking.service` y `parking-watchdog.service` activos,
    checkout de deploy en el merge, `/docs` HTTP 200 y fecha inválida HTTP 422.
  - Vercel Production `success` para el merge frontend; smoke HTTP 200 en
    `https://centralparking-j6wsnojbe-fas-projects-aa4f98ac.vercel.app`.
  - Smoke funcional sin datos sensibles: `/api/stays` devolvió estadías para
    fechas históricas reales y `/api/detections` respondió al día operativo.

- Rama/worktree: `agent/hu-005-tres-columnas` en
  `.worktrees/hu-005-tres-columnas-frontend`, basada en `origin/main` real
  (commit `e928f8d`, que incluye el ajuste de tarjeta de estadía de PR #6).
- `Dashboard.tsx` reescrito como grid de 3 columnas (`DashboardColumn`,
  `DetectionCard` con roles `entry`/`exit`/`triage`, reutiliza `StayEvidence`
  para columna 3) + franja "Sin dirección clara" para `direction === "UNKNOWN"`.
  Filtros de fecha/patente, barra de confirmación de conciliación y polling
  de 15s sin cambios de lógica respecto a la iteración anterior.
- `npm run lint`: correcto tras corregir un error real (`react-hooks/rules-of-hooks`
  disparado porque dos funciones locales empezaban con `use`; se renombraron a
  `markAsEntry`/`markAsExit`) — 0 errores, 4 advertencias preexistentes de
  `no-img-element`.
- `npx tsc --noEmit`: correcto, sin errores.
- `npm test -- --run`: 5 archivos, 11 pruebas correctas. Se actualizó
  `App.integration.test.tsx` (heading esperado pasa de "Estadías" a
  "Dashboard", único cambio de texto visible en el flujo caracterizado).
- `npm run build`: correcto en el worktree aislado (no se tocó el proceso
  `next start` que sirve `.next` en el checkout principal).
- Sin verificación visual en navegador logueado: mismo bloqueo documentado en
  la iteración anterior — `API` apunta a producción
  (`https://2.24.69.49.nip.io`) y no hay credenciales disponibles para
  loguearse de forma segura en este entorno.
- Publicado: commit `9f45be1`,
  [PR #7](https://github.com/anomvlito/adyac-camaras-frontend/pull/7).
  Checks: `Vercel` y `Vercel Preview Comments` en `pass`, PR `MERGEABLE`/`CLEAN`.
- Mergeado a `main`: merge commit `52bf59bd1030ffd6dcf9db7b58fb7f78414463dd`,
  autorizado explícitamente por el usuario.
- Deploy Vercel producción: `success` para el merge commit —
  `https://centralparking-gmpf1k909-fas-projects-aa4f98ac.vercel.app`.
- Smoke check post-deploy: `HTTP 200`.
- Pendiente (fuera de esta etapa, a definir con el usuario): publicar esta
  actualización de HU-005.md en el repo `centralparking-mvp`, y el spike de
  backend para el wiring de `direction` documentado en "Riesgos y datos".

## Evidencia de la iteración anterior ("Estadías", implementada 2026-07-24)

- Frontend: commit `bfed715`,
  [PR #5](https://github.com/anomvlito/adyac-camaras-frontend/pull/5),
  merge `08b56d97bc6d758870f2cbc4ad0d723768f47f12`.
- Verificación: 11 pruebas Vitest, TypeScript y build correctos; lint sin
  errores y con tres advertencias no bloqueantes de imágenes.
- Vercel: deployment `Production` exitoso para el merge.
- Smoke: URL de producción del deployment responde HTTP 200.
- Ajuste posterior: commit `a16c3f8`,
  [PR #6](https://github.com/anomvlito/adyac-camaras-frontend/pull/6) —
  muestra evidencia (imágenes) a ambos lados de la estadía en la tarjeta
  (componente `StayEvidence`, reutilizado en esta reapertura para columna 3).
- Nota de trazabilidad: esta HU se implementó primero contra un mock
  (`src/lib/dashboardMock.ts`, 2026-07-24 01:29 UTC) con el diseño de 3
  columnas (`EntryOpen`/`ExitOrphan`/`SessionClosed`) descrito originalmente
  junto con HU-004 y ADR-001 el 2026-07-23; nunca se conectó contra backend
  real. Luego se reemplazó por completo por la vista `Estadías`/`Por
  conciliar` (evidencia arriba), que sí se conectó, probó y publicó contra
  backend real. Esta reapertura (2026-07-24, más tarde) vuelve al layout de
  3 columnas, pero ahora sí conectado contra los endpoints reales de HU-004
  (`/api/detections`, `/api/stays`), sin mocks. El nombre de archivo de esta
  HU conserva su slug original
  (`HU-005-frontend-dashboard-tres-columnas-conciliacion.md`) por
  continuidad de enlaces existentes.
