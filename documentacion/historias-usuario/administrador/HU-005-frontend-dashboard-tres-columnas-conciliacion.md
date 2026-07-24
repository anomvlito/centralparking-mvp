# HU-005 — Consultar duración de estadías y revisar detecciones sin conciliar

**Actor:** `administrador`
**Estado:** `en-progreso`
**Feature relacionada:** [Estadías conciliadas desde detecciones](../../features/in-progress/conciliacion-automatica-entradas-salidas.md)
**Issue:** [#23](https://github.com/anomvlito/centralparking-mvp/issues/23)
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In progress` / `In Progress`
**HU backend:** [HU-004](./HU-004-backend-conciliacion-automatica-entradas-salidas.md)

## Historia

Como **administrador**, quiero **ver cuánto duró cada estadía y revisar aparte
las detecciones que todavía no tienen pareja**, para **obtener permanencias
confiables sin exigir OCR perfecto ni convertir “autos actualmente dentro” en
la vista principal**.

## Contexto y problema

La UI productiva mantiene `ParkedCar`, consulta `/api/cars` y tiene un
dashboard de tres columnas conectado a mocks `EntryOpen`, `ExitOrphan` y
`SessionClosed`. Eso no representa la necesidad prioritaria: una estadía
completa y su duración, derivada de detecciones particulares auditables.

## Criterios de aceptación

- [ ] La vista principal se llama `Estadías` y consume `GET /api/stays`.
- [ ] Por defecto muestra estadías `COMPLETED`, ordenadas por salida reciente.
- [ ] Cada fila muestra patente resuelta, entrada, salida, duración y tipo de
  match; imágenes son detalle opcional.
- [ ] La duración proviene del backend y se presenta en minutos/horas sin
  recalcular la regla de negocio.
- [ ] Hay filtros por fecha y patente que no mezclan estado actual con
  historial.
- [ ] Una sección secundaria `Por conciliar` consume detecciones
  `UNMATCHED`; muestra timestamp, lectura OCR, confianza, dirección e imagen.
- [ ] El administrador puede elegir una detección de entrada y una de salida,
  indicar la patente resuelta y ejecutar conciliación manual.
- [ ] La UI permite diferencias de OCR y advierte, pero no exige coincidencia
  literal ni confianza 100 %.
- [ ] La salida anterior a la entrada queda bloqueada también visualmente y el
  backend sigue siendo la autoridad.
- [ ] Una detección puede descartarse con confirmación sin desaparecer de la
  evidencia durable.
- [ ] Tras conciliar o descartar se refrescan estadías y pendientes.
- [ ] Estados de carga, vacío, error, 401 y 403 son explícitos.
- [ ] El layout funciona en móvil y escritorio.

## No-alcance

- Mostrar autos actualmente estacionados como KPI o vista principal.
- Eliminar `/api/cars` del backend.
- Calcular cobros desde el navegador.
- Ocultar evidencia incierta o forzar un match.
- Activar efectos del clasificador vertical.

## Código relacionado

- Frontend productivo:
  - `src/app/page.tsx`;
  - `src/lib/parking.ts`;
  - reemplazo de `src/lib/dashboardMock.ts` por contratos y cliente reales.
- Backend: endpoints definidos por HU-004.
- Operación: Vercel; no afecta el frontend histórico de `centralparking-mvp`.

## Contratos que deben preservarse

- `DetectionEvent` y `ParkingStay` definidos por HU-004.
- Login, renovación de sesión, 401/403 y proxy actual.
- Historial, Sightings y Excel siguen accesibles.
- `ParkedCar` puede permanecer como compatibilidad interna, con
  `eventFee?: number | null`, pero no conduce esta vista.

## Impacto sobre funcionalidades existentes

Se reemplaza el dashboard mock de tres columnas y se deja de consultar
`/api/cars` para decidir el contenido principal. El historial existente no se
elimina en esta entrega.

## Riesgos y datos

- Confundir OCR con patente resuelta.
- Presentar `UNKNOWN` como error.
- Conciliar dos detecciones equivocadas.
- Exponer rutas internas o datos reales en fixtures.

La UI debe mostrar incertidumbre y mantener revisión humana.

## Pruebas de regresión

- Estadía completa y duración.
- Vacío, error y reconexión.
- Detecciones con patente distinta pueden conciliarse manualmente.
- Orden temporal inválido se bloquea y el error backend se presenta.
- Dismiss requiere confirmación y refresca.
- Login, Historial, Sightings y Excel sin regresión.
- `npm run lint`, TypeScript y build aislado.
- Verificación responsive y preview Vercel.

## Evidencia de implementación

- Commit/PR: pendiente.
- Preview/deploy y smoke: pendientes.
