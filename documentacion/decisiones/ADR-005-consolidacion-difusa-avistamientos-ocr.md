# ADR-005 — Consolidación difusa de avistamientos por ráfaga de OCR inconsistente

**Estado:** `aceptada`
**Fecha:** 2026-08-10
**Creado por:** Francisco (vía sesión asistida)
**HUs relacionadas:** ninguna — feature técnica, ver
[consolidacion-difusa-avistamientos.md](../features/in-progress/consolidacion-difusa-avistamientos.md)

## Contexto

Un vehículo real, en una sola ráfaga frente a la cámara, puede generar
varios avistamientos con patentes **distintas** cuando el OCR falla en la
mayoría de los frames. Caso real (`/ftp/historico/2026-08-10`): la patente
`PCYD65` se leyó correctamente 3 veces en 54 segundos, pero también se leyó
como `CCYD65`, `PCYD55`, `HCYD63`, `HCYD05`, `PCY8655` y `PCYI65` — 7
avistamientos de ruido para un solo auto, cada uno con su propia imagen en
`/ftp/historico`.

La causa: `staging_submit()` (`api/staging.py`) dedupe por **string exacto**
dentro de una ventana de 2 minutos (`STAGING_TTL_SECONDS`). Lecturas con
strings distintos entre sí nunca compiten — cada una abre su propia ventana
y se promueve como avistamiento independiente. El mecanismo de corrección
difusa existente (`find_similar_active_session`, distancia ≤2) solo revisa
sesiones abiertas en `parking_sessions`, que desde el 2026-07-17 casi no se
abren automáticamente (entrada/salida es manual) — no cubre esta capa.

## Decisión

Agregar `consolidate_fuzzy_sightings(date)` (`api/database.py`), un job
post-hoc y disparado por un admin (`POST /api/sightings/consolidate-fuzzy`,
mismo patrón que `POST /api/stays/auto-reconcile-exact`), que:

1. Lee las lecturas **crudas** de `staging_detections` del día (no los
   avistamientos ya promovidos a `detection_log`) — ahí vive la confianza
   real por lectura y la multiplicidad completa, incluidas las que
   perdieron su propia competencia interna dentro de staging.
2. Filtra por confianza cruda de OCR ≥ `min_confidence` (0.90 por defecto)
   **antes** de agrupar.
3. Agrupa lecturas de la misma patente-o-parecida (distancia de edición ≤
   `max_distance`, 1 por defecto) dentro de una ventana corta
   (`window_seconds`, 90s por defecto) — comparando cada lectura nueva
   contra la patente **mayoritaria** del grupo hasta el momento, no contra
   la de mayor confianza individual.
4. Dentro de un grupo con más de una patente distinta, la ganadora es la que
   más veces se repite igual entre las lecturas filtradas (empate se
   desempata por confianza promedio) — ver "Iteración de diseño" abajo.
5. Los avistamientos promovidos (`detection_log`) de las patentes
   perdedoras pasan a `match_status = 'DISMISSED'`. Nunca se borra una
   imagen ni se sobrescribe la patente leída de ninguna detección — mismo
   contrato ya establecido en
   [`matching-revisable-detecciones.md`](../features/done/matching-revisable-detecciones.md)
   ("evidencia y OCR original son inmutables").

Rollout con flags de apagado seguro, mismo patrón que ADR-001/ADR-004
(`SightingConsolidationSettings`: `enabled`, `shadow_mode`, `max_distance`,
`window_seconds`, `min_confidence`). Arranca `enabled=false`; con
`enabled=true` arranca en `shadow_mode=true` (audita qué agruparía y quién
ganaría, no marca nada). Solo con `shadow_mode=false` se ejecuta el
`DISMISSED` real.

## Iteración de diseño (por qué no "la de mayor confianza gana")

El primer diseño usaba la confianza ya promovida a `detection_log`
(`combined_score`: confianza × 0.7 + calidad de imagen × 0.3) para elegir la
patente ganadora de un grupo. Contra los datos reales de este mismo caso,
ese diseño **eligió mal**: `PCYD55` (incorrecta) tuvo `combined_score`
0.9509 contra 0.9549 de `PCYD65` (correcta) — perdía por nitidez de imagen,
no por lectura. Un segundo intento (confianza cruda de la única lectura
promovida por string) tampoco alcanzaba: la lectura de `PCYD65` que
sobrevivió su propia competencia interna de staging tenía confianza cruda
0.9989, todavía por debajo del 0.9991 de `PCYD55`.

Se corrigió mirando **todas** las lecturas crudas de cada string (no solo la
promovida) y votando por **frecuencia**: `PCYD65` aparece 3 veces entre las
lecturas con confianza ≥90%, ninguna otra patente se repite tanto — gana por
cantidad, con la confianza promedio como desempate solo en caso de empate.
Verificado con tests contra los números reales de la ráfaga
(`tests/test_sighting_consolidation.py`).

## Incidente durante el desarrollo

Una prueba de integración con el **primer** diseño (canónica por
`combined_score`) corrió `consolidate_fuzzy_sightings` en modo activo contra
Postgres real completo (la función escanea el día entero, no IDs
sintéticos como el resto de `test_reconciliation_integration.py`) y marcó
**28 avistamientos reales** de producción como `DISMISSED` por error.
Revertido a `UNMATCHED` de inmediato (evento de auditoría `SIGHTING_UNDO`,
sin pérdida de evidencia — imágenes y patentes originales nunca se
tocaron). Las pruebas de integración se reescribieron para correr dentro de
una única transacción que siempre se revierte (`_NoCommitConnection` en
`tests/test_sighting_consolidation_integration.py`), sin importar el
resultado del test.

## Alternativas consideradas

1. **Operar sobre `detection_log` (avistamientos ya promovidos) en vez de
   `staging_detections`.** Descartada: ahí solo queda `combined_score` (una
   mezcla con calidad de imagen) y un único valor por string — se pierde la
   multiplicidad de lecturas que hace confiable el voto por frecuencia (ver
   "Iteración de diseño").
2. **Fusionar/borrar en el momento de la captura** (dentro de
   `staging_submit()`), en vez de post-hoc. Descartada: una decisión
   equivocada en tiempo real pierde la imagen antes de poder revisarla —
   post-hoc, todas las imágenes candidatas ya existen en disco cuando se
   decide.
3. **Umbral de distancia más amplio (≤2, igual que
   `find_similar_active_session`)** para agrupar el caso completo (incluido
   `HCYD63`, a distancia 2 de `PCYD65`). Descartada por el usuario: mayor
   riesgo de fusionar dos autos reales con patentes parecidas que entren en
   la misma ventana — prioridad en seguridad sobre cobertura completa.
   `HCYD63` queda como avistamiento suelto, sin peor comportamiento que
   antes de este feature.
4. **Correr automáticamente en el loop de background** (`staging_loop`,
   cada 30s) en vez de a demanda de un admin. Descartada por ahora: mismo
   criterio que `auto_reconcile_exact_matches`, que tampoco es automático —
   mantener toda acción que afecta el estado de revisión de evidencia
   detrás de un disparo explícito mientras el umbral no esté calibrado con
   datos reales.

## Consecuencias

- No reduce el uso de disco (no borra imágenes) — solo reduce ruido en la
  cola de avistamientos y evita que `build_stay_proposals`/reconciliación
  intente emparejar una lectura errónea con algo. Limpieza de disco sigue
  siendo una decisión separada, con autorización explícita como las ya
  hechas en esta sesión.
- Falso positivo de fusión (dos autos reales distintos, patentes a
  distancia ≤1, en la misma ventana de 90s) queda posible en teoría — no
  hay señal de posición/dirección confiable en esta cámara (ver ADR-003) que
  lo descarte. Mitigado por: umbral de distancia angosto, ventana corta,
  filtro de confianza previo, y sobre todo por el hecho de que el peor caso
  es perder la visibilidad independiente de un avistamiento, no cerrar una
  sesión real ni afectar un cobro (`match_status` no autoriza cobro,
  sanción ni acceso por sí solo).
- No cambia el contrato de `parking_sessions`/`DetectionEvent` ni las rutas
  consumidas por el frontend existentes.

## Trabajo futuro

- Correr en `shadow_mode` contra tráfico real y revisar visualmente una
  muestra de los grupos propuestos (¿alguno junta autos que en las fotos son
  claramente distintos?) antes de autorizar `shadow_mode=false`.
- Si se calibra bien, evaluar extender `max_distance` a 2 con evidencia real
  de que no aumenta la tasa de fusiones incorrectas.

Cualquier ampliación de alcance más allá de lo decidido acá requiere su
propia HU o una revisión explícita de esta ADR.
