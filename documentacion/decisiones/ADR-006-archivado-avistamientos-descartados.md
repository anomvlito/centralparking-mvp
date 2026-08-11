# ADR-006 — Archivado de imágenes de avistamientos descartados

**Estado:** `aceptada`
**Fecha:** 2026-08-11
**Creado por:** Francisco (vía sesión asistida)
**HUs relacionadas:** ninguna — feature técnica, ver
[archivado-sighting-descartados.md](../features/in-progress/archivado-sighting-descartados.md)

## Contexto

`consolidate_fuzzy_sightings()` (ver [ADR-005](ADR-005-consolidacion-difusa-avistamientos-ocr.md))
marca como `DISMISSED` las lecturas perdedoras de una ráfaga de OCR
inconsistente — pero, por diseño explícito de ese ADR, **nunca toca el
archivo de imagen**. El resultado, verificado con datos reales de
producción (2026-08-11, ~10-70 lecturas `DISMISSED` por día): la carpeta
`/ftp/historico/{fecha}/` sigue acumulando, indefinidamente, un archivo
`.jpg` por cada lectura perdedora — con nombre de patente que en varios
casos no tiene sentido (p. ej. `PCY8655`, `HCYD05`) — aunque el dashboard ya
no las muestre como avistamientos separados.

El usuario pidió específicamente que la carpeta de cada día en
`/ftp/historico` no acumule patentes sin sentido, sin habilitar un borrado
real todavía.

Se evaluaron tres opciones (ver conversación de esta sesión): (1) mover el
archivo a una subcarpeta dentro del mismo día en `/ftp/historico`, (2)
renombrarlo en el lugar con un sufijo, (3) archivarlo en una carpeta nueva a
nivel de `/ftp`, con la misma estructura por día que `/ftp/historico`. El
usuario eligió la (3).

## Decisión

Cuando `consolidate_fuzzy_sightings()` marca una lectura como `DISMISSED`
(solo con `shadow_mode=false`, igual que hoy) y el nuevo flag
`archive_discarded_images=true` está activo, la imagen de esa lectura se
**mueve** (`os.replace`, no copia+borra) de
`/ftp/historico/{fecha}/{archivo}` a `/ftp/descartadas/{fecha}/{archivo}` —
carpeta nueva, hermana de `/ftp/historico` y `/ftp/revisar`, con la misma
estructura por día. `detection_log.image_path` se actualiza para apuntar a
la nueva ubicación, así que la imagen sigue siendo accesible vía
`/api/monitor/file/descartadas/{fecha}/{archivo}` — nunca queda huérfana.

Esto **extiende** (no contradice sin registro) el no-alcance explícito de
[consolidacion-difusa-avistamientos.md](../features/done/consolidacion-difusa-avistamientos.md):
*"No borra imágenes de `/ftp/historico` ni libera espacio en disco"*. Sigue
siendo cierto: no se borra nada y no se libera espacio (la imagen ocupa el
mismo disco, solo cambia de carpeta). El contrato de
[`matching-revisable-detecciones.md`](../features/done/matching-revisable-detecciones.md)
("evidencia y OCR original son inmutables") tampoco se rompe: la imagen no
se altera, no se recomprime, no se le cambia un solo píxel, y el string de
patente leído (`detection_log.plate`) nunca se toca — solo cambia dónde vive
el archivo en disco, con esa ubicación reflejada exactamente en la base de
datos.

Rollout con el mismo patrón de flags que el resto del proyecto
(`SightingConsolidationSettings.archive_discarded_images`, dataclass ya
existente de ADR-005): arranca `false` por defecto. Activarlo en producción
(`SIGHTING_CONSOLIDATION_ARCHIVE_ENABLED=true`) es una decisión separada,
posterior, con autorización explícita — mismo criterio ya usado dos veces
hoy para `SIGHTING_CONSOLIDATION_SHADOW_MODE` y `VEHICLE_FILTER_*`.

## Por qué mover y no copiar+borrar, ni symlink

- **Mover (`os.replace`)** es atómico dentro del mismo filesystem (mismo
  criterio que ya usa `ftp_handler._append_ftp_event` para su escritura
  atómica) y no duplica espacio en disco ni un instante.
- **Copiar y luego borrar** deja una ventana donde el archivo existe dos
  veces, o ninguna, si el proceso se interrumpe entre medio — sin ganar
  nada frente a mover.
- **Symlink** fue descartado: mantiene el archivo "sucio" visible en
  `/ftp/historico/{fecha}/` (el problema original que se quiere resolver),
  solo lo esconde de un `ls` superficial.

## Cuándo NO se mueve nada (fail-safe, no fail-loud)

`_archive_discarded_image()` devuelve `None` — deja `image_path` sin tocar
en la base de datos, mismo comportamiento que hoy — en cualquiera de estos
casos, sin lanzar excepción (una falla acá nunca puede tumbar
`consolidate_fuzzy_sightings`, mismo criterio que el `try/except` ya
aplicado al audit_sink de `VEHICLE_FILTER_EVAL`):

- `image_path` es `NULL` (detecciones sin imagen asociada).
- El archivo ya no existe físicamente en la ruta esperada.
- El path no tiene la forma exacta `historico/{fecha}/{archivo}` (protege
  contra mover algo que no sea una imagen de `/ftp/historico`, incluida
  cualquier ruta ya reubicada por una corrida anterior).
- `os.replace()` falla por cualquier motivo de filesystem (permisos, disco
  lleno, etc.) — capturado explícitamente.

## Consecuencias

- No reduce el uso de disco total (nada se borra) — solo reorganiza dónde
  vive cada imagen. La limpieza real de espacio sigue siendo una decisión
  aparte, no autorizada por este ADR.
- `/ftp/historico/{fecha}/` queda, con el paso de las corridas, con
  únicamente las patentes que el sistema considera reales — que es
  exactamente lo que motivó este cambio.
- Nueva superficie: `/api/monitor/file/descartadas/{fecha}/{archivo}` (solo
  lectura, mismo mecanismo de autorización — o falta de ella, igual que
  `historico`/`revisar` hoy — que las rutas existentes; no se cambia el
  modelo de acceso a imágenes en este ADR).
- Una vez `DISMISSED`, ninguna función del sistema vuelve a mirar esa
  detección — verificado en esta sesión: `get_stay_proposals`/
  `build_stay_proposals` solo consideran `UNMATCHED`, y no existe ningún
  endpoint de "restaurar" un `DISMISSED`. Mover la imagen en ese momento no
  puede romper ninguna referencia viva en `parking_sessions`.
