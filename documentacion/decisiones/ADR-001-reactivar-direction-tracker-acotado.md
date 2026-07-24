# ADR-001 — Reactivar `DirectionTracker` acotado a desempate, con plan de mejora iterativa

**Estado:** `aceptada`
**Fecha:** 2026-07-23
**Creado por:** Francisco
**HUs relacionadas:** [HU-004 — Backend: conciliación automática de entradas y salidas](../historias-usuario/administrador/HU-004-backend-conciliacion-automatica-entradas-salidas.md), [HU-005 — Frontend: dashboard de tres columnas para conciliar entradas y salidas](../historias-usuario/administrador/HU-005-frontend-dashboard-tres-columnas-conciliacion.md)

> **Refinamiento propuesto (2026-07-24):** ADR-001 conserva la decisión de
> usar dirección solo como desempate revisable. La señal geométrica concreta
> queda refinada, aún como propuesta no implementada, por
> [ADR-003 — Clasificar dirección exclusivamente por trayectoria vertical](./ADR-003-clasificacion-direccion-trayectoria-vertical.md):
> solo `y(t)` normalizado contra la imagen truncada, sin X, tamaño ni cruce de
> zonas. Ver [HU-007](../historias-usuario/administrador/HU-007-clasificar-direccion-trayectoria-vertical.md).

## Contexto

`api/direction_tracker.py` implementa `DirectionTracker`: clasifica una
detección de patente como `APPROACHING`/`DEPARTING`/`UNKNOWN` a partir de una
señal geométrica (posición en eje X/Y o tamaño de bbox) observada en 2-3
frames dentro de una ventana corta (`DIRECTION_WINDOW_SEC`).

El módulo se desconectó el 2026-07-17 (ver comentarios en
`api/ftp_handler.py::_handle_auto_detection` y `api/staging.py`) porque,
usado para decidir la dirección de **el 100% de las detecciones**, producía:

- salidas falsas, muchas veces con la peor foto de la ráfaga (necesita varias
  muestras consistentes antes de confirmar, y para entonces el auto ya se
  había alejado de la cámara);
- registros duplicados.

Desde entonces, la apertura/cierre de sesión es enteramente manual
(`/api/entry`, `/api/exit/{plate}`, botones "Registrar entrada"/"Registrar
salida" en el frontend). Esto funciona, pero no escala: cada detección de
cámara requiere intervención humana, y no existe forma de registrar una
salida cuya entrada no fue vista por la cámara (`/api/exit/{plate}` devuelve
`404` si no hay sesión abierta con esa patente).

HU-004 necesita decidir automáticamente, para las detecciones sin sesión
abierta que matchee, si son una entrada nueva o una salida sin entrada
(columna 2 del dashboard de HU-005). No hay ninguna otra señal disponible en
el sistema hoy para resolver ese caso sin intervención humana — es
`DirectionTracker` o nada.

## Decisión

Reactivar `DirectionTracker`, pero con un alcance deliberadamente más
acotado que su uso original: se consulta **solo** cuando no hay ninguna
sesión abierta que matchee la patente detectada (ni exacta ni difusa vía
`find_similar_active_session`). En ese caso, aplicando el refinamiento
vertical de ADR-003:

- `APPROACHING` → se asume entrada nueva (`upsert_vehicle`).
- `DEPARTING` → se registra como salida sin entrada asociada
  (`orphan_exits`), pendiente de revisión manual — nunca cierra ni cobra una
  sesión de forma autoritativa.
- `UNKNOWN` → se conserva el avistamiento y su evidencia para revisión/manual,
  sin abrir o cerrar sesiones y sin crear una salida huérfana.

Esta reactivación es intencionalmente el primer paso de un camino iterativo,
no un fin en sí mismo: la intención de fondo es **volver a tener
clasificación automática de dirección funcionando en el sistema**, y usar la
operación real (con la cola de revisión de columna 2 como red de seguridad)
para ir afinándola, en vez de intentar dejarla perfecta antes de encender
nada. Ver "Trabajo futuro".

## Alternativas consideradas

1. **Mantenerlo desconectado indefinidamente**, exigiendo siempre match
   manual para el caso sin sesión abierta. Descartada como decisión final:
   no resuelve la necesidad de producto (conciliación automática) ni deja
   camino para recuperar la inversión ya hecha en `DirectionTracker`; sí es,
   en la práctica, el estado en el que queda cualquier detección que caiga
   en `UNKNOWN` — no se pierde como opción, coexiste como resultado posible.
2. **Reactivarlo con su alcance original** (decide dirección del 100% de las
   detecciones, incluyendo las que sí tienen sesión abierta que matchear).
   Descartada: repite exactamente las condiciones que causaron el problema
   de 2026-07-17, sin ninguna mitigación nueva.
3. **Reactivarlo acotado a desempate, con matching por patente+estado de
   sesión como señal primaria determinística** (la elegida). El toggle por
   patente cubre el caso normal sin geometría; `DirectionTracker` solo entra
   en el subconjunto ambiguo, y su resultado siempre es revisable, nunca
   autoritativo.

## Consecuencias

- El radio de impacto de un error de clasificación es menor que en el uso
  original: como máximo, una entrada se abre cuando en realidad era una
  salida sin entrada (o viceversa), y queda visible/corregible en columna 1
  o columna 2 del dashboard — no se pierde información ni se cobra de más.
- Sigue existiendo riesgo real de repetir clasificaciones erróneas si los
  umbrales (`DIRECTION_MIN_DISPLACEMENT`, `DIRECTION_MIN_CONSISTENCY`,
  `DIRECTION_AXIS`, `DIRECTION_ENTRY_SIGN`) no se validan con fotos/video
  reales de la cámara actual antes de confiar en el resultado — son los
  mismos umbrales que ya fallaron una vez, ahora en un contexto distinto.
- Introduce una tabla nueva (`orphan_exits`) y un flujo de conciliación
  manual (match/dismiss) como contraparte necesaria de cualquier
  clasificación automática imperfecta — es parte del costo de esta decisión,
  no un extra opcional.
- No implementa por sí sola cobro, sanción ni control de acceso a partir de
  una clasificación `DEPARTING`/`APPROACHING` — se mantiene el guardrail de
  tratar ALPR/geometría como evidencia probabilística.

## Trabajo futuro

Esta ADR documenta el punto de partida, no el estado final deseado. Una vez
que HU-004 esté en producción y se acumule evidencia real (tasa de acierto
de `DEPARTING` vs. correcciones manuales en columna 2), evaluar:

- Re-afinar `DIRECTION_MIN_DISPLACEMENT`/`DIRECTION_MIN_CONSISTENCY` con
  datos reales de la cámara actual (los valores por defecto son los
  heredados de cuando se desconectó, sin garantía de que sigan siendo
  correctos).
- Si la tasa de acierto es alta y sostenida, evaluar ampliar el rol de
  `DirectionTracker` más allá del desempate (por ejemplo, como segunda
  confirmación incluso cuando sí hay sesión abierta que matchea, sin
  reemplazar la señal primaria determinística).
- Evaluar señales geométricas o de hardware adicionales (segunda cámara,
  sensor de barrera, zona de detección) si la señal de un único ángulo de
  cámara resulta insuficiente de forma estructural.

Cualquier ampliación de alcance más allá de lo decidido acá requiere su
propia HU o una revisión explícita de esta ADR — no se asume implementada
solo por estar mencionada aquí.

## Referencias

- `api/direction_tracker.py` — implementación de `DirectionTracker`.
- `api/ftp_handler.py::_handle_auto_detection` — punto de integración.
- `api/staging.py` (comentario de cabecera) — contexto de la desconexión
  original del 2026-07-17.
