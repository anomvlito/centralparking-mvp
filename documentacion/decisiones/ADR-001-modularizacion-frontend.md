# ADR-001 — Modularización incremental del frontend

**Estado:** aceptada
**Fecha:** 2026-07-21
**HU relacionada:** [HU-002](../historias-usuario/administrador/HU-002-modularizacion-segura-frontend.md)

## Contexto

El frontend productivo concentraba cerca de 972 líneas en `src/app/page.tsx`,
mezclando autenticación, acceso HTTP, polling, dashboard, historial, evidencia
y conciliación. La refactorización debe preservar comportamiento y permitir
rollback por etapas.

## Decisión

- Organizar el código por dominio bajo `src/features/` y componentes operativos
  compartidos bajo `src/components/parking/`.
- Mantener contratos, persistencia y acceso HTTP en `src/lib/`.
- Conservar App Router y la ruta única actual; no introducir un gestor global
  de estado.
- Usar Vitest para pruebas de caracterización de funciones, contratos y render
  inicial.
- Mantener los efectos cerca del dominio que los consume y conservar el polling
  en 15 segundos.
- Implementar desde un worktree limpio basado en `origin/main`, con `fd38cc1`
  como respaldo verificable.

## Alternativas consideradas

- Mantener el archivo monolítico: menor cambio inmediato, pero conserva alto
  acoplamiento y baja capacidad de prueba.
- Migrar a otro framework o añadir gestión global de estado: amplía
  innecesariamente el alcance y el riesgo.
- Reescribir cada componente desde cero: dificulta demostrar equivalencia
  funcional.

## Consecuencias

- `page.tsx` queda dedicado a composición y coordinación.
- Se añade Vitest como dependencia de desarrollo y una suite de caracterización.
- Los imports internos pasan a usar el alias `@/` existente.
- La extracción mecánica conserva textos, clases, URLs y payloads; futuras
  mejoras pueden revisarse por dominio.
- El archivo compartido del feed mantiene juntas las operaciones de evidencia,
  revisión y registro para evitar separar prematuramente reglas acopladas.

## Verificación

- Comparación exacta de las 15 llamadas HTTP antes/después.
- Lint, TypeScript, Vitest y build Next.js.
- Comparación semántica del HTML de acceso contra el baseline.
- Pruebas con datos exclusivamente sintéticos.
