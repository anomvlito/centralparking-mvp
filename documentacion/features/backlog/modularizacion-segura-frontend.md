# Feature — Modularización segura del frontend

**Etapa Project 4:** `Backlog`
**HUs relacionadas:** [HU-002 — Modularizar el frontend preservando su comportamiento](../../historias-usuario/administrador/HU-002-modularizacion-segura-frontend.md)
**Issues:** pendiente

## Problema

El frontend productivo concentra autenticación, acceso API, polling, evidencia,
operación y tres vistas en un único `src/app/page.tsx` de aproximadamente 972
líneas. Esto eleva el costo de prueba y el riesgo de regresiones al mantenerlo.

## Resultado esperado

Una arquitectura modular por responsabilidades y dominios, protegida por
pruebas de caracterización y comparaciones contra una línea base recuperable,
sin cambios funcionales ni visuales no aprobados.

## Alcance

- Línea base y estrategia de recuperación.
- Pruebas de caracterización previas a la extracción.
- Tipos, cliente API, componentes y hooks separados por responsabilidad.
- Shell de aplicación pequeño y composición explícita.
- Verificación incremental de equivalencia funcional.

## No-alcance

- Nuevas funcionalidades o rediseño visual.
- Cambios de backend, API, datos, ALPR o reglas operativas.
- Migración de framework, despliegue o reemplazo incidental de `.next`.

## Contratos

- Baseline: `adyac-camaras-frontend@fd38cc11aa03d40d69442b6cb6344696f6dae2ce`.
- Frontend productivo: `adyac-camaras-frontend/src/`.
- Se preservan autenticación, endpoints, polling, trazabilidad de evidencia,
  revisión humana, historial y conciliación.

## Riesgos

- Cambiar comportamiento al extraer efectos y estados.
- Perder trazabilidad entre avistamiento, sesión, imagen y corrección.
- Mezclar cambios locales ajenos en una refactorización extensa.
- Declarar equivalencia basándose sólo en compilación.

## Criterio de cierre

La HU relacionada cumple su matriz de regresión, cada etapa posee evidencia
reproducible y el frontend modular conserva el comportamiento observado en la
línea base, con rollback comprobable y sin cambios de contratos.
