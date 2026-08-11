# ADR-007 — La consolidación difusa deja de excluir lecturas de longitud inválida

**Estado:** `aceptada`
**Fecha:** 2026-08-11
**Creado por:** Francisco (vía sesión asistida)
**HUs relacionadas:** ninguna — feature técnica, ver
[consolidacion-incluye-longitud-invalida.md](../features/in-progress/consolidacion-incluye-longitud-invalida.md)

## Contexto

Revisión manual del usuario sobre `/ftp/historico/2026-08-11` tras activar y
hacer backfill de [ADR-006](ADR-006-archivado-avistamientos-descartados.md):
encontró varios pares/tríos de imágenes del mismo auto, con distinta lectura
de OCR, que seguían **ambas** visibles en `historico` — el problema que
`consolidate_fuzzy_sightings` (ADR-005) debía resolver.

Clasificados con datos reales del día, los casos caen en tres causas
distintas:

1. **Longitud de patente distinta a 6 caracteres** (la mayoría de los casos
   reportados: `TJB56`/`CTJB56`, `DKJ82`/`HDKJ82`, `GBT38`/`PGBT38`,
   `CWY15`/`VCWY15`, `CSB77`/`TSBZ38`, `STW4489`/`CSTW44`).
   `_cluster_staging_reads()` excluye a propósito toda lectura cuyo string
   no tenga exactamente 6 caracteres (`len(r["plate"]) == 6`) antes de
   agrupar — y `log_to_db()` le asigna `match_status = 'INVALID_FORMAT'` en
   vez de `UNMATCHED` al promoverla. El resultado: esa lectura nunca compite
   contra su hermana correcta, nunca se marca `DISMISSED`, nunca se archiva
   — queda para siempre en `/ftp/historico`. **Esta ADR resuelve esta
   causa.**
2. **Distancia de edición 2 entre dos lecturas válidas de 6 caracteres**
   (`PGSY86`/`BGSY06`, `VCWY15`/`CWY155`, `RPTD80`/`RP7080` — todas distancia
   real 2, verificada con `_levenshtein`). El umbral `max_distance=1` las
   deja afuera a propósito — ADR-005 ya evaluó y rechazó explícitamente
   ampliarlo, por el riesgo de fusionar dos autos reales con patentes
   parecidas. **Esta ADR NO toca esto** — queda pendiente, a decidir aparte.
3. **Evidencia de una sesión real** (`CTJB56`/`CIJB56`, ligadas a
   `parking_sessions.id=6929`, `VOID`). Ambas imágenes deben seguir
   existiendo por diseño — no es un bug.

## Decisión

`_cluster_staging_reads()` deja de filtrar por longitud exacta de 6 —
cualquier lectura cruda con confianza suficiente (`min_confidence`, ya
aplicado antes de agrupar) puede unirse a un grupo si su distancia de
edición a la patente representante del grupo es `<= max_distance`. La
distancia de edición ya maneja inserciones/borrados de forma nativa
(`_levenshtein("TJB56", "CTJB56") == 1`, aunque tengan longitud distinta),
así que no hace falta ningún filtro de longitud aparte — el mismo umbral que
ya protege contra fusionar autos distintos sigue aplicando exactamente
igual.

`_majority_plate()` cambia su criterio de desempate: si el grupo tiene
**algún** candidato de 6 caracteres (único formato válido de patente
chilena), la ganadora se elige **solo** entre esos candidatos —
independientemente de cuántas veces se repitió uno de longitud inválida.
Solo si **ningún** candidato del grupo tiene 6 caracteres se vota entre los
que hay (mismo comportamiento que hoy, sin cambios, para ese caso extremo).

`consolidate_fuzzy_sightings()` amplía qué detecciones puede marcar
`DISMISSED`: antes solo `match_status = 'UNMATCHED'`, ahora también
`'INVALID_FORMAT'` — así una lectura de longitud inválida que pierde el
voto queda correctamente descartada (y, con
[ADR-006](ADR-006-archivado-avistamientos-descartados.md) ya activo, se
archiva sola, sin cambiar ese código).

## Por qué es seguro

- **Verificado con datos reales de hoy**: `TJB56` (0.9965), `DKJ82`
  (0.9792), `GBT38` (0.9895), `CWY15` (hasta 0.9993) — todas por encima de
  `min_confidence=0.90` a nivel de lectura cruda, así que hoy mismo habrían
  sido detectadas y corregidas con este cambio. Los dos casos de longitud
  inválida que el usuario reportó y que **no** se habrían corregido
  (`CSB77` 0.6968, `STW4489` 0.7462) ya quedan filtrados por
  `min_confidence` de todas formas — mismo resultado que hoy, sin regresión.
- **No amplía el radio de fusión de autos distintos**: sigue siendo el
  mismo `max_distance` ya aceptado en ADR-005 — solo deja de exigir que las
  dos longitudes coincidan exactamente, algo que `_levenshtein` ya
  manejaba correctamente pero que el filtro previo bloqueaba antes de
  llegar a comparar distancia.
- **El ganador nunca puede ser peor que hoy**: si hay algún candidato de 6
  caracteres en el grupo, gana uno de ellos — nunca uno de longitud
  inválida. Antes de este cambio, un candidato de longitud inválida ni
  siquiera entraba a competir, así que el ganador ya salía exclusivamente de
  los válidos; este cambio no lo empeora, solo agrega qué lecturas
  compiten como perdedoras.
- **`INVALID_FORMAT` → `DISMISSED` no interactúa con ningún otro
  consumidor**: verificado que `get_stay_proposals`/`build_stay_proposals`
  solo miran `UNMATCHED` (nunca miraron `INVALID_FORMAT` ni lo harán
  después de `DISMISSED`), y que ninguna otra función depende de que
  `INVALID_FORMAT` sea un estado terminal.

## Consecuencias

- Reduce, no elimina, el ruido de longitud inválida en `/ftp/historico` —
  cubre los casos donde SÍ existe una lectura hermana de 6 caracteres
  dentro de la misma ventana/distancia. Un auto leído mal en **todas** sus
  lecturas (nunca 6 caracteres ni una vez) sigue sin cobertura, igual que
  hoy.
- La Causa B (distancia 2 entre dos lecturas válidas) queda explícitamente
  fuera de esta ADR — pendiente de una decisión aparte sobre si vale la
  pena reabrir el trade-off de ADR-005.
- No cambia el contrato de `parking_sessions`/`DetectionEvent` ni rutas del
  frontend.
