# Feature — Ampliar `max_distance` de la consolidación difusa a 2

**Etapa Project 4:** sin tarjeta (trabajo técnico sin actor asociado).
**HUs relacionadas:** ninguna — feature técnica.
**Issues:** pendiente (no se crea salvo pedido explícito del usuario).

## Problema

Revisión manual del usuario sobre `/ftp/historico/2026-08-11`, después de
ADR-006/007: quedaban pares del mismo auto sin consolidar porque su
distancia de edición real es 2 (`PGSY86`/`BGSY06`, `HPVF43`/`HPVF2`,
`TSBZ38`/`KSBZ38`), por encima del `max_distance=1` que ADR-005 dejó a
propósito, sin evidencia cuantitativa disponible en ese momento.

## Resultado esperado

Con datos reales de un día completo (`max_distance=1` activo en
producción), se midió el trade-off real: 15 casos adicionales resueltos el
2026-08-11, cero señales del patrón de riesgo que preocupaba a ADR-005
(fusión de dos grupos ya bien establecidos por separado). Ver
[ADR-008](../../decisiones/ADR-008-max-distance-2-con-evidencia-real.md).

## Alcance

- `SightingConsolidationSettings.max_distance` (`api/core/config.py`):
  default `1` → `2`. Campo y validación ya existían desde ADR-005 — sin
  cambios de código en la lógica de clustering/votación.

## No-alcance

- **No toca `window_seconds`** — el caso que lo motivó (`HZB55`) resultó
  ser un auto real dando dos pasadas por la cámara buscando dónde
  estacionar, no un problema de ventana insuficiente.
- No cambia `min_confidence` ni ningún otro parámetro.
- No hace backfill retroactivo — aplica hacia adelante, igual que
  ADR-007.

## Contratos

- `SightingConsolidationSettings.__post_init__` ya validaba
  `max_distance in {0, 1, 2}` desde ADR-005 — sin cambios de validación.
- No cambia `parking_sessions`, `DetectionEvent` ni el contrato REST.

## Riesgos

- Riesgo residual de fusionar dos autos reales con patentes a distancia 2
  dentro de la misma ventana de 90s — no se puede descartar con certeza
  absoluta a partir de dos días de datos. Mitigado por lo mismo que ya
  mitiga distancia 1 hoy: el peor caso es perder visibilidad de un
  avistamiento suelto, nunca cierra una sesión real ni autoriza cobro.
  Reversible de inmediato si aparece evidencia de una fusión incorrecta.

## Verificación

- Unitarios: default de `SightingConsolidationSettings` ahora es 2;
  `_cluster_staging_reads`/`_majority_plate` ya soportaban `max_distance=2`
  desde ADR-005 (parámetro explícito), sin cambios de código ahí.
- Integración: caso real `HPVF43`/`HPVF2` (distancia 2) se consolida
  correctamente con el nuevo default; distancia 3 sigue sin fusionar (no
  regresión).
- `py_compile` + import de `api.detect:app`.

## Criterio de cierre

Implementado y probado en worktree aislado. Sin flag nuevo ni paso de
activación aparte — el deploy mismo lo activa, mismo criterio que ADR-007.
