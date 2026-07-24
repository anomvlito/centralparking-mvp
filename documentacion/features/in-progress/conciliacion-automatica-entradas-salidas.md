# Feature — Estadías conciliadas desde detecciones particulares

**Etapa Project 4:** `In progress`
**HUs:** [HU-004](../../historias-usuario/administrador/HU-004-backend-conciliacion-automatica-entradas-salidas.md), [HU-005](../../historias-usuario/administrador/HU-005-frontend-dashboard-tres-columnas-conciliacion.md)
**Issues:** [#22](https://github.com/anomvlito/centralparking-mvp/issues/22), [#23](https://github.com/anomvlito/centralparking-mvp/issues/23)

## Problema

El producto modela el estado actual mediante `ParkedCar` y el dashboard de
conciliación usa tres DTO conectados a mocks. La necesidad prioritaria es
conocer cuánto duró una estadía, conservando cada lectura de cámara aunque su
OCR o dirección sean inciertos.

## Resultado

- `DetectionEvent`: evidencia particular e inmutable.
- `ParkingStay`: interpretación conciliada que referencia entrada y salida.
- Vista principal de estadías completas y duración.
- Cola secundaria de detecciones sin pareja con match/dismiss manual.
- Matching permisivo sin exigir OCR perfecto y sin efectos autoritativos.

## Contratos y guardrails

- Las correcciones agregan interpretación; no sobrescriben la evidencia.
- Una detección se consume una sola vez mediante transacción.
- La duración se calcula en backend sólo con entrada y salida coherentes.
- `UNKNOWN` y baja confianza son estados válidos.
- `/api/cars`, `/api/history`, `/api/entry` y `/api/exit/{plate}` permanecen
  compatibles durante la transición.
- Ninguna detección incierta produce cobro, sanción o acceso.

## No-alcance

- Mostrar ocupación actual como objetivo principal.
- Borrar evidencia o retirar contratos REST existentes.
- Activar decisiones automáticas del clasificador.

## Criterio de cierre

Backend y frontend desplegados; detecciones, conciliación manual, estadías,
duración, auth y errores verificados; regresión existente correcta y evidencia
de producción/preview registrada.
