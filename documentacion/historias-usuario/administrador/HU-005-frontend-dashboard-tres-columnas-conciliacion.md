# HU-005 — Dashboard de 3 columnas para conciliar entradas y salidas

**Actor:** `administrador`
**Estado:** `en-progreso` (reapertura de alcance — ver nota de trazabilidad)
**Feature relacionada:** [Estadías conciliadas desde detecciones](../../features/in-progress/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#23](https://github.com/anomvlito/centralparking-mvp/issues/23) — cerrado en GitHub; este documento
adelanta una reapertura de alcance aún no reflejada en el issue ni en el
Project 4 (pendiente de autorización explícita para publicar/sincronizar).
**HU backend:** [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)

## Historia

Como **administrador**, quiero **ver el Dashboard organizado en tres columnas
— entradas pendientes de salida, salidas pendientes de entrada y sesiones
completas — y poder resolver manualmente los casos que quedan ambiguos**,
para **tener una vista operativa clara de lo pendiente de conciliar, en vez de
una única tabla de estadías con una grilla plana de detecciones debajo**.

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

## Criterios de aceptación

- [ ] El Dashboard muestra 3 columnas: (1) Entradas pendientes, (2) Salidas
  pendientes, (3) Sesiones completas.
- [ ] Columna 1 y columna 2 se derivan client-side del mismo array que hoy
  trae `fetchUnmatchedDetections` (`GET /api/detections?match_status=UNMATCHED`):
  columna 1 = `direction === "APPROACHING"`, columna 2 = `direction === "DEPARTING"`.
- [ ] Una franja de triage aparte (fuera de columnas 1 y 2) muestra las
  detecciones con `direction === "UNKNOWN"`, con ambos botones "Es entrada" /
  "Es salida" visibles — no se asignan por defecto a ninguna columna.
- [ ] Columna 3 consume `GET /api/stays?status=COMPLETED` (`fetchStays`) y
  reutiliza el componente `StayEvidence` ya existente: evidencia de entrada a
  la izquierda, patente + duración al centro, evidencia de salida a la
  derecha.
- [ ] Seleccionar una tarjeta como entrada (columna 1 o triage) y otra como
  salida (columna 2 o triage) habilita la barra de conciliación manual con
  patente resuelta editable → `POST /api/stays/reconcile` (sin cambios de
  lógica respecto a la iteración anterior).
- [ ] Descartar una tarjeta (columna 1, 2 o triage) → `PATCH
  /api/detections/{id}` con `action: dismiss`, sin borrar el registro.
- [ ] Tras conciliar o descartar, las 3 zonas se refrescan (mismo polling de
  `DASHBOARD_REFRESH_MS`, 15s).
- [ ] El layout se adapta sin huecos ni columnas rotas en desktop y mobile
  (1 columna en mobile, 3 en desktop).

## No-alcance

- No modifica el backend, `api/staging.py`, `api/ftp_handler.py` ni la tabla
  `staging_detections` — el gap de wiring de `direction` (ver "Riesgos y
  datos") queda documentado para una HU/spike de backend separada, no se
  resuelve acá.
- No agrega `GET /api/stays?status=ENTRY_ONLY` ni `EXIT_ONLY` en esta
  iteración — hoy no los llena ningún flujo activo; se evalúa sumarlos más
  adelante si empiezan a tener datos reales.
- No modifica `src/lib/stays.ts`, sus tipos ni sus funciones — se reutilizan
  literalmente.
- No modifica `/api/stats`, Historial ni Reconciliación de Excel.
- No publica (commit/push/PR/merge/deploy) en esta etapa — implementación y
  verificación solamente local, por decisión explícita del usuario.
- No reabre el issue #23 ni mueve la tarjeta del Project 4 en GitHub — eso
  requiere autorización separada.

## Código relacionado

- Frontend: `adyac-camaras-frontend/src/features/dashboard/Dashboard.tsx` —
  único archivo a reescribir. Reutiliza sin cambios `src/lib/stays.ts` y
  `src/lib/constants.ts` (`DASHBOARD_REFRESH_MS`).
- Backend: no requiere cambios en esta HU.
- Operación: no requiere cambios.

## Contratos que deben preservarse

- `DetectionEvent` y `ParkingStay` definidos por
  [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md) —
  sin cambios, se consumen tal cual.
- `POST /api/stays/reconcile` y `PATCH /api/detections/{id}` conservan su
  contrato y comportamiento actuales.
- Login, Historial, Sightings y Reconciliación de Excel sin cambios.

## Impacto sobre funcionalidades existentes

Cambia únicamente la presentación visual del Dashboard (de "tabla + grilla
única" a "3 columnas + franja de triage"). No cambia qué datos se piden, ni
cuándo, ni la lógica de conciliación/descarte. El resto de la app (Historial,
Reconciliación) no se ve afectado.

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
- La conciliación manual (`POST /api/stays/reconcile`) y el descarte
  (`PATCH /api/detections/{id}`) siguen funcionando igual que en la
  iteración anterior, solo cambia desde qué columna/franja se disparan.
- Verificación visual de las 3 columnas + franja de triage en desktop y
  mobile, sin huecos ni overflow.
- `npm run lint`, `npx tsc --noEmit`, suite de tests existente, `npm run
  build` en worktree aislado.

## Propuesta técnica

1. Reescribir `Dashboard.tsx` a un grid de 3 columnas (`grid-cols-1
   lg:grid-cols-3`), reutilizando íntegramente `src/lib/stays.ts` (sin
   cambios) y el componente `StayEvidence` ya implementado para columna 3.
2. Derivar client-side, a partir del mismo array `detections` que ya se trae
   hoy: `entradas = detections.filter(d => d.direction === "APPROACHING")`,
   `salidas = ... "DEPARTING"`, `triage = ... "UNKNOWN"`.
3. Columna 1: tarjeta con botón único "Usar como entrada" (`setEntry`) +
   "Descartar". Columna 2: botón único "Usar como salida" (`setExit`) +
   "Descartar". Franja de triage: ambos botones + "Descartar" (mismo
   comportamiento que la tarjeta de "Por conciliar" de la iteración
   anterior).
4. Barra de confirmación (entrada + salida + patente resuelta + "Crear
   estadía") sin cambios de lógica, solo de ubicación en el layout.
5. Probar localmente (lint, tsc, tests, build aislado) y reportar evidencia;
   sin publicar salvo autorización explícita adicional.

## Evidencia de implementación

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
