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
- Fecha operativa común para pendientes y estadías, con solapamiento correcto
  de estadías nocturnas.
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

La reapertura de 2026-07-28 exige además fecha inicial de Chile, ausencia de
mezcla histórica implícita, selección manual de rol en toda detección y
estadías nocturnas visibles en cada día que solapen.

## Evidencia

- Backend: [PR #34](https://github.com/anomvlito/centralparking-mvp/pull/34),
  deploy [30069920707](https://github.com/anomvlito/centralparking-mvp/actions/runs/30069920707).
- Frontend: [PR #5](https://github.com/anomvlito/adyac-camaras-frontend/pull/5),
  Vercel Production sobre `08b56d97bc6d758870f2cbc4ad0d723768f47f12`.
