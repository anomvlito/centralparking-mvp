# HU-007 — Clasificar entrada y salida por trayectoria vertical

**Actor:** `administrador`  
**Estado:** `en-progreso`  
**Feature relacionada:** [Clasificación de entrada y salida por trayectoria vertical](../../features/in-progress/clasificacion-vertical-entrada-salida.md)  
**Issue:** [#25](https://github.com/anomvlito/centralparking-mvp/issues/25)  
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In progress` / `In Progress`  
**Creado por:** Codex, a solicitud del usuario  
**ADRs relacionadas:** [ADR-001](../../decisiones/ADR-001-reactivar-direction-tracker-acotado.md), [ADR-003](../../decisiones/ADR-003-clasificacion-direccion-trayectoria-vertical.md)  
**HUs relacionadas:** [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md), [HU-006](./HU-006-modularizar-backend-sin-regresiones.md)

## Historia

Como **administrador**, quiero **que Central Parking estime si un vehículo
entra o sale usando exclusivamente la trayectoria vertical temporal de su
patente**, para **apoyar la conciliación automática con una señal adaptada a
la cámara real, manteniendo los casos inciertos disponibles para revisión**.

## Contexto y condiciones confirmadas

- La cámara está instalada en altura.
- Los vehículos entran y salen por el mismo sector.
- La imagen se trunca previamente a una zona de detección.
- Dentro de esa zona la patente cambia verticalmente durante el movimiento.
- No existen zonas de entrada/salida distintas dentro de la imagen.
- No se usará movimiento horizontal ni tamaño del bounding box.

`DirectionTracker` existe pero está desconectado. Su implementación actual
permite X/Y y tamaño. Esta HU reemplaza esa señal por:

```text
(t1, y1), (t2, y2), ..., (tn, yn)
y(t) = a*t + b
dirección = signo(a) = signo(dy/dt)
```

El backend calcula hoy `center_y` contra `processed.shape`, pero no documenta
un recorte global: `center_crop` es una estrategia opcional que recorta y
reescala. Antes de integrar, se debe confirmar dónde ocurre el truncado real y
qué altura corresponde al bounding box. No se asumirá una ruta inexistente.

## Criterios de aceptación

### Coordenadas

- [ ] Se documenta con evidencia si el recorte ocurre en cámara, configuración
  externa o backend.
- [ ] Una fixture conocida demuestra el sistema de coordenadas retornado por
  YOLOv9.
- [ ] Cada muestra calcula:

  ```text
  center_y = ((bbox.y1 + bbox.y2) / 2) / detection_image_height
  ```

- [ ] `detection_image_height` es la altura de la imagen efectivamente enviada
  a YOLO en esa inferencia.
- [ ] `center_y` fuera de `[0,1]`, bbox ausente o geometría no comparable no
  genera una muestra válida.
- [ ] El texto puede usar consenso de múltiples estrategias, pero la geometría
  proviene de una estrategia que preserve el sistema documentado.

### Historial

- [ ] Existe un historial temporal independiente por patente normalizada.
- [ ] El mínimo configurable nunca es inferior a 3.
- [ ] El máximo configurable está entre el mínimo y 8.
- [ ] Las muestras fuera de la ventana se purgan antes de clasificar.
- [ ] Los cálculos usan tiempo monotónico y toleran intervalos irregulares.
- [ ] Se define cómo interactúan las correcciones OCR con el historial sin
  mezclar vehículos ni perder trazabilidad.

### Cálculo

- [ ] Se calcula desplazamiento `y_final - y_inicial`.
- [ ] Se calcula la pendiente `a` mediante regresión lineal de `y` respecto de
  timestamps reales, no índices igualmente espaciados.
- [ ] Se calcula la proporción de deltas consecutivos no nulos cuyo signo
  coincide con el desplazamiento general.
- [ ] Solo se clasifica si se cumplen simultáneamente mínimos de muestras,
  desplazamiento, pendiente y consistencia.
- [ ] Pendiente con signo configurado como entrada devuelve `APPROACHING`.
- [ ] Pendiente contraria devuelve `DEPARTING`.
- [ ] Evidencia insuficiente, contradictoria o inválida devuelve `UNKNOWN`.
- [ ] La respuesta permite conocer el resultado sin alterar texto o confianza
  OCR.

### Exclusiones demostrables

- [ ] El algoritmo no lee `center_x`.
- [ ] El algoritmo no recibe ni calcula tamaño/ancho/alto/área del bbox.
- [ ] No existen zonas ni límites `0.35`/`0.65`.
- [ ] No se exige atravesar todo el recorte.
- [ ] Tests fallan si accidentalmente X o tamaño modifican el resultado.

### Integración segura

- [ ] La implementación se integra a través de la frontera ALPR/servicio de
  HU-006 o una fachada compatible, sin reintroducir imports circulares.
- [ ] Inicialmente puede operar en modo observación sin efectos de sesión.
- [ ] Su uso en conciliación se limita al caso decidido por ADR-001.
- [ ] `UNKNOWN` conserva el avistamiento y su evidencia para revisión/manual;
  no abre ni cierra sesiones, no crea `orphan_exits` y no provoca cobro,
  sanción ni control de acceso.
- [ ] Existe una forma documentada de desactivar la clasificación y volver al
  flujo de avistamientos/manual sin perder evidencia.

## No-alcance

- Zonas superior/intermedia/inferior o cruce de zonas.
- Movimiento X, tamaño, profundidad aparente o sensores adicionales.
- Soportar otra cámara o geometría no descrita.
- Modificar reconocimiento OCR, validación o consenso de texto.
- Decidir dirección con una sola imagen.
- Cambiar rutas públicas o payloads existentes.
- Implementar UI de parámetros; corresponde a HU-008 si se autoriza.
- Implementar observabilidad completa; corresponde a HU-009.
- Activar cobro o control de acceso.

## Código relacionado

- Backend:
  - `api/detect.py::extract_best_plate`: origen actual de bbox/`center_y`.
  - `api/detect.py::run_multi_strategy`: selección actual de geometría.
  - `api/detect.py::strategy_center_crop`: recorte opcional a auditar.
  - `api/direction_tracker.py`: regresión vertical a implementar.
  - `api/ftp_handler.py::_handle_auto_detection`: integración hoy desconectada.
  - `api/video_processor.py`: secuencias de frames.
  - `api/staging.py`: ventana de evidencia, distinta de la ventana direccional.
  - `tests/test_direction_tracker.py`: ampliar/reemplazar casos.
- Frontend: no requiere cambios para calcular dirección; la revisión visual
  pertenece a HU-005.
- Operación: cámara/configuración del recorte y servicio backend; no se
  modifican en esta HU sin procedimiento separado.

## Contratos que deben preservarse

- `APPROACHING`, `DEPARTING`, `UNKNOWN`.
- Texto, estrategia y confianza ALPR.
- `POST /api/detect`, `/api/ftp/image`, `/api/ftp/video`.
- Staging y mejor evidencia.
- `/api/entry`, `/api/exit/{plate}`, `/api/history`, `/api/cars`.
- Relación entre imagen, avistamiento, sesión y corrección.
- Revisión humana y rollback al flujo pasivo/manual.

La firma interna esperada podrá evolucionar desde:

```python
record(plate, center_x, center_y, size=None)
```

hacia un contrato vertical explícito:

```python
record(plate, center_y, timestamp=None)
```

La transición deberá adaptar todos los consumidores en la misma tanda o
proveer una fachada temporal, sin aceptar silenciosamente X/tamaño.

## Impacto sobre funcionalidades existentes

Modifica una señal que estuvo conectada al flujo FTP y fue apagada por falsos
resultados. Aunque el algoritmo pueda probarse aislado, su integración afecta
ingesta, conciliación y sesiones. No debe reactivarse sobre el 100 % de las
detecciones ni desplegarse sin observabilidad y rollback.

## Riesgos y datos

- Altura incorrecta al normalizar por una imagen distinta.
- Mezcla de coordenadas de estrategias con geometrías diferentes.
- Historial fragmentado por variaciones OCR.
- Historial mezclado por matching difuso excesivo.
- Umbrales sobreajustados a pocas secuencias.
- Logs con patentes reales.
- Confundir confianza OCR con confianza direccional.

Se usarán secuencias sintéticas o anonimizadas. No se borrará evidencia.

## Pruebas de regresión

### Pruebas unitarias obligatorias

- Creciente regular → sentido positivo.
- Decreciente regular → sentido negativo.
- `DIRECTION_ENTRY_SIGN` invertido.
- 0, 1 y 2 muestras → `UNKNOWN`.
- Desplazamiento insuficiente → `UNKNOWN`.
- Pendiente insuficiente → `UNKNOWN`.
- Desplazamiento grande pero inconsistente → `UNKNOWN`.
- Timestamps irregulares con tendencia válida.
- Timestamps duplicados/no ordenados tratados explícitamente.
- Inicio o fin cerca de `0` o `1`.
- Coordenadas negativas o mayores a 1.
- Expiración de ventana.
- Máximo de ocho muestras.
- X y tamaño distintos con mismo `y(t)` → mismo resultado.
- Geometría de `center_crop`/deskew excluida si no se transforma.
- Reutilización de patente tras expirar la ventana.

### Pruebas de integración

- Imagen FTP repetida genera muestras sin duplicar sesiones.
- Video conserva timestamps/secuencia suficientes para el tracker.
- Texto detectado igual antes/después.
- No detección y decode fallido no crean historial direccional.
- Staging conserva mejor imagen independientemente de dirección.
- `UNKNOWN` mantiene revisión/manual.
- Match exacto/difuso de HU-004 conserva prioridad según ADR-001.
- Auth, historial, Excel y frontend permanecen sin regresión.

## Propuesta técnica

1. Definir un resultado tipado con dirección, cantidad de muestras,
   desplazamiento, pendiente y consistencia; los detalles sensibles no se
   exponen en logs generales.
2. Al registrar una muestra, purgar por ventana y limitar a ocho.
3. Para `n >= min_samples`, calcular regresión:

   ```text
   a = sum((ti - mean_t)*(yi - mean_y)) /
       sum((ti - mean_t)^2)
   ```

4. Calcular desplazamiento y consistencia solo con deltas no nulos.
5. Aplicar todas las puertas antes de mapear el signo.
6. Mantener `clear(plate)` y expiración explícita.
7. Ejecutar primero en pruebas/modo observación.
8. Integrar al caso acotado de ADR-001 solo tras HU-008 y HU-009.

## Dependencias

- Recomendada después de la frontera ALPR de HU-006.
- Refina el componente direccional de HU-004; no sustituye matching ni cola de
  revisión.
- HU-008 y HU-009 son puertas antes de activación productiva.

## Evidencia de implementación

- Commit/PR: pendiente.
- Fixture de coordenadas: pendiente.
- Calibración: pendiente.
- Verificaciones: pendientes.
