# HU-005 — Frontend: dashboard de tres columnas para conciliar entradas y salidas

**Actor:** `administrador`
**Estado:** `backlog`
**Feature relacionada:** [Conciliación automática de entradas y salidas](../../features/backlog/conciliacion-automatica-entradas-salidas.md)
**Issue:** pendiente
**Project 4:** pendiente
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

- Commit/PR: pendiente.
- Verificaciones: pendientes.
