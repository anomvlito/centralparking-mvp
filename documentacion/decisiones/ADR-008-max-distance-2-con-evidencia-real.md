# ADR-008 — Ampliar `max_distance` de 1 a 2, con evidencia real

**Estado:** `aceptada`
**Fecha:** 2026-08-11
**Creado por:** Francisco (vía sesión asistida)
**HUs relacionadas:** ninguna — feature técnica.
**Reabre:** [ADR-005](ADR-005-consolidacion-difusa-avistamientos-ocr.md),
sección "Alternativas consideradas", punto 3.

## Contexto

Tras activar [ADR-006](ADR-006-archivado-avistamientos-descartados.md) y
[ADR-007](ADR-007-consolidacion-incluye-longitud-invalida.md), el usuario
revisó a mano `/ftp/historico/2026-08-11` y encontró pares del mismo auto
que seguían sin consolidarse porque su distancia de edición real es 2, no 1
— el umbral que ADR-005 dejó a propósito en 1, citando el riesgo de
fusionar dos autos reales con patentes parecidas. Ejemplos reales:
`PGSY86`/`BGSY06`, `HPVF43`/`HPVF2`, `TSBZ38`/`KSBZ38`.

Un cuarto ejemplo (`HZB55`/`FHZB55`, con ~135s de separación) inicialmente
parecía un problema de `window_seconds` (90s) demasiado corta — pero el
usuario, mirando las imágenes con más contexto, identificó que el auto dio
una vuelta buscando dónde estacionar: son dos pasadas reales por la cámara,
no un único evento de permanencia larga. **Por eso este ADR no toca
`window_seconds`** — ampliarlo hubiera sido resolver un problema que en
realidad no existe.

## Por qué se reabre ADR-005 y no se descarta de nuevo

ADR-005 rechazó ampliar `max_distance` sin evidencia cuantitativa — una
decisión conservadora razonable en ese momento (feature recién creada, sin
datos de producción con la consolidación activa todavía). Ahora sí hay
datos reales de un día completo con la consolidación y el archivado activos
end-to-end, lo que permite medir el trade-off real en vez de estimarlo.

## Evidencia

Script de análisis (no forma parte del pipeline, solo diagnóstico) sobre
`staging_detections` real del 2026-08-11 (603 lecturas con confianza
≥0.90) y del 2026-08-10 (52 lecturas):

- **Beneficio**: ampliar `max_distance` de 1 a 2 (`window_seconds` sin
  cambios, 90s) agrupa correctamente **15 casos adicionales** el
  2026-08-11 que hoy quedan sueltos. En cada uno se revisó el conteo de
  lecturas crudas por patente dentro del grupo: siempre hay una ganadora
  clara por mayoría (2 a 4 lecturas de la patente real contra 1 lectura
  suelta de una variante), el mismo patrón de "un auto, ráfaga con ruido"
  que ya sustenta ADR-005 — no dos patentes compitiendo de igual a igual.
- **Riesgo**: se buscó explícitamente el patrón de falso positivo que
  preocupaba a ADR-005 — dos grupos **ya bien establecidos por separado**
  (3 o más lecturas cada uno, es decir dos autos ya identificados con
  confianza independiente) que se fusionan en uno solo al ampliar la
  distancia. Sobre el 2026-08-11 y el 2026-08-10: **cero casos** de ese
  patrón.
- Los demás días recientes (`2026-08-04`, `2026-08-06`, `2026-08-07`) no
  tienen lecturas en `staging_detections` para comparar — la tabla no
  retiene el detalle crudo indefinidamente, así que el análisis cuantitativo
  queda acotado a los dos días con datos disponibles.

## Decisión

`SightingConsolidationSettings.max_distance` cambia su valor por defecto de
`1` a `2`. `window_seconds` **no se toca** (sigue en 90s) — el caso que
motivó considerarlo (`HZB55`) resultó ser un auto real dando dos pasadas,
no una ventana insuficiente.

Es un cambio de configuración, no de mecanismo: `max_distance` ya era un
parámetro validado y soportado (`__post_init__` acepta `{0, 1, 2}` desde
ADR-005) — sin cambios de código en `_cluster_staging_reads`,
`_majority_plate` ni `consolidate_fuzzy_sightings`. Mismo criterio que las
tres tuneadas anteriores de esta sesión (piso de confianza del ALPR,
umbral del filtro de vehículo): un ajuste de parámetro documentado con su
propio PR y ADR, no una edición silenciosa de variable de entorno.

## Riesgo residual

Sigue siendo, en teoría, posible que dos autos reales con patentes a
distancia de edición 2 crucen la cámara dentro de la misma ventana de 90s
y se fusionen por error — ningún análisis de un par de días de datos puede
descartar esto con certeza absoluta, igual que ADR-005 ya reconocía para
distancia 1. Mitigado por lo mismo que ya mitiga ese riesgo hoy: el peor
caso es perder visibilidad de un avistamiento suelto (nunca cierra una
sesión real ni autoriza cobro — `match_status` no tiene ese poder), y
`min_confidence=0.90` ya filtra la mayoría del ruido antes de llegar a
agrupar.

## Consecuencias

- Reduce más el ruido en `/ftp/historico` (vía el archivado ya activo de
  ADR-006), sin flag nuevo ni paso de activación aparte — mismo criterio
  que ADR-007.
- No cambia `window_seconds`, `min_confidence` ni ningún otro parámetro.
- Si en el futuro aparece evidencia real de una fusión incorrecta con
  distancia 2, revertir es tan simple como volver el default a 1 — no hay
  dato irreversible en juego (ninguna imagen se borra, ver ADR-005/006).
