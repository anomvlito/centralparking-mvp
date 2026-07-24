# HU-008 — Configurar y validar parámetros del clasificador vertical

**Actor:** `administrador`  
**Estado:** `en-revision`
**Feature relacionada:** [Clasificación de entrada y salida por trayectoria vertical](../../features/in-review/clasificacion-vertical-entrada-salida.md)
**Issue:** [#26](https://github.com/anomvlito/centralparking-mvp/issues/26)  
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In review` / `In Progress`
**Creado por:** Codex, a solicitud del usuario  
**ADR relacionada:** [ADR-003 — Clasificar dirección exclusivamente por trayectoria vertical](../../decisiones/ADR-003-clasificacion-direccion-trayectoria-vertical.md)  
**HU base:** [HU-007 — Clasificar entrada y salida por trayectoria vertical](./HU-007-clasificar-direccion-trayectoria-vertical.md)

## Historia

Como **administrador**, quiero **que los parámetros del clasificador vertical
sean explícitos, validados, trazables y recuperables**, para **calibrar la
dirección de la cámara real sin editar lógica ni dejar el backend en una
configuración inválida**.

## Contexto y problema

`DirectionTracker` usa hoy variables de entorno para ventana, muestras,
desplazamiento, consistencia, eje, signo y tamaño. HU-007 elimina X y tamaño e
incorpora pendiente temporal. La nueva configuración necesita límites
coherentes y una fuente de verdad documentada.

Esta HU no presupone que los parámetros deban editarse desde una pantalla ni
inventa un endpoint. Primero consolida un objeto de configuración validado,
carga al inicio, evidencia de valores efectivos y rollback. Una UI o API de
mutación requiere decisión adicional de permisos, persistencia y operación.

## Parámetros mínimos

La implementación debe modelar, como mínimo:

```text
DIRECTION_ENABLED
DIRECTION_OBSERVATION_ONLY
DIRECTION_WINDOW_SEC
DIRECTION_MIN_SAMPLES
DIRECTION_MAX_HISTORY
DIRECTION_MIN_DISPLACEMENT
DIRECTION_MIN_SLOPE
DIRECTION_MIN_CONSISTENCY
DIRECTION_ENTRY_SIGN
```

Los nombres definitivos deben reconciliarse con las variables ya desplegadas;
no se renombrarán silenciosamente. Las variables retiradas de X/tamaño deberán
detectarse y documentarse durante la transición.

## Criterios de aceptación

### Fuente y validación

- [ ] Existe una clase/schema único de configuración direccional.
- [ ] Todos los valores se cargan una vez al inicio o mediante un mecanismo de
  recarga explícitamente diseñado; no se leen de `os.environ` en cada cálculo.
- [ ] La fuente de cada valor efectivo está documentada sin imprimir secretos.
- [ ] El backend falla de forma clara antes de aceptar tráfico si una
  configuración habilitada es inválida.
- [ ] Con el clasificador deshabilitado, una configuración direccional inválida
  no puede activar efectos; se reporta de forma operable.

### Invariantes

- [ ] `3 <= MIN_SAMPLES <= MAX_HISTORY <= 8`.
- [ ] `WINDOW_SEC > 0`.
- [ ] `MIN_DISPLACEMENT` pertenece a `(0,1]`.
- [ ] `MIN_SLOPE > 0` y sus unidades normalizadas/segundo están documentadas.
- [ ] `MIN_CONSISTENCY` pertenece a `(0.5,1]`.
- [ ] `ENTRY_SIGN` solo admite `positive` o `negative`.
- [ ] `OBSERVATION_ONLY=false` no habilita efectos si `ENABLED=false`.
- [ ] Combinaciones incoherentes producen error accionable, no fallback
  silencioso.

### Compatibilidad y transición

- [ ] Se inventarían primero las variables reales del servicio VPS sin exponer
  valores sensibles.
- [ ] `DIRECTION_WINDOW_SEC`, `DIRECTION_MIN_SAMPLES`,
  `DIRECTION_MAX_HISTORY`, `DIRECTION_MIN_DISPLACEMENT`,
  `DIRECTION_MIN_CONSISTENCY` y `DIRECTION_ENTRY_SIGN` mantienen significado o
  cuentan con migración documentada.
- [ ] `DIRECTION_AXIS` y parámetros de tamaño quedan obsoletos de manera
  explícita; no influyen en el algoritmo vertical.
- [ ] La presencia de variables obsoletas produce advertencia no sensible
  durante una ventana de transición y luego tiene criterio de retiro.

### Operación segura

- [ ] El valor efectivo puede inspeccionarse por un mecanismo autenticado o
  diagnóstico operativo autorizado, sin revelar secretos ni patentes.
- [ ] La configuración reporta versión/hash para relacionarla con decisiones
  observadas.
- [ ] Existe una configuración conocida que desactiva o deja en
  `observation_only` el clasificador.
- [ ] El procedimiento de cambio incluye estado previo, validación, reinicio
  solo cuando corresponda, health, smoke y rollback.
- [ ] Ningún cambio de parámetro borra historiales persistidos o evidencia.

### Calibración

- [ ] Se define un conjunto de secuencias sintéticas/anonimizadas etiquetadas
  como entrada, salida o incierta.
- [ ] Los umbrales candidatos se evalúan sobre el mismo conjunto reproducible.
- [ ] Se registran falsos `APPROACHING`, falsos `DEPARTING` y `UNKNOWN`.
- [ ] No se elige una configuración solo por maximizar decisiones; se preserva
  la capacidad de abstención.
- [ ] La configuración candidata no pasa a efectos productivos hasta cumplir
  el criterio acordado en HU-009.

## No-alcance

- Diseñar una pantalla de administración.
- Crear un endpoint de escritura sin decisión explícita de seguridad.
- Guardar configuración en PostgreSQL de forma incidental.
- Ajustar automáticamente parámetros con datos productivos.
- Cambiar YOLO/OCR o estrategias de imagen.
- Usar X, tamaño o zonas.
- Habilitar cobro, sanción o control de acceso.
- Exponer variables de entorno completas o secretos.

## Código relacionado

- Backend:
  - `api/direction_tracker.py`: constantes actuales a inyectar.
  - `api/detect.py`: configuración/lifespan actual.
  - estructura `api/core/config.py` propuesta por HU-006.
  - servicio direccional propuesto por HU-007.
  - tests unitarios y de startup.
- Frontend: no requiere cambios.
- Operación:
  - configuración efectiva de `centralparking.service`.
  - `start-backend.sh` y procedimiento documentado de deploy/rollback.

## Contratos que deben preservarse

- El backend sigue iniciando con la configuración actual compatible mientras
  el clasificador esté deshabilitado.
- `APPROACHING`, `DEPARTING`, `UNKNOWN` no cambian.
- Los parámetros solo afectan dirección, no texto/confianza OCR ni staging.
- Ningún endpoint existente cambia su shape.
- Seguridad/autorización aplica a cualquier futura lectura de configuración.
- Los defaults de propuesta no se afirman como calibrados para producción.

## Impacto sobre funcionalidades existentes

Centralizar configuración cambia el startup del backend y puede impedir
arranque ante valores inválidos. Eso es deseable cuando la función está
habilitada, pero requiere pruebas de compatibilidad y rollback. Las variables
existentes pueden estar en archivos o unidades del servicio fuera del repo; se
inspeccionan sin mostrar valores sensibles antes de migrar.

## Riesgos y datos

- Umbral demasiado bajo produce falsas decisiones.
- Umbral demasiado alto produce exceso de `UNKNOWN`.
- Signo invertido intercambia entrada/salida.
- Unidad de pendiente mal documentada cambia con frame rate.
- Defaults de desarrollo llegan a producción sin calibración.
- Endpoint diagnóstico expone configuración o información sensible.
- Reinicio operativo incidental interrumpe detección.

## Pruebas de regresión

- Startup con defaults compatibles y clasificador deshabilitado.
- Cada valor fuera de rango produce error específico.
- Relaciones min/max inválidas se rechazan.
- Signo positivo/negativo cambia solo el mapeo final.
- Intervalos distintos producen pendiente en unidades consistentes.
- Variables obsoletas no afectan el resultado.
- `observation_only` calcula pero no produce efectos.
- `enabled=false` conserva flujo actual.
- Configuración no modifica `/api/detect`, FTP, staging, historial o auth.
- Hash/version cambia cuando cambia un parámetro relevante.
- Rollback recupera configuración anterior y health correcto.

## Propuesta técnica

1. Crear `DirectionSettings` inmutable y validado.
2. Inyectarlo a `DirectionTracker`; eliminar lecturas internas dispersas de
   variables de entorno.
3. Mantener adapter de compatibilidad que mapee variables existentes.
4. Introducir `MIN_SLOPE` con unidad `center_y normalizado/segundo`.
5. Separar `ENABLED` de `OBSERVATION_ONLY`.
6. Calcular una huella de configuración excluyendo secretos.
7. Documentar tabla de variables:

   | Parámetro | Unidad | Rango | Efecto | Rollback |
   | --- | --- | --- | --- | --- |
   | Window | segundos | `>0` | vigencia de muestras | valor previo |
   | Samples | conteo | `3..8` | evidencia mínima | valor previo |
   | Displacement | `center_y` | `(0,1]` | movimiento mínimo | valor previo |
   | Slope | `center_y/s` | `>0` | velocidad mínima | valor previo |
   | Consistency | proporción | `(0.5,1]` | estabilidad | valor previo |
   | Entry sign | enum | `positive/negative` | orientación | valor previo |

8. No habilitar mutación HTTP en esta HU.

## Dependencias

- Depende de HU-007 para conocer el contrato final.
- Se beneficia de `core/config` de HU-006.
- Es puerta previa a activación productiva junto con HU-009.

## Evidencia de implementación

- Commit: `e12c07b`.
- PR: [#28](https://github.com/anomvlito/centralparking-mvp/pull/28).
- Inventario y rollback:
  [configuración del clasificador](../../guias/configuracion-clasificador-vertical.md).
- Dataset: secuencias sintéticas reproducibles en
  `tests/test_direction_tracker.py`.
- Valores efectivos productivos: pendientes de observación/calibración; no se
  afirma que los defaults estén aprobados para efectos.
- Verificaciones: validación de rangos, hash, variables obsoletas,
  `enabled=false` y `observation_only`.
