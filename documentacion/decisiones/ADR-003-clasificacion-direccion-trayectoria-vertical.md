# ADR-003 — Clasificar dirección exclusivamente por trayectoria vertical

**Estado:** `aceptada`  
**Fecha:** 2026-07-24  
**Creado por:** Codex, a solicitud del usuario  
**HUs relacionadas:** [HU-007](../historias-usuario/administrador/HU-007-clasificar-direccion-trayectoria-vertical.md), [HU-008](../historias-usuario/administrador/HU-008-configurar-parametros-clasificador-vertical.md), [HU-009](../historias-usuario/auditor/HU-009-observar-decisiones-clasificador-vertical.md)  
**Relación:** refina la señal geométrica de [ADR-001](./ADR-001-reactivar-direction-tracker-acotado.md); no amplía por sí sola el alcance operativo decidido allí.

## Contexto confirmado

- La cámara está instalada en altura.
- Los vehículos entran y salen por el mismo sector.
- La imagen entregada al pipeline corresponde a una zona truncada.
- Dentro de ella, la patente cambia verticalmente durante el movimiento.
- No se distinguen sentidos por carriles ni zonas diferentes.
- No debe introducirse división o cruce de zonas.

El código calcula `center_y` desde el bounding box de YOLOv9:

```text
center_y = ((bbox.y1 + bbox.y2) / 2) / processed_image_height
```

El repositorio solo confirma que `strategy_center_crop` recorta el 60 % central
como una de doce estrategias y redimensiona el resultado. No existe una etapa
global de recorte documentada en backend. Antes de integrar se verificará si el
truncado ocurre en cámara/configuración externa y se demostrará el sistema de
coordenadas efectivo con una fixture. Esto no cuestiona la instalación
confirmada; evita normalizar contra una altura equivocada.

## Decisión

La dirección se estimará exclusivamente desde:

```text
(t1, y1), (t2, y2), ..., (tn, yn)
```

Cada `yi` será el centro vertical dividido por la altura de la imagen
efectivamente enviada a YOLOv9 en esa inferencia. Se ajustará:

```text
y(t) = a*t + b
dirección = signo(dy/dt) = signo(a)
```

Solo se clasificará si conjuntamente:

1. hay entre 3 y 8 muestras en una ventana configurable;
2. `abs(y_final - y_inicial)` supera el desplazamiento mínimo;
3. `abs(a)` supera la pendiente mínima;
4. los deltas consecutivos alcanzan la consistencia mínima.

El signo configurado como entrada devuelve `APPROACHING`; el contrario,
`DEPARTING`; evidencia insuficiente o inconsistente devuelve `UNKNOWN`.

## Exclusiones explícitas

No se utilizarán:

- `center_x`;
- ancho, alto, área o tamaño del bounding box;
- crecimiento o reducción aparente;
- zonas superior, intermedia o inferior;
- límites como `0.35` o `0.65`;
- recorrido completo de la imagen;
- supuestos sobre otras cámaras.

Las estrategias que alteran geometría —recorte reescalado, deskew o upscale—
no aportarán coordenadas a una trayectoria sin transformación demostrada al
sistema común. El consenso de texto puede usar todas las estrategias; la
muestra geométrica vendrá de una estrategia que preserve las coordenadas.

## Asociación temporal

El historial será independiente por patente normalizada. La implementación
declarará cómo evita que correcciones OCR mezclen dos autos o fragmenten una
trayectoria. No se autoriza inventar tracking visual adicional: cualquier
matching difuso reutilizará contratos existentes y conservará trazabilidad.

Los tiempos usados por la regresión serán monotónicos. El timestamp persistido
seguirá usando `America/Santiago`.

## Alcance operativo

Este ADR no autoriza cobro, sanción, control de acceso, cierre autoritativo,
eliminación de revisión humana ni activación directa sin calibración,
observabilidad y rollback. `UNKNOWN` es un resultado normal: conserva el
avistamiento/evidencia para revisión y no abre ni cierra sesiones ni crea
`orphan_exits`.

## Alternativas consideradas

1. **Cruce de zonas:** descartado por el mismo sector y el recorte existente.
2. **Movimiento horizontal:** descartado para esta instalación.
3. **Tamaño del bbox:** descartado expresamente.
4. **Dos muestras:** descartado por sensibilidad a variaciones aisladas.
5. **Regresión + desplazamiento + consistencia:** elegida.

## Consecuencias

- `DirectionTracker` retirará X y tamaño de su contrato.
- Se usarán timestamps explícitos o reloj inyectable.
- Los umbrales se validarán con datos anonimizados o sintéticos.
- El signo de entrada será configuración explícita.
- Exactitud direccional y confianza OCR se medirán por separado.

## Pruebas obligatorias

- trayectorias creciente/decreciente y signo invertido;
- muestras, desplazamiento o pendiente insuficientes;
- deltas inconsistentes y timestamps irregulares;
- muestras cerca de bordes, expiración y más de ocho muestras;
- coordenadas fuera de `[0,1]`;
- estrategia sin geometría comparable;
- `UNKNOWN` sin efectos autoritativos.

## Referencias

- `api/detect.py::extract_best_plate`
- `api/detect.py::run_multi_strategy`
- `api/detect.py::strategy_center_crop`
- `api/direction_tracker.py::DirectionTracker`
- `api/ftp_handler.py::_handle_auto_detection`
- `api/staging.py`
- `tests/test_direction_tracker.py`
