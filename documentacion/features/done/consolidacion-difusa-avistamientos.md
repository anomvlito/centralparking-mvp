# Feature — Consolidación difusa de avistamientos por ráfaga de OCR inconsistente

**Etapa Project 4:** `Done` (sin tarjeta en Project 4 — no se creó
issue, trabajo técnico sin actor asociado)
**HUs relacionadas:** ninguna — feature técnica (AGENTS.md: "trabajo
puramente técnico... no se fuerza a una HU").
**Issues:** pendiente (no se crea salvo pedido explícito del usuario).

## Problema

Un vehículo real puede generar varios avistamientos con patentes distintas
en una sola ráfaga cuando el OCR falla en la mayoría de los frames. Caso
real (`/ftp/historico/2026-08-10`): `PCYD65` correcta 3 veces en 54s, pero
también leída como `CCYD65`, `PCYD55`, `HCYD63`, `HCYD05`, `PCY8655` y
`PCYI65` — 7 avistamientos de ruido para un solo auto. El mecanismo de
corrección difusa existente (`find_similar_active_session`) solo cubre
sesiones abiertas en `parking_sessions`, que casi no se abren
automáticamente desde el 2026-07-17 — no alcanza a esta capa.

## Resultado esperado

Un job post-hoc, disparado por un admin, agrupa lecturas crudas de
`staging_detections` por proximidad de tiempo y distancia de edición de
patente, filtradas por confianza mínima de OCR, y elige la patente ganadora
por frecuencia (no por confianza individual — ver ADR-005 para el porqué).
Los avistamientos perdedores del grupo pasan a `DISMISSED`; nada se borra
ni se sobrescribe.

## Alcance

- `SightingConsolidationSettings` (`api/core/config.py`): `enabled`,
  `shadow_mode`, `max_distance` (1), `window_seconds` (90),
  `min_confidence` (0.90) — mismo patrón de rollout seguro que
  `VehicleFilterSettings`/`DirectionSettings`.
- `consolidate_fuzzy_sightings(date)` (`api/database.py`): lee
  `staging_detections` del día, filtra por confianza, agrupa, decide
  ganadora por voto de frecuencia, marca perdedoras como `DISMISSED` (solo
  si `shadow_mode=false`), audita cada grupo (`SIGHTING_CONSOLID`).
- `POST /api/sightings/consolidate-fuzzy?date=YYYY-MM-DD` (admin), mismo
  patrón que `POST /api/stays/auto-reconcile-exact`.
- `shadow_mode` (auditar sin marcar) como paso obligatorio antes de activar
  el `DISMISSED` real.

## No-alcance

- No borra imágenes de `/ftp/historico` ni libera espacio en disco — el
  contrato de este dominio ("evidencia y OCR original son inmutables",
  `matching-revisable-detecciones.md`) no lo permite. Limpieza de disco
  sigue siendo una decisión aparte, con autorización explícita.
- No se toca el frontend.
- No corre automáticamente en el loop de background — solo a demanda de un
  admin, mismo criterio que `auto_reconcile_exact_matches`.
- No se activa (`enabled=true`) en el deploy inicial.
- No se crea issue/Project 4 salvo pedido explícito (no es una HU).

## Contratos

- `parking_sessions`, `DetectionEvent` y el contrato REST existente no
  cambian.
- Solo agrega interpretación (`detection_log.match_status`); nunca borra ni
  sobrescribe `plate`/`image_path`.

## Riesgos

- Fusionar dos autos reales con patentes a distancia ≤1 en la misma ventana
  de 90s. Mitigado con umbral angosto, filtro de confianza previo y el
  hecho de que el peor caso es perder visibilidad de un avistamiento —no
  cerrar una sesión real ni afectar cobro (ver ADR-005, "Consecuencias").

## Criterio de cierre

El job corre en `shadow_mode` contra tráfico real durante un período de
calibración, se revisa visualmente una muestra de los grupos propuestos, y
solo entonces se decide (con autorización explícita) activar el `DISMISSED`
real en producción.

## Evidencia de implementación

- `api/core/config.py::SightingConsolidationSettings`,
  `api/database.py::consolidate_fuzzy_sightings()` (+ `_majority_plate()`,
  `_cluster_staging_reads()`, `_get_staging_reads_for_date()`),
  `api/services/reconciliation.py::consolidate_fuzzy()`,
  `api/routers/reconciliation.py::POST /api/sightings/consolidate-fuzzy`.
- Tests: `tests/test_sighting_consolidation.py` (14 casos unitarios —
  settings, voto por mayoría, clustering, caso real 2026-08-10 con los
  números exactos de la ráfaga) + `tests/test_sighting_consolidation_integration.py`
  (4 casos contra Postgres real, corridos dentro de una transacción que
  siempre se revierte). Suite completa: 83/83 OK.
- Ver [ADR-005](../../decisiones/ADR-005-consolidacion-difusa-avistamientos-ocr.md)
  para la iteración de diseño (dos intentos descartados con evidencia real)
  y el incidente de desarrollo (28 avistamientos reales marcados
  `DISMISSED` por error durante una prueba con el diseño anterior,
  revertidos de inmediato).

## Activación en producción (2026-08-10)

- **Calibración en `shadow_mode`:** corrida contra el tráfico real del día
  (39 grupos detectados, solo auditados). Muestra de 5 grupos verificada
  visualmente contra las imágenes reales de `/ftp/historico/2026-08-10`
  (`HGYB41`/`BGYB41`, `SHKV20`/`PHKV20`, `ZP2127`/`ZP2117`,
  `RXLY54`/`CXLY54`, además del caso original `PCYD65`) — en los 5 casos la
  ganadora elegida coincide con lo que se ve a simple vista en la foto,
  ninguna fusión mezcla dos vehículos distintos.
- **Activación real:** `SIGHTING_CONSOLIDATION_SHADOW_MODE=false` (drop-in
  `/etc/systemd/system/centralparking.service.d/40-sighting-consolidation.conf`).
  Corrida manual contra el día: 39 grupos, 34 avistamientos marcados
  `DISMISSED` (los 5 restantes ya habían sido resueltos por la conciliación
  de estadías, sin fila que tocar).
- **Enganche al frontend:** `consolidateFuzzySightings(date)` agregado al
  refresco automático del dashboard (`Dashboard.tsx::load()`, cada
  `DASHBOARD_REFRESH_MS` = 15s mientras esté abierto), mismo patrón ya
  usado por `autoReconcileExact` — sin botón ni acción nueva del admin.
  Frontend: [adyac-camaras-frontend#15](https://github.com/anomvlito/adyac-camaras-frontend/pull/15),
  Vercel Production verificado (`commit status: success`).
- **Límite conocido:** solo corre mientras el dashboard está abierto (no es
  un cron real en el backend) — decisión aparte si se quiere independizar
  de eso.
