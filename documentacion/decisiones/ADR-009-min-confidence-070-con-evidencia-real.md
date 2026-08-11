# ADR-009 — Bajar `min_confidence` de la consolidación difusa de 0.90 a 0.70

**Estado:** `aceptada`
**Fecha:** 2026-08-11
**Creado por:** Francisco (vía sesión asistida)
**HUs relacionadas:** ninguna — feature técnica.
**Continúa:** [ADR-008](ADR-008-max-distance-2-con-evidencia-real.md) — misma
metodología (evidencia real de producción, buscar explícitamente el patrón
de riesgo antes de decidir).

## Contexto

Con [ADR-007](ADR-007-consolidacion-incluye-longitud-invalida.md) (longitud
inválida) y [ADR-008](ADR-008-max-distance-2-con-evidencia-real.md)
(distancia 2) ya desplegados y corriendo en producción, el usuario siguió
viendo en vivo pares del mismo auto sin consolidar — esta vez con la causa
concentrada casi por completo en un solo lugar: la confianza cruda de la
lectura perdedora, por debajo de `min_confidence=0.90` (el piso que filtra
qué lecturas de `staging_detections` entran a competir, **antes** de que
distancia o longitud siquiera se evalúen). Casos reales en vivo:
`WWVR30` (0.84), `RPEG5` (0.85), `DPG072` (0.82), `WWVF21` (0.84), `WYF21`
(0.86).

Auditoría completa de `/ftp/historico/2026-08-11` (198 archivos, 31 pares
candidatos a duplicado): descontando 3 pares que son evidencia legítima de
sesiones reales y 2 pares que son autos distintos correctamente separados,
**los ~26 restantes comparten la misma causa**: confianza cruda entre 0.70
y 0.89.

## Por qué 0.70 y no otro valor

`MIN_SINGLE_VOTE_CONFIDENCE` (`api/detect.py`, ver el fix de esta misma
sesión "Piso de Confianza del ALPR Solo Protegía Lecturas de 1 Estrategia
Sin Considerar 2") ya es el piso que decide si una lectura llega a
**guardarse como archivo** en `/ftp/historico` — 0.70. Exigirle más a la
consolidación (0.90) que a la captura misma (0.70) no tiene un motivo
propio: cualquier lectura que ya pasó ese piso y quedó guardada como
evidencia es, por definición del propio sistema, lo bastante buena como
para competir por ser reconocida. 0.70 es el piso más bajo posible sin
inventar un nuevo criterio — alinea ambos umbrales.

## Evidencia

Mismo script de análisis que ADR-008 (no forma parte del pipeline, solo
diagnóstico), sobre `staging_detections` real del 2026-08-11 y el
2026-08-10, probando 0.90 (actual), 0.85, 0.80, 0.75 y 0.70:

- **Beneficio**: bajar a 0.70 agrupa correctamente **16 casos adicionales**
  el 2026-08-11 (`RP7080`/`RPTD80`, `WWVF21`/`WYF21`, `HDJD27`/`HDJD79`,
  `PRGW9`/`PRGW91`, entre otros) frente al piso actual de 0.90.
- **Riesgo — el más importante**: se comparó la **ganadora** de cada grupo
  ya existente a 0.90 contra la ganadora del mismo grupo (o su superconjunto)
  en cada nivel más bajo (0.85, 0.80, 0.75, 0.70). **Cero cambios de
  ganadora** en los 4 niveles — ninguna decisión ya correcta se invierte al
  admitir lecturas de menor confianza. Esto tiene sentido: una lectura de
  0.75 casi nunca alcanza a superar en votos a una patente ya corroborada
  por 2+ lecturas de alta confianza (el criterio de `_majority_plate` sigue
  siendo por cantidad de votos, no por confianza individual — ver ADR-005).
- Se buscó también el patrón de riesgo de ADR-008 (dos grupos ya bien
  establecidos por separado, 3+ lecturas cada uno, fusionándose en uno):
  **cero casos**, sobre 2026-08-11 y 2026-08-10.

## Decisión

`SightingConsolidationSettings.min_confidence` cambia su valor por defecto
de `0.90` a `0.70`. Sin cambios de código en `_cluster_staging_reads`,
`_majority_plate` ni `consolidate_fuzzy_sightings` — `min_confidence` ya
era un parámetro validado (`__post_init__` exige `0 < min_confidence < 1`)
desde ADR-005. Mismo criterio que ADR-007/ADR-008: cambio de
configuración documentado con su propio PR y ADR, no una edición silenciosa
de variable de entorno.

## Riesgo residual

El caso `VWYF21`/`WYF211` (ver conversación de esta sesión, mismo día)
mostró que un empate 1-voto-contra-1-voto se desempata por confianza
promedio, y en ese desempate puede ganar la lectura equivocada por una
diferencia de ruido — sin que esto rompa evidencia real (el ganador
"equivocado" nunca puede desplazar a una detección ya `MATCHED_ENTRY`/
`MATCHED_EXIT`, el código no toca esos estados). Bajar `min_confidence`
aumenta cuántas lecturas de un solo voto pueden entrar a un empate así, por
lo que este tipo de resultado "no dañino pero subóptimo" puede volverse
algo más frecuente. No se aborda en este ADR — sigue siendo un caso
distinto, de menor severidad (costo: no limpia una imagen, nunca daña una).

## Consecuencias

- Reduce aún más el ruido en `/ftp/historico`, sin flag nuevo ni paso de
  activación aparte — mismo criterio que ADR-007/ADR-008.
- Alinea el piso de la consolidación con el piso de captura del ALPR
  (`MIN_SINGLE_VOTE_CONFIDENCE=0.70`) — deja de existir una franja
  (0.70-0.89) donde una lectura es "lo bastante buena para guardarse" pero
  "no lo bastante buena para que se le compare contra su hermana".
- Reversión inmediata si aparece evidencia de un cambio de ganadora
  incorrecto: no hay dato irreversible en juego (ninguna imagen se borra,
  ver ADR-005/006).
