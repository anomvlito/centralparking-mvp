# HU-011 — Validar patentes y proponer conciliaciones revisables

**Actor:** `administrador`
**Estado:** `implementada`
**Feature relacionada:** [Matching revisable de detecciones](../../features/done/matching-revisable-detecciones.md)
**Issue:** [#43](https://github.com/anomvlito/centralparking-mvp/issues/43)
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — cierre verificado después de producción

## Historia

Como **administrador**, quiero **que sólo las patentes normalizadas de seis
caracteres entren a conciliación y recibir propuestas de entrada/salida
revisables**, para **formar estadías confiables sin perder fotos ni convertir
el OCR probabilístico en una decisión automática**.

## Contexto y problema

La cola actual contiene lecturas de cinco y siete caracteres, mientras
`reconcile_detection_events()` sólo crea estadías por selección manual. El
fuzzy match existente corrige sesiones abiertas recientes, pero no empareja
detecciones. Las fotos históricas permanecen en `/ftp/historico` y
`/ftp/revisar`; estas últimas no pueden entrar hoy a conciliación porque no
tienen una patente resuelta ni `DetectionEvent`.

## Criterios de aceptación

- [x] La normalización elimina símbolos y exige exactamente seis caracteres
  alfanuméricos.
- [x] Una lectura inválida queda `INVALID_FORMAT`, conserva imagen, timestamp,
  OCR original y auditoría, y no aparece como `UNMATCHED`.
- [x] Un backfill idempotente reclasifica pendientes históricos inválidos sin
  borrar archivos ni filas.
- [x] La patente resuelta de una conciliación también exige seis caracteres.
- [x] `GET /api/stay-proposals?date=YYYY-MM-DD` devuelve propuestas exactas y
  difusas, nunca crea sesiones ni consume detecciones.
- [x] Las propuestas respetan salida posterior, máximo de 24 horas, consumo
  único y prioridad de match exacto; dirección/confianza sólo ponderan.
- [x] El administrador puede aceptar una propuesta mediante el flujo manual
  existente, editar la patente o ignorarla.
- [x] Una imagen de `/ftp/revisar` puede promoverse con patente válida a
  `DetectionEvent` sin mover ni borrar el archivo.
- [x] Lecturas, propuestas, promoción y conciliación requieren autenticación;
  las escrituras requieren rol administrador.
- [x] La UI separa propuestas, pendientes sin propuesta y formatos inválidos,
  conservando fecha operativa y revisión humana.

## No-alcance

- Crear estadías automáticamente sin confirmación.
- Borrar, renombrar o mover evidencia histórica.
- Usar una propuesta para cobro, sanción o acceso.
- Reprocesar OCR masivamente sobre las 18 mil imágenes de revisión.

## Código relacionado

- Backend: `api/database.py`, `api/routers/reconciliation.py`,
  `api/services/reconciliation.py`, `api/schemas/reconciliation.py`,
  `api/ftp_handler.py` y tests.
- Frontend: `src/features/dashboard/Dashboard.tsx`, `src/lib/stays.ts` y tests.
- Operación: `centralparking.service`; migración aditiva/idempotente en startup.

## Contratos que deben preservarse

- DTO `DetectionEvent` y `ParkingStay`; se agrega `INVALID_FORMAT`.
- `POST /api/stays/reconcile` sigue siendo la única escritura que forma una
  estadía.
- `/api/history`, `/api/cars`, FTP, Sightings y Excel permanecen compatibles.

## Impacto sobre funcionalidades existentes

Se reduce la cola operativa al formato válido, se agregan propuestas de lectura
y recuperación manual de evidencia. No se elimina historial.

## Riesgos y datos

- Dos vehículos con patentes similares pueden generar una propuesta difusa
  incorrecta: siempre requiere confirmación.
- Varias pasadas del mismo vehículo pueden producir candidatos ambiguos: el
  algoritmo es greedy y no consume datos.
- El backfill cambia estado, no contenido; debe reportar conteos agregados y ser
  reversible cambiando `INVALID_FORMAT` a `UNMATCHED`.

## Pruebas de regresión

- Normalización 5/6/7 caracteres y símbolos.
- Backfill idempotente y evidencia intacta.
- Propuesta exacta, difusa, fuera de ventana y orden inválido.
- Conciliación de patente inválida rechazada.
- Promoción segura: path traversal, archivo inexistente, patente inválida y
  caso correcto con fixture sintético.
- Auth 401/403, OpenAPI, historial, staging y FTP sin regresión.
- Frontend: fecha, propuesta seleccionable, edición, vacío/error, lint,
  TypeScript, tests y build aislado.

## Propuesta técnica

1. Agregar `INVALID_FORMAT` y clasificar en `log_to_db()`.
2. Reclasificar sólo filas `UNMATCHED` de longitud distinta de seis.
3. Construir propuestas greedy exactas y luego difusas (Levenshtein 1) dentro
   de 24 horas, puntuadas por confianza y dirección.
4. Exponer propuestas read-only y reutilizar `POST /api/stays/reconcile`.
5. Promover una imagen de revisión creando una fila auditable que referencia
   su ruta original.

## Evidencia de implementación

- Backend/documentación: commits `d2d1e06` y `8fd0317`,
  [PR #44](https://github.com/anomvlito/centralparking-mvp/pull/44),
  merge `4d80d427fd21c9f8fe7736f38ddf707e0480c3c7`.
- Frontend: commit `37e34a4`,
  [PR #9](https://github.com/anomvlito/adyac-camaras-frontend/pull/9),
  merge `ab4c18fd5d630c2fef609c3eec3572b7f4fb7b28`.
- Verificación local: 14 pruebas backend, `compileall`, 14 pruebas frontend,
  lint sin errores, TypeScript y build Next.js correctos.
- Deploy backend:
  [run 30393877329](https://github.com/anomvlito/centralparking-mvp/actions/runs/30393877329)
  correcto; servicios activos, `/docs` 200 y rutas protegidas 401 sin token.
- Backfill productivo: 1.115 filas respaldadas y reclasificadas
  `INVALID_FORMAT`; 877 mantienen imagen; 5.396 continúan `UNMATCHED`.
- Propuestas agregadas para 2026-07-28: 177 (138 `EXACT`, 39 `FUZZY`), sin
  crear ni consumir sesiones.
- Vercel Production `success` para el merge frontend; smoke HTTP 200 en
  `https://centralparking-8o8d1fsb0-fas-projects-aa4f98ac.vercel.app`.
