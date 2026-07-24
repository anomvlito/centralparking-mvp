# Feature — Conciliación automática de entradas y salidas en el Dashboard

**Etapa Project 4:** `Backlog`
**HUs relacionadas:**
- [HU-004 — Backend: conciliación automática de entradas y salidas](../../historias-usuario/administrador/HU-004-backend-conciliacion-automatica-entradas-salidas.md)
- [HU-005 — Frontend: dashboard de tres columnas para conciliar entradas y salidas](../../historias-usuario/administrador/HU-005-frontend-dashboard-tres-columnas-conciliacion.md) (depende de HU-004)

**Issues:** pendiente

## Problema

El Dashboard muestra un feed único donde entradas, salidas y avistamientos se
mezclan cronológicamente. La apertura/cierre de sesión es siempre manual
(botones "Registrar entrada"/"Registrar salida"), y no existe forma de
registrar una salida cuya entrada no fue vista por la cámara — el endpoint de
salida exige una sesión abierta y devuelve `404` si no la encuentra. No hay
ninguna cola visible de "casos que el sistema no pudo asociar solo".

## Resultado esperado

El Dashboard organiza la operación en tres columnas — entradas sin salida,
salidas sin entrada, sesiones completas — y el backend intenta asociar cada
detección de cámara automáticamente por patente (match exacto o difuso sobre
sesiones abiertas). Cuando no puede decidir con esa señal, usa
`DirectionTracker` (geometría de posición en 2-3 frames, hoy desconectado)
solo para desempatar entre "entrada nueva" y "salida sin entrada", nunca para
clasificar el 100% de las detecciones como en su uso original. Todo resultado
ambiguo queda en cola de revisión, conciliable manualmente por un
administrador.

## Alcance

- Reactivación acotada de `DirectionTracker`, solo como desempate del caso
  sin sesión abierta que matchee.
- Nueva tabla `orphan_exits` para salidas sin entrada asociada, con
  trazabilidad completa (nunca se borra una fila).
- Nuevos endpoints de lectura por columna y de conciliación manual
  (`match`/`dismiss`) — ver propuesta técnica de HU-004.
- Rediseño del Dashboard (`adyac-camaras-frontend/src/app/page.tsx`) a un
  layout de 3 columnas — ver HU-005, depende de que HU-004 exponga los
  endpoints.

## No-alcance

- `/api/stats`, Historial, Reconciliación de Excel (`api/excel.py`) — sin
  cambios.
- `/api/cars`, `/api/history` — se preservan sin cambios; los nuevos
  endpoints son adicionales.
- Cobro o sanción automática a partir de una clasificación
  `DEPARTING`/`APPROACHING` sin revisión humana.
- Publicación (commit/push/PR/merge/deploy) como parte de esta etapa de
  diseño.

## Contratos

- `/api/cars`, `/api/history`, `/api/entry`, `/api/exit/{plate}` mantienen su
  contrato actual.
- `orphan_exits` nunca se borra; `dismiss` solo cambia de estado.
- Ningún registro puede aparecer simultáneamente en columna 1/2 y columna 3.

## Riesgos

- `DirectionTracker` ya se desconectó una vez (2026-07-17) por generar
  salidas falsas y duplicados al decidir dirección del 100% de las
  detecciones; esta feature acota su uso al caso ambiguo, pero sus umbrales
  deben re-validarse con datos reales antes de confiar en producción.
- Cambia el comportamiento del pipeline de ingesta FTP en producción (pasa de
  solo loguear avistamientos a poder abrir/cerrar sesiones automáticamente).

## Criterio de cierre

HU-004 y HU-005 implementadas, con pruebas de los casos de match automático,
desempate por `DirectionTracker`, match manual y dismiss (backend), y de las
3 columnas y su interacción de conciliación manual (frontend), sin regresión
en Historial, `/api/cars` ni Reconciliación de Excel.
