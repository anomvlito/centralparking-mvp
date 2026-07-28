# Feature — Matching revisable de detecciones

**Etapa Project 4:** `Done`  
**HU:** [HU-011](../../historias-usuario/administrador/HU-011-validar-patentes-proponer-conciliacion.md)

## Resultado esperado

La cola acepta sólo patentes normalizadas de seis caracteres, conserva
evidencia inválida fuera de la operación y ofrece pares entrada/salida exactos
o difusos para confirmación humana. Las fotos de revisión pueden incorporarse
manualmente sin borrar ni mover archivos.

## Guardrails

- Ninguna propuesta crea cobro, acceso o estadía por sí sola.
- Evidencia y OCR original son inmutables.
- Backfill idempotente, agregado y reversible.
- Escrituras sólo para administrador.

## Criterio de cierre

Backend y frontend desplegados, migración verificada por conteos agregados,
propuestas y promoción manual probadas, sin regresión de historial/FTP/Excel.

## Evidencia

- Backend [PR #44](https://github.com/anomvlito/centralparking-mvp/pull/44),
  deploy [30393877329](https://github.com/anomvlito/centralparking-mvp/actions/runs/30393877329).
- Frontend [PR #9](https://github.com/anomvlito/adyac-camaras-frontend/pull/9),
  Vercel Production y smoke HTTP 200.
- Backfill respaldado: 1.115 inválidas; evidencia preservada.
- Motor productivo: 138 propuestas exactas y 39 difusas en la fecha de smoke.
