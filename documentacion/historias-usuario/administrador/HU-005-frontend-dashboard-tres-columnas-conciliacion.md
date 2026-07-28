# HU-005 — Dashboard de 3 columnas para conciliar entradas y salidas

**Actor:** `administrador`
**Estado:** `en-progreso`
**Feature relacionada:** [Estadías conciliadas desde detecciones](../../features/in-progress/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#23](https://github.com/anomvlito/centralparking-mvp/issues/23)
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

## Criterios de aceptación

- [x] Existe un único selector de fecha operativa, iniciado en la fecha actual
  de `America/Santiago`; al cambiarlo se recargan columnas, triage y sesiones
  completas con el mismo valor `YYYY-MM-DD`.
- [ ] Junto al selector existen controles para avanzar o retroceder exactamente
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

## Código relacionado

- Frontend: `adyac-camaras-frontend/src/features/dashboard/Dashboard.tsx`,
  `src/lib/stays.ts` y pruebas relacionadas.
- Backend: `api/database.py`, `api/routers/reconciliation.py` y pruebas
  relacionadas; se preservan rutas y shapes.
- Operación: deploy habitual de `centralparking.service` y Vercel, sin mover
  datos runtime.

## Contratos que deben preservarse

- `DetectionEvent` y `ParkingStay` definidos por
  [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md) —
  sin cambios, se consumen tal cual.
- `POST /api/stays/reconcile` y `PATCH /api/detections/{id}` conservan su
  contrato y comportamiento actuales.
- `GET /api/stays?date=YYYY-MM-DD` conserva query y respuesta; su semántica
  queda precisada como solapamiento del día en `America/Santiago`.
- Login, Historial, Sightings y Reconciliación de Excel sin cambios.

## Impacto sobre funcionalidades existentes

Cambia la presentación y la semántica del filtro `date` de estadías. El resto
de la app (Historial, Sightings y Reconciliación Excel) no se ve afectado.

## Riesgos y datos

- **Hallazgo bloqueante para el valor real de columnas 1 y 2:**
  `api/staging.py::staging_promote_expired()` llama a
  `log_to_db(plate, "DETECTED", status="STAGING_AUTO", conf=..., image_path=...)`
  sin pasar `direction`. La evaluación de `direction_service.observe()` que sí
  se calcula en `ftp_handler._handle_auto_detection()` solo se audita en
  `audit_log` (consumida por `/api/audit/direction/metrics` de HU-009) y nunca
  llega a la fila de `detection_log` que lee `/api/detections`. Resultado:
  **hoy el 100% de las detecciones reales de cámara tienen
  `direction: "UNKNOWN"`**, sin importar los umbrales de HU-008
  (`DIRECTION_MIN_DISPLACEMENT`, `DIRECTION_MIN_CONSISTENCY`, etc.) — el
  problema es de propagación del dato entre `staging_detections` y
  `detection_log`, no de calibración. Ajustar esos umbrales sin resolver el
  wiring no tendría ningún efecto visible.
- Por eso mismo, en producción, columnas 1 y 2 estarán casi vacías y la
  franja de triage concentrará la operación real hasta que ese wiring se
  resuelva en una HU/spike de backend aparte (fuera de alcance acá).
- Sin riesgo de datos nuevo: se reutilizan endpoints y componentes ya
  probados; no se cambia ninguna regla de negocio ni de cobro.

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

## Evidencia de implementación

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
