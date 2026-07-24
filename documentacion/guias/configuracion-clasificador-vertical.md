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
4. Conservar `audit_log`; el rollback no elimina evidencia previa.

No modificar secretos, borrar eventos ni editar datos runtime como parte del
rollback.
