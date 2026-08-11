# Feature — Bajar `min_confidence` de la consolidación difusa a 0.70

**Etapa Project 4:** sin tarjeta (trabajo técnico sin actor asociado).
**HUs relacionadas:** ninguna — feature técnica.
**Issues:** pendiente (no se crea salvo pedido explícito del usuario).

## Problema

Con ADR-007 (longitud) y ADR-008 (distancia) ya desplegados, la causa
dominante de duplicados sin consolidar en `/ftp/historico/2026-08-11` pasó
a ser casi por completo la confianza cruda de la lectura perdedora, por
debajo de `min_confidence=0.90` — el filtro que decide qué lecturas
compiten, antes de evaluar distancia o longitud. Auditoría completa del
día: de 31 pares candidatos a duplicado, ~26 comparten esta única causa.

## Resultado esperado

Con datos reales de dos días completos, se midió el trade-off: bajar
`min_confidence` a 0.70 (mismo piso que ya usa el ALPR para decidir si una
lectura se guarda como archivo, `MIN_SINGLE_VOTE_CONFIDENCE`) resuelve 16
casos adicionales el 2026-08-11, sin cambiar ninguna ganadora ya
establecida en ningún nivel probado (0.90→0.85→0.80→0.75→0.70). Ver
[ADR-009](../../decisiones/ADR-009-min-confidence-070-con-evidencia-real.md).

## Alcance

- `SightingConsolidationSettings.min_confidence` (`api/core/config.py`):
  default `0.90` → `0.70`. Campo y validación ya existían desde ADR-005 —
  sin cambios de código en clustering/votación.

## No-alcance

- No toca `max_distance` ni `window_seconds`.
- No aborda el caso de empate 1-voto-contra-1-voto con desempate por
  confianza (visto en vivo con `VWYF21`/`WYF211`) — costo bajo (no limpia
  una imagen, nunca daña evidencia real), queda anotado en ADR-009 como
  riesgo residual, no resuelto acá.
- No hace backfill retroactivo.

## Contratos

- `SightingConsolidationSettings.__post_init__` ya validaba
  `0 < min_confidence < 1` desde ADR-005 — sin cambios de validación.
- No cambia `parking_sessions`, `DetectionEvent` ni el contrato REST.

## Riesgos

- Ver ADR-009, "Riesgo residual" — empates más frecuentes entre lecturas
  de un solo voto, sin impacto en evidencia real (el código nunca toca una
  detección ya `MATCHED_ENTRY`/`MATCHED_EXIT`).

## Verificación

- Unitarios: default de `SightingConsolidationSettings` ahora es 0.70.
- Integración: caso real de confianza baja (`RPTD80`/`RP7080`) se
  consolida con el nuevo default; una lectura por debajo de 0.70 sigue sin
  tocarse (no regresión).
- `py_compile` + import de `api.detect:app`.

## Criterio de cierre

Implementado y probado en worktree aislado. Sin flag nuevo ni paso de
activación aparte — mismo criterio que ADR-007/ADR-008.
