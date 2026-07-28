# Feature — Matching revisable de detecciones

**Etapa Project 4:** `In progress`  
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
