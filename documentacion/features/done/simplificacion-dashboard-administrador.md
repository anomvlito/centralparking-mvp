# Feature — Simplificación del Dashboard operativo

**Etapa Project 4:** `Done`
**HUs relacionadas:** [HU-003 — Simplificar el Dashboard eliminando estadísticas y estado](../../historias-usuario/administrador/HU-003-simplificar-dashboard-sin-estadisticas.md)
**Issues:** [#21](https://github.com/anomvlito/centralparking-mvp/issues/21)

## Problema

El Dashboard combina el feed en vivo con recuadros de estadísticas
(Entradas hoy, Salidas hoy, En parking, Recaudado) y un bloque de estado
(Cámara/Staging/Actualización) que se propone retirar de la vista.

## Resultado esperado

El Dashboard muestra únicamente el feed en vivo, sin los recuadros de
estadísticas ni el bloque de estado, conservando el resto de su
comportamiento (polling, orden, refresco tras acciones).

## Alcance

- Remoción de los 4 `StatCard` y el bloque "Estado" en
  `Dashboard.tsx`.
- Ajuste de layout para que el feed ocupe el espacio liberado.
- Verificación visual y de regresión del feed en vivo.

## No-alcance

- Cambios en el endpoint `/api/stats` o en Historial/Reconciliación.
- Retiro de `stats` o de la llamada a `/api/stats` en `App` (page.tsx).
- Publicación (commit/push/PR/merge/deploy) como parte de esta etapa.

## Contratos

- `/api/stats` se preserva en backend y en `App`, aunque deje de
  renderizarse en `Dashboard`.
- Polling del feed cada 15 segundos (`DASHBOARD_REFRESH_MS`).
- Trazabilidad visual imagen–avistamiento–sesión en `FeedRow`/`PhotoThumb`.

## Riesgos

- Layout de 2 columnas (`lg:grid-cols-[300px_1fr]`) requiere ajuste al
  quitar la columna izquierda.
- Posible código/prop sin uso si `stats` deja de graficarse en `Dashboard`.

## Criterio de cierre

La HU-003 cumple sus criterios de aceptación, supera lint/TypeScript/tests y
se valida visualmente en desktop y mobile, sin regresiones en el feed en
vivo ni en el resto de las pestañas.
