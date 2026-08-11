# Feature — Consolidación difusa incluye lecturas de longitud inválida

**Etapa Project 4:** sin tarjeta (trabajo técnico sin actor asociado, mismo
criterio que las dos features de consolidación anteriores).
**HUs relacionadas:** ninguna — feature técnica.
**Issues:** pendiente (no se crea salvo pedido explícito del usuario).

## Problema

Revisión manual del usuario sobre `/ftp/historico/2026-08-11`: encontró
varios pares del mismo auto con lecturas de OCR distintas, ambas todavía
visibles, a pesar de la consolidación difusa ya activa. La causa dominante
(6 de 10 casos reportados, ver [ADR-007](../../decisiones/ADR-007-consolidacion-incluye-longitud-invalida.md)):
`_cluster_staging_reads()` excluye cualquier lectura cuyo string no tenga
exactamente 6 caracteres antes de agrupar, y esas lecturas quedan
promovidas con `match_status = 'INVALID_FORMAT'` — un estado que ninguna
función del sistema vuelve a tocar. Quedan para siempre en `historico`.

## Resultado esperado

Una lectura de longitud distinta a 6 (ej. `TJB56`, dropeó la "C" inicial de
`CTJB56`) puede competir dentro del mismo grupo que su hermana correcta —
la distancia de edición ya las relaciona bien (inserción/borrado de un
carácter = distancia 1) — pero **nunca puede ganar** si el grupo tiene
algún candidato de 6 caracteres. Al perder, queda `DISMISSED` igual que
cualquier otra perdedora, y con el archivado de ADR-006 ya activo, su
imagen se mueve sola a `/ftp/descartadas` sin tocar ese código.

## Alcance

- `api/database.py::_cluster_staging_reads()`: se quita el filtro
  `len(r["plate"]) == 6` de la lista `valid` — la admisión al grupo pasa a
  depender solo de `max_distance` (ya existente, sin cambios).
- `api/database.py::_majority_plate()`: si el grupo tiene algún candidato
  de 6 caracteres, la ganadora sale solo de ese subconjunto; si ninguno
  tiene 6 caracteres, vota entre todos (mismo comportamiento que hoy).
- `api/database.py::consolidate_fuzzy_sightings()`: el `SELECT`/`UPDATE`
  que busca y marca perdedoras pasa de `match_status = 'UNMATCHED'` a
  `match_status IN ('UNMATCHED', 'INVALID_FORMAT')`.

## No-alcance

- **No toca la Causa B** (distancia de edición 2 entre dos lecturas de 6
  caracteres — `PGSY86`/`BGSY06`, `VCWY15`/`CWY155`, `RPTD80`/`RP7080`).
  Reabrir `max_distance` es una decisión aparte, ya evaluada y rechazada
  una vez en ADR-005 por riesgo de fusionar autos distintos.
- No cubre un auto cuyas lecturas **nunca** alcanzan 6 caracteres (ninguna
  lectura hermana válida en la ventana) — sigue sin cobertura, igual que
  hoy.
- No hace backfill retroactivo de `INVALID_FORMAT` existentes — eso es una
  decisión aparte, con autorización explícita, mismo criterio que el
  backfill de ADR-006 (y con la lección aprendida ese día: cualquier
  backfill futuro debe excluir explícitamente filas con
  `linked_session_id IS NOT NULL`).
- No cambia `log_to_db()` ni cómo se asigna `INVALID_FORMAT` al promover
  — solo qué pasa con esa fila *después*, dentro de la consolidación.

## Contratos

- `parking_sessions`, `DetectionEvent` y el contrato REST no cambian.
- El ganador de un grupo nunca puede ser una lectura de longitud inválida
  si existe al menos un candidato de 6 caracteres — no se debilita ninguna
  garantía existente, solo se amplía qué compite como perdedora.

## Riesgos

- Ampliar el pool de candidatos podría, en teoría, hacer que una lectura
  de longitud inválida de **otro** auto se cuele en el grupo si cae dentro
  de la misma ventana y a distancia <= `max_distance` de la representante.
  Mitigado: mismo `max_distance`/`window_seconds` ya aceptados en ADR-005,
  sin ampliar ningún radio — el riesgo es idéntico al ya asumido para
  candidatos de 6 caracteres, solo se extiende a longitudes distintas.
- Confianza baja en lecturas de longitud inválida podría colar ruido de
  fondo. Mitigado: `min_confidence` (0.90) ya se aplica antes de agrupar,
  sin cambios — verificado con datos reales que los casos de baja
  confianza (`CSB77` 0.6968, `STW4489` 0.7462) ya quedan filtrados ahí.

## Verificación

- Unitarios: `_majority_plate()` prefiere formato válido con votos en
  contra; fallback sin ningún candidato de 6 caracteres; `_cluster_staging_reads()`
  admite longitudes distintas dentro de distancia; par a distancia 2 con
  longitudes distintas sigue sin agruparse (no regresión de Causa B por
  otra vía).
- Integración (`RUN_DB_INTEGRATION_TESTS=1`, mismo patrón
  `_NoCommitConnection`): reproduce el caso real
  `TJB56`/`CTJB56`/`CIJB56` completo — `TJB56` (`INVALID_FORMAT`) termina
  `DISMISSED`; con `archive_discarded_images=True` su imagen se archiva sin
  tocar código de ADR-006. Caso de longitud inválida con confianza < 0.90
  nunca se toca (regresión).
- `py_compile` + import de `api.detect:app`.

## Criterio de cierre

Implementado y probado en worktree aislado. Activación en producción: el
código ya desplegado de `consolidate_fuzzy_sightings`/`archive_discarded_images`
sigue corriendo con la misma configuración ya activa (`SIGHTING_CONSOLIDATION_ENABLED=true`,
`SHADOW_MODE=false`, `ARCHIVE_ENABLED=true`) — no requiere ningún flag
nuevo. El deploy mismo activa el fix; no hay paso de activación separado
como en ADR-005/006.
