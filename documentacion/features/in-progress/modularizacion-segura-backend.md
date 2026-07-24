# Feature — Modularización segura del backend

**Etapa Project 4:** `In progress`  
**HUs relacionadas:** [HU-006](../../historias-usuario/administrador/HU-006-modularizar-backend-sin-regresiones.md)  
**ADR:** [ADR-002](../../decisiones/ADR-002-arquitectura-modular-backend.md)  
**Issues:** [#24](https://github.com/anomvlito/centralparking-mvp/issues/24)

## Problema

`api/detect.py` concentra FastAPI, ALPR, schemas y endpoints; `api/database.py`
concentra persistencia de varios dominios. FTP y video importan directamente el
módulo de aplicación. Esto amplía el impacto de cambios y dificulta probar o
reemplazar una etapa aislada.

## Resultado esperado

Backend organizado por composición, routers, servicios, ALPR, schemas y
repositorios, con dependencias explícitas, caracterización y migración
incremental. Los consumidores observan los mismos contratos y efectos.

## Alcance y tandas

1. Línea base OpenAPI, consumidores y pruebas.
2. Composición: `main`, configuración, seguridad y lifespan.
3. ALPR: engine, preprocesamiento, validación, consenso y modelos.
4. Routers y schemas por dominio.
5. Servicios sin lógica HTTP.
6. Repositorios por dominio y transacciones preservadas.
7. Retiro de fachadas, regresión, smoke y rollback.

Cada tanda será verificable y desplegable; no mezclará estructura y algoritmo.

## No-alcance

- Cambiar formatos, estrategias, umbrales o modelos ALPR.
- Reactivar dirección automática.
- Crear endpoints nuevos por conveniencia.
- Modificar frontend, credenciales o despliegue.
- Reescribir todo en un único PR.

## Contratos

- Métodos, paths, parámetros, payloads, respuestas y errores actuales.
- `CarsResponse = Record<string, ParkedCar>` conserva `plate`, `entryTime`,
  `isEvent` y `eventFee?: number | null`.
- `EntryOpen`, `ExitOrphan` y `SessionClosed` siguen siendo proyecciones
  distintas de `ParkedCar`; extraer módulos no puede sustituir ni mezclar
  estos DTO.
- Detección, FTP, video, staging, vehículos, historial, revisión, estadísticas,
  Excel y auth sin regresión.
- Watchdog y entrypoint del VPS compatibles.
- Timestamps y trazabilidad de evidencia preservados.
- La dirección usa exclusivamente `record(plate, center_y, timestamp)`;
  `UNKNOWN` no produce cambios en sesiones ni salidas huérfanas.

## Riesgos

- Alterar orden de inicialización o registrar routers dos veces.
- Inicializar ALPR múltiples veces.
- Cambiar excepciones al mover handlers.
- Romper imports de Uvicorn, FTP o video.
- Mezclar cambios locales ajenos.

## Criterio de cierre

HU-006 implementada por tandas, OpenAPI equivalente, regresión completa, smoke
backend/watchdog, rollback documentado y handlers sin reglas de negocio.
