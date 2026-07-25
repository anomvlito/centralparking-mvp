# Configuración y rollback del clasificador vertical

El clasificador usa únicamente la trayectoria temporal de `center_y`
normalizado contra la imagen efectivamente inferida. No usa X, tamaño del
bounding box ni zonas.

## Fuente de coordenadas

La cámara entrega al backend la imagen del sector configurado. El backend no
aplica un recorte global adicional. `center_crop` es solo una de las
estrategias ALPR y no se usa como fuente geométrica. La geometría direccional
se toma de la estrategia ganadora que preserve el sistema de la imagen
inferida (`raw`, `clahe`, `highlight_recovery`, `sharpen`,
`bilateral+clahe` o `grayscale_eq`) y se normaliza contra su altura.

## Variables

| Variable | Default seguro | Unidad/rango | Efecto |
| --- | --- | --- | --- |
| `DIRECTION_ENABLED` | `false` | booleano | Habilita cálculo y auditoría. |
| `DIRECTION_OBSERVATION_ONLY` | `true` | booleano | Impide efectos sobre sesiones. |
| `DIRECTION_WINDOW_SEC` | `15` | segundos, `> 0` | Vigencia de muestras. |
| `DIRECTION_MIN_SAMPLES` | `3` | entero `3..8` | Evidencia mínima. |
| `DIRECTION_MAX_HISTORY` | `8` | entero `MIN_SAMPLES..8` | Memoria acotada. |
| `DIRECTION_MIN_DISPLACEMENT` | `0.08` | `center_y`, `(0,1]` | Movimiento total mínimo. |
| `DIRECTION_MIN_SLOPE` | `0.01` | `center_y/segundo`, `> 0` | Pendiente mínima. |
| `DIRECTION_MIN_CONSISTENCY` | `0.67` | proporción `(0.5,1]` | Deltas con el signo dominante. |
| `DIRECTION_ENTRY_SIGN` | `positive` | `positive`/`negative` | Orientación física de entrada. |

`DIRECTION_AXIS` y las variables `DIRECTION_SIZE_*` son obsoletas y no
participan en el resultado.

## Modos

- Deshabilitado: `DIRECTION_ENABLED=false`. Conserva exactamente el flujo
  previo y no genera evaluaciones.
- Sombra: `DIRECTION_ENABLED=true` y
  `DIRECTION_OBSERVATION_ONLY=true`. Calcula y audita con `effect=none`.
- Activo: reservado para la integración de conciliación de HU-004. El servicio
  direccional no abre ni cierra sesiones por sí mismo.

La configuración efectiva y su hash no secreto se consultan autenticadamente
en `GET /api/audit/direction/config`. Las métricas agregadas, sin patente como
dimensión, se consultan en `GET /api/audit/direction/metrics`.

## Activación en sombra

1. Registrar estado y hash actuales mediante el endpoint autenticado.
2. Preparar el cambio manteniendo `DIRECTION_OBSERVATION_ONLY=true`.
3. Validar configuración con la suite unitaria antes del reinicio.
4. Reiniciar únicamente durante el deploy autorizado.
5. Verificar health, ingesta, auditoría y que `effect` permanezca `none`.
6. Evaluar secuencias sintéticas/anonimizadas y revisión humana antes de
   considerar cualquier efecto productivo.

## Rollback

1. Restaurar `DIRECTION_ENABLED=false`.
2. Reiniciar `centralparking.service` por el procedimiento de deploy vigente.
3. Verificar `/docs`, ingesta FTP y ausencia de nuevas evaluaciones.

## Propuesta de calibración con datos reales (2026-07-24)

Contexto: tras HU-010 (wiring de `direction` hacia `detection_log`), se
juntaron datos reales de producción en modo sombra desde que el servicio
arrancó (~19:34 UTC) hasta el momento de este análisis (~23:00 UTC),
suficientes para una primera propuesta de calibración — algo que HU-008
dejó explícitamente pendiente ("no se afirma que los defaults estén
aprobados para producción").

**No se aplicó ningún cambio todavía.** Esto es una propuesta para revisión,
según pide HU-008 ("los umbrales candidatos se evalúan sobre el mismo
conjunto reproducible... no se elige una configuración solo por maximizar
decisiones").

### Dataset

228 evaluaciones con `sample_count >= 3` (evidencia suficiente para
intentar clasificar). De esas, 126 tienen `consistency = 1.0` — es decir,
movimiento verticalmente monótono sin ningún delta en contra del signo
dominante. Ese subconjunto es la base más confiable para calibrar: filtra
ruido de dirección por diseño (`insufficient_consistency` nunca aparece
ahí), así que cualquier `UNKNOWN` restante se debe únicamente a
`DIRECTION_MIN_DISPLACEMENT` o `DIRECTION_MIN_SLOPE`.

```
Dentro de consistency = 1.0 (n=126):
  clasificado (APPROACHING/DEPARTING):  45
  insufficient_displacement:            51
  insufficient_slope:                   30
```

### Hallazgo 1 — `DIRECTION_MIN_SLOPE` (0.01) parece demasiado alto

Los 30 casos rechazados por `insufficient_slope` **ya superaron** el umbral
de desplazamiento (0.08) y tienen consistencia perfecta — son, con alta
confianza, movimiento vehicular real, solo que ocurrió más lento (más
tiempo) que lo que el umbral de pendiente permite:

```
insufficient_slope (n=30): displacement 0.083–0.145, slope 0.00579–0.00995
                                                              ↑ máximo, apenas
                                                                bajo el umbral 0.01
```

**Propuesta:** bajar `DIRECTION_MIN_SLOPE` de `0.01` a `0.006` — cubre la
mayoría de estos 30 casos sin llegar al mínimo observado exacto (evita
ajustar el umbral literalmente al dato de hoy). No se toca
`DIRECTION_MIN_DISPLACEMENT` en este cambio, así que solo afecta casos que
ya tienen desplazamiento real confirmado.

### Hallazgo 2 — `DIRECTION_MIN_DISPLACEMENT` (0.08): sin evidencia suficiente para tocarlo

Los 51 casos rechazados por `insufficient_displacement` (consistency=1.0)
se distribuyen de forma pareja entre 0.0003 y 0.077 — sin un quiebre claro
que separe "ruido/OCR jitter" de "movimiento real pero pequeño":

```
bucket     rango              casos
0.0003–0.0096   probable ruido/estacionario   14
0.013–0.077     sin patrón claro               37
```

**No se propone bajar este umbral todavía.** A diferencia de la pendiente,
acá no hay una señal limpia — bajarlo a ciegas arriesga convertir OCR
jitter en falsos `APPROACHING`/`DEPARTING`, justo el tipo de error que
causó el incidente de 2026-07-17 (ADR-001). Antes de tocarlo, se
recomienda revisar manualmente una muestra de estos casos contra su imagen
real (`GET /api/monitor/file/...`, ya vinculada por patente/timestamp) para
confirmar si son movimiento genuino o ruido, en vez de inferirlo solo de
los números.

### Recomendación

1. Aplicar solo el cambio de `DIRECTION_MIN_SLOPE` (0.01 → 0.006) —
   evidencia limpia, riesgo bajo, no toca `MIN_DISPLACEMENT` ni
   `MIN_CONSISTENCY`.
2. Mantener `DIRECTION_OBSERVATION_ONLY=true` — este cambio sigue sin
   abrir/cerrar sesiones, solo cambia qué proporción de evaluaciones deja
   de ser `UNKNOWN`.
3. Dejar `DIRECTION_MIN_DISPLACEMENT` sin tocar hasta hacer una revisión
   manual de evidencia real (paso separado, no incluido acá).
4. Medir de nuevo `GET /api/audit/direction/metrics` tras el cambio,
   comparando contra esta línea base (126 casos de alta confianza, 45
   clasificados hoy) para confirmar el efecto real, no solo el esperado.

### Resultado (aplicado 2026-07-24, mismo día)

- Aplicado exactamente como en la recomendación: `Environment=DIRECTION_MIN_SLOPE=0.006`
  agregado al drop-in `20-deploy-worktree.conf` de `centralparking.service`,
  `systemctl daemon-reload` + `restart`. `DIRECTION_OBSERVATION_ONLY=true`
  sin cambios. Valor confirmado leyendo `/proc/<pid>/environ` del proceso
  real, no solo la unidad declarada.
- Backup del drop-in anterior en `/tmp/20-deploy-worktree.conf.before-slope-change`
  (rollback: restaurar ese archivo, `daemon-reload`, `restart`).
- Verificado con tráfico real minutos después: `JTXY84` evaluó
  `APPROACHING` (displacement 0.16, slope 0.014, consistencia 1.0) y se
  promovió correctamente a `detection_log.direction=APPROACHING`. También
  `TLVX70` y `RXTX88` llegaron a `APPROACHING` en algún momento de su
  secuencia (aunque `TLVX70` y `RXTX88` volvieron a `UNKNOWN` al llegar más
  muestras dentro de la ventana — ver nota de comportamiento en la
  evidencia de HU-010, no es un efecto de este cambio de umbral).
- `DIRECTION_MIN_DISPLACEMENT` sigue sin tocar, como se recomendó.
