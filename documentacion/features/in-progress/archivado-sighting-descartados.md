# Feature — Archivado de imágenes de avistamientos descartados

**Etapa Project 4:** sin tarjeta (trabajo técnico sin actor asociado, mismo
criterio que `consolidacion-difusa-avistamientos.md`)
**HUs relacionadas:** ninguna — feature técnica.
**Issues:** pendiente (no se crea salvo pedido explícito del usuario).

## Problema

`consolidate_fuzzy_sightings()` (ver
[ADR-005](../../decisiones/ADR-005-consolidacion-difusa-avistamientos-ocr.md))
marca lecturas perdedoras como `DISMISSED` pero nunca toca su imagen — por
diseño explícito de ese feature. Medido en producción (2026-08-11): ~10-70
lecturas `DISMISSED` por día quedan como archivo físico en
`/ftp/historico/{fecha}/`, con nombre de patente que en varios casos no
tiene sentido, aunque el dashboard ya no las muestre. La carpeta de cada
día nunca se "limpia" sola.

## Resultado esperado

Cuando una lectura pasa a `DISMISSED` (solo en modo activo, no en
`shadow_mode`) y el archivado está habilitado, su imagen se mueve — nunca
se borra — de `/ftp/historico/{fecha}/{archivo}` a una carpeta nueva,
hermana de `/ftp/historico`, con la misma estructura por día:
`/ftp/descartadas/{fecha}/{archivo}`. `detection_log.image_path` se
actualiza para reflejar la nueva ubicación, así que la imagen sigue siendo
accesible.

## Alcance

- `SightingConsolidationSettings.archive_discarded_images`
  (`api/core/config.py`): nuevo campo `bool`, default `False`,
  `SIGHTING_CONSOLIDATION_ARCHIVE_ENABLED` — mismo dataclass de ADR-005, sin
  crear un flag nuevo separado.
- `api/database.py::_archive_discarded_image()`: mueve el archivo
  (`os.replace`, atómico) y devuelve el nuevo `image_path` relativo a
  `/ftp`, o `None` si no se movió nada (ver ADR-006, "Cuándo NO se mueve
  nada").
- Enganchado dentro de `consolidate_fuzzy_sightings()`: solo corre para las
  filas que la propia corrida acaba de pasar a `DISMISSED` (via `RETURNING`
  del `UPDATE` existente) — nunca reprocesa una fila ya archivada en una
  corrida anterior.
- `api/ftp_handler.py::serve_ftp_file`: agrega `"descartadas"` al mapeo de
  carpetas servibles, mismo mecanismo que `historico`/`revisar`.

## No-alcance

- No borra ninguna imagen ni libera espacio en disco — extiende, no
  contradice, el no-alcance de
  [consolidacion-difusa-avistamientos.md](../done/consolidacion-difusa-avistamientos.md)
  (ver ADR-006 para el detalle de por qué "mover" no viola ese contrato).
- No agrega ninguna vista ni listado nuevo en el frontend — el usuario no
  lo pidió. La imagen archivada sigue siendo accesible por URL directa
  (`/api/monitor/file/descartadas/...`), no por una pantalla nueva.
- No cambia el comportamiento de `staging.py` (la deduplicación dentro de
  la ventana corta de 120s, que sí borra hoy vía `_delete_ftp_image`, no se
  toca).
- No se activa (`archive_discarded_images=true`) en el deploy inicial —
  arranca apagado, activación posterior con autorización explícita.
- No se crea issue/Project 4 salvo pedido explícito (no es una HU).

## Contratos

- `parking_sessions`, `DetectionEvent` y el contrato REST existente no
  cambian.
- `detection_log.plate` (el string leído por OCR) nunca se toca — solo
  `image_path` cambia, y solo para reflejar dónde vive realmente el
  archivo.

## Riesgos

- Mover un archivo que en realidad sigue siendo evidencia viva de una
  sesión real. Mitigado: verificado en código que `get_stay_proposals`/
  `build_stay_proposals` solo consideran detecciones `UNMATCHED` — una
  lectura recién pasada a `DISMISSED` nunca pudo haber sido promovida a
  `parking_sessions.entry_image_path`/`exit_image_path` en el instante
  anterior a este cambio (ver ADR-006, "Consecuencias").
- Fallo de filesystem a mitad de un lote (varias lecturas descartadas en la
  misma corrida). Mitigado: cada movimiento es independiente y capturado
  (`try/except OSError`) — un fallo en un archivo no aborta el resto del
  lote ni la transacción de base de datos.

## Verificación

- Unitarios: `_archive_discarded_image()` contra directorios temporales
  (`FTP_ROOT`/`FTP_DISCARDED_DIR` monkeypatcheados) — nunca toca `/ftp`
  real. Casos: movimiento exitoso, `image_path` nulo, archivo inexistente,
  path con forma inesperada, intento de path traversal.
- Integración (`RUN_DB_INTEGRATION_TESTS=1`, mismo patrón
  `_NoCommitConnection` de ADR-005): `archive_discarded_images=True` mueve
  el archivo y actualiza `image_path`; `archive_discarded_images=False`
  (default) dejan el comportamiento actual sin cambios — regresión
  explícita del feature ya activo en producción.
- `py_compile` + import de `api.detect:app` (rutas intactas).

## Criterio de cierre

Implementado y probado en worktree aislado; **no** se activa
(`archive_discarded_images=true`) en el deploy inicial. Activación real en
producción es una decisión separada, posterior, con autorización explícita
del usuario — mismo criterio ya usado para `SIGHTING_CONSOLIDATION_SHADOW_MODE`.
