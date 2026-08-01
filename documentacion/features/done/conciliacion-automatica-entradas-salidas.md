# Feature — Estadías conciliadas desde detecciones particulares

**Etapa Project 4:** `Done`
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

La reapertura de 2026-07-31 exige además que clasificar manualmente una
detección `UNKNOWN` como entrada/salida persista su `direction` real
(`PATCH /api/detections/{id}` con `action: "set_direction"`) y mueva la
tarjeta a la columna de pendientes correspondiente, para que la conciliación
automática existente la tome en su próximo ciclo. Esto invierte, sólo para el
caso `UNKNOWN`, el guardrail "ninguna detección incierta produce... acceso"
en su lectura estricta de "la dirección es ayuda visual y nunca autoridad":
la corrección manual sí queda como autoridad sobre `direction`, aunque sigue
sin producir cobro, sanción ni acceso por sí sola.

## Evidencia

- Dirección manual persistida al clasificar UNKNOWN: backend
  [PR #59](https://github.com/anomvlito/centralparking-mvp/pull/59), deploy
  [30709705482](https://github.com/anomvlito/centralparking-mvp/actions/runs/30709705482);
  frontend
  [PR #13](https://github.com/anomvlito/adyac-camaras-frontend/pull/13),
  Vercel Production y smoke HTTP 200.
- Fecha operativa y conciliación accesible: backend
  [PR #41](https://github.com/anomvlito/centralparking-mvp/pull/41),
  deploy
  [30392654410](https://github.com/anomvlito/centralparking-mvp/actions/runs/30392654410);
  frontend
  [PR #8](https://github.com/anomvlito/adyac-camaras-frontend/pull/8),
  Vercel Production y smoke HTTP 200.
- Backend: [PR #34](https://github.com/anomvlito/centralparking-mvp/pull/34),
  deploy [30069920707](https://github.com/anomvlito/centralparking-mvp/actions/runs/30069920707).
- Frontend: [PR #5](https://github.com/anomvlito/adyac-camaras-frontend/pull/5),
  Vercel Production sobre `08b56d97bc6d758870f2cbc4ad0d723768f47f12`.
