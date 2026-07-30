# HU-012 — Excluir vehículos operativos y descartar estadías duplicadas

**Actor:** `administrador`
**Estado:** `en-progreso`
**Feature relacionada:** [Exclusiones y evidencia navegable](../../features/in-progress/exclusiones-evidencia-navegable.md)
**Issue:** [#48](https://github.com/anomvlito/centralparking-mvp/issues/48)
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In progress` / `In Progress`

## Historia

Como **administrador**, quiero **excluir vehículos configurados y lecturas
similares, descartar estadías de cero minutos y ampliar cualquier foto**, para
**evitar ruido operativo sin perder evidencia ni trazabilidad**.

## Criterios de aceptación

- [x] Existe una lista durable de patentes excluidas con distancia máxima
  configurable; la patente real no aparece en código, docs, fixtures ni logs.
- [x] Una detección exacta o a distancia Levenshtein 1 de una exclusión queda
  `DISMISSED`, conserva evidencia y no genera propuesta ni estadía.
- [x] Un backfill idempotente descarta pendientes históricos alcanzados.
- [x] Una pareja con duración calculada de 0 minutos no crea una estadía útil:
  queda `VOID`, sus detecciones `DISMISSED` y se audita como duplicado.
- [x] Las propuestas exactas o fuzzy inferiores a 60 segundos se descartan
  automáticamente antes de mostrarse y no reaparecen al recargar.
- [ ] Una pareja mostrada como `0 min` o `1 min` se considera captura repetida:
  la primera detección permanece `UNMATCHED` como entrada pendiente y sólo la
  segunda queda `DISMISSED`; ambas evidencias se conservan.
- [ ] Si la segunda captura ya era la entrada de una estadía válida, esa
  estadía adopta la primera captura como entrada, conserva su salida y descarta
  la repetición; no queda una entrada pendiente adicional.
- [x] Un backfill reversible anula sesiones de 0 minutos ya existentes sin
  borrar fotos o filas.
- [x] Todas las imágenes del Dashboard se pueden pulsar para abrir un visor
  ampliado y cerrar con botón, fondo o `Escape`.
- [x] La barra superior de conciliación muestra las fotos seleccionadas de
  entrada y salida antes de confirmar.
- [x] Las evidencias se sirven con caché privada de navegador por una hora,
  sin convertirlas en contenido público ni perder el control de acceso.
- [x] Exclusión, backfills y escrituras requieren administrador.

## No-alcance

- Borrar físicamente imágenes, detecciones, auditoría o sesiones.
- Excluir automáticamente otras patentes no configuradas.
- Alterar conciliaciones fuzzy distintas de la exclusión.

## Código relacionado

- Backend: `api/database.py`, schemas/services/routers de reconciliación y tests.
- Frontend: `src/features/dashboard/Dashboard.tsx` y tests.
- Operación: inserción controlada de la exclusión en PostgreSQL y deploy normal.

## Contratos y riesgos

Se agregan endpoints administrativos de exclusión sin romper DTO existentes.
La similitud puede capturar una patente real cercana; por eso la configuración
es explícita, auditable y reversible. `VOID`/`DISMISSED` preservan evidencia.

## Pruebas de regresión

- Exacta, distancia 1 y distancia 2.
- Backfill idempotente.
- Duración mostrada 0/1 versus 2 minutos.
- Evidencia intacta y sesión `VOID`.
- Auth 401/403.
- Visor para estadía, detección y revisión; teclado y mobile.
- Backend, frontend, Historial, FTP y Excel sin regresión.

## Evidencia

- Backend PR [#49](https://github.com/anomvlito/centralparking-mvp/pull/49),
  merge `9674f1a`, deploy VPS correcto y health `/docs` HTTP 200.
- Frontend PR [#11](https://github.com/anomvlito/adyac-camaras-frontend/pull/11),
  merge `61f85af` y deploy Vercel Production correcto.
- Backend: 16 pruebas y `compileall`; frontend: 14 pruebas, lint sin errores y
  build de producción.
- Configuración privada aplicada sin publicar la patente: 90 detecciones
  descartadas y 39 sesiones excluidas anuladas; 1 sesión de duración inferior
  a un minuto anulada por el backfill reversible.
- Regresión corregida en backend PR
  [#51](https://github.com/anomvlito/centralparking-mvp/pull/51) y corrección
  de integridad referencial en PR
  [#52](https://github.com/anomvlito/centralparking-mvp/pull/52).
- Antes del arreglo se observaron 22 propuestas de `0 min`; después del deploy
  y backfill quedaron 0, incluyendo el listado interno sin filtro. Permanecen
  14 propuestas de duración válida.
- Verificación final: 18 pruebas unitarias/contrato, 2 pruebas PostgreSQL,
  `compileall`, servicio activo y `/docs` HTTP 200.
