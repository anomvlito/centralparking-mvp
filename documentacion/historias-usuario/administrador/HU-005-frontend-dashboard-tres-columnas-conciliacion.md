# HU-005 — Frontend: dashboard de tres columnas para conciliar entradas y salidas

**Actor:** `administrador`
**Estado:** `en-progreso`
**Feature relacionada:** [Conciliación automática de entradas y salidas](../../features/in-progress/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#23](https://github.com/anomvlito/centralparking-mvp/issues/23)
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In progress`
**Creado por:** Francisco

## Historia

Como **administrador**, quiero **ver el Dashboard organizado en tres
columnas — entradas sin salida asociada, salidas sin entrada asociada y
sesiones completas — y poder resolver manualmente los casos que el backend no
logró asociar solo**, para **tener una vista operativa clara de lo pendiente
de conciliar, sin depender del feed cronológico único actual**.

## Contexto y problema

Hoy el Dashboard (`Dashboard`, `adyac-camaras-frontend/src/app/page.tsx`)
muestra un feed único (`FeedRow`) que mezcla avistamientos, entradas y
salidas en orden cronológico, con "Registrar entrada"/"Registrar salida"
(`RegisterActions`) como única forma de asociar sesiones.

Esta HU depende de [HU-004 — Backend: conciliación automática de entradas y
salidas](./HU-004-backend-conciliacion-automatica-entradas-salidas.md), que
define y debe exponer los endpoints `GET /api/dashboard/entries-open`, `GET
/api/dashboard/exits-orphan`, `GET /api/dashboard/sessions-closed` y `PATCH
/api/dashboard/exits-orphan/{id}`. Sin esos endpoints construidos (o al menos
su contrato estable), esta HU no puede completarse contra datos reales.

## Criterios de aceptación

- [ ] El Dashboard muestra tres columnas: (1) entradas sin salida asociada,
  (2) salidas sin entrada asociada, (3) sesiones completas.
- [ ] Columna 1: tarjeta con imagen de entrada, patente y hora de ingreso —
  consume `GET /api/dashboard/entries-open`.
- [ ] Columna 2: tarjeta con imagen de salida, patente y hora de salida —
  consume `GET /api/dashboard/exits-orphan`.
- [ ] Columna 3: tarjeta con imagen de entrada + hora de entrada a la
  izquierda, patente + tiempo total dentro al centro, imagen de salida + hora
  de salida a la derecha — consume `GET /api/dashboard/sessions-closed`.
- [ ] El administrador puede seleccionar una tarjeta de columna 2 y asociarla
  manualmente a una tarjeta de columna 1, disparando `PATCH
  /api/dashboard/exits-orphan/{id}` con `action: match`.
- [ ] El administrador puede descartar una tarjeta de columna 2 (`action:
  dismiss`) sin que se borre el registro en backend.
- [ ] Tras un match o dismiss, las tres columnas se refrescan y el registro
  ya no aparece en su columna de origen (columna 1/2), reflejando lo que
  devuelve el backend.
- [ ] Polling cada `DASHBOARD_REFRESH_MS` (15s), igual que el feed actual.
- [ ] El layout se adapta sin espacio vacío ni columnas rotas en desktop y
  mobile.

## No-alcance

- No modifica el algoritmo de matching automático ni `DirectionTracker` —
  eso es HU-004.
- No crea ni modifica los endpoints `/api/dashboard/*` — esta HU los
  consume, asumiendo que HU-004 ya los expone.
- No modifica `/api/stats`, Historial ni Reconciliación de Excel.
- No define aún la interacción exacta de "seleccionar 2 tarjetas de columnas
  distintas para matchear" a nivel de mockup — se resuelve en implementación.
- No publica (commit/push/PR/merge/deploy) como parte de esta etapa de
  creación de HU.

## Código relacionado

- Frontend: `adyac-camaras-frontend/src/app/page.tsx`, componente
  `Dashboard` — reemplaza el feed único de 1 columna por el grid de 3
  columnas descrito arriba.
- Backend: no requiere cambios en esta HU — consume los endpoints definidos
  en HU-004.
- Operación: no requiere cambios.

## Contratos que deben preservarse

- El estado actual de un auto dentro del estacionamiento conserva un contrato
  distinto de los objetos de las tres columnas:

  ```ts
  type ParkedCar = {
    plate: string;
    entryTime: number;
    isEvent: boolean;
    eventFee?: number | null;
  };

  type CarsResponse = Record<string, ParkedCar>;
  ```

  `EntryOpen`, `ExitOrphan` y `SessionClosed` no reemplazan `ParkedCar` ni
  cambian el shape de `GET /api/cars`.
- Los shapes de respuesta de `GET /api/dashboard/entries-open`, `GET
  /api/dashboard/exits-orphan`, `GET /api/dashboard/sessions-closed` y
  `PATCH /api/dashboard/exits-orphan/{id}` definidos en HU-004 — cualquier
  cambio de contrato debe coordinarse entre ambas HUs.
- `/api/cars`, `/api/history`, login y Reconciliación de Excel sin cambios.
- Polling cada 15s (`DASHBOARD_REFRESH_MS`), mismo patrón que el feed actual.

## Impacto sobre funcionalidades existentes

Cambia significativamente la vista Dashboard; `FeedRow`/`RegisterActions`
dejan de usarse ahí (a decidir en implementación si Historial los sigue
usando tal cual, ya que ese feed no cambia en esta HU).

## Riesgos y datos

- **Bloqueo por dependencia:** si HU-004 no está implementada o su contrato
  cambia, esta HU no se puede completar contra datos reales — coordinar
  orden de implementación entre ambos repos.
- Sin datos sensibles adicionales: es una vista ya autenticada, reutiliza
  imágenes y patentes que el backend ya expone hoy en `/api/history`.

## Pruebas de regresión

- Login, Historial y Reconciliación de Excel sin cambios.
- Verificación visual de las 3 columnas en desktop y mobile, sin huecos ni
  overflow.
- `npm run lint`, `npm exec tsc -- --noEmit`, suite de tests existente,
  `npm run build` en copia aislada si hay una `.next` activa sirviendo local.

## Propuesta técnica

1. Consumir los endpoints de HU-004 (idealmente `GET /api/dashboard`
   combinado si backend lo expone) con polling de 15s.
2. Renderizar las 3 columnas con el layout de tarjeta descrito en los
   criterios de aceptación.
3. Implementar la UI de match manual (columna 2 → columna 1) y de dismiss,
   llamando `PATCH /api/dashboard/exits-orphan/{id}`.
4. Refrescar las 3 columnas tras cada acción (match/dismiss), igual que hoy
   se refresca el feed tras registrar/corregir una patente.
5. Probar localmente en servidor de desarrollo, correr la regresión listada
   arriba, y sólo entonces evaluar publicar — fuera del alcance de esta etapa
   de creación de HU.

## Evidencia de implementación

- Rama: `agent/hu-001-boton-ingresar-lila` en
  `adyac-camaras-frontend` (checkout ya activo, sin worktree aislado nuevo —
  autorizado explícitamente así por el usuario, sin push/PR/merge/deploy en
  esta etapa por el bloqueo de dependencia con HU-004).
- Implementado contra mock local: `src/lib/dashboardMock.ts` (tipos +
  `fetchDashboardData`/`patchExitOrphan` con el contrato exacto de HU-004,
  estado mutable en memoria para que match/dismiss se reflejen en las 3
  columnas). Punto de integración real documentado en el propio archivo:
  reemplazar el cuerpo de esas dos funciones por `apiFetch` a
  `/api/dashboard/*` cuando HU-004 exista.
- `Dashboard` reescrito en `src/app/page.tsx` como grid de 3 columnas
  (`EntryOpenCard`, `ExitOrphanCard`, `SessionClosedCard`, `DashboardColumn`),
  con selección de salida huérfana + confirmación en columna de entradas para
  el match manual, botón de dismiss con confirmación, y polling cada
  `DASHBOARD_REFRESH_MS` (15s, mismo valor que usaba el feed anterior).
- Efecto colateral documentado (mismo criterio que HU-003 con `stats`): al
  dejar de pasar `stats`/`history`/`parked`/`loading` desde `App` a
  `Dashboard`, esas 4 variables y el componente `StatCard` quedan sin uso en
  `page.tsx`. No se retiraron sus llamadas/`useState` ni el polling de
  `App.refresh()` (`/api/stats`, `/api/history`, `/api/sightings`,
  `/api/cars`) — requiere autorización separada, igual que en HU-003.
- `npm run lint`: correcto, 0 errores, 7 advertencias (2 preexistentes de
  `no-img-element`; 5 esperadas por el punto anterior: `StatCard`, `stats`,
  `history`, `parked`, `loading` sin uso).
- `npx tsc --noEmit`: correcto, sin errores.
- `npm run build`: correcto, ejecutado en copia aislada (`rsync` a
  scratchpad) porque hay un proceso `next start` sirviendo el `.next` de este
  repo — no se tocó ese proceso ni su build.
- Sin suite de tests: este branch no tiene `test` en `package.json` ni
  dependencias de testing (a diferencia de lo reportado en la evidencia de
  HU-003, que corrió en otro branch/worktree con tests configurados) — no se
  fingió cobertura.
- Sin verificación visual en navegador: `API` apunta al backend de
  producción (`https://2.24.69.49.nip.io`) y no hay credenciales disponibles
  para loguearse ahí de forma segura en este entorno — pendiente de
  validación visual real.
- Commit/PR: pendiente (no autorizado en esta etapa).
- Bloqueo activo: no se puede verificar end-to-end contra datos reales hasta
  que HU-004 (backend) esté implementada.
