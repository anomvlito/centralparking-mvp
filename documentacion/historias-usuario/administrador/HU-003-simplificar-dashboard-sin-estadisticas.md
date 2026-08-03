# HU-003 — Simplificar el Dashboard eliminando estadísticas y estado

**Actor:** `administrador`
**Estado:** `implementada`
**Feature relacionada:** [Simplificación del Dashboard operativo](../../features/done/simplificacion-dashboard-administrador.md)
**Issue:** [#21](https://github.com/anomvlito/centralparking-mvp/issues/21) — cerrado
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `Done`

## Historia

Como **administrador**, quiero **que el Dashboard deje de mostrar los
recuadros de estadísticas y el bloque de estado**, para **simplificar la
vista operativa y validar, en una prueba controlada, el flujo completo de
creación e implementación de una HU**.

## Contexto y problema

`Dashboard.tsx` muestra actualmente una columna izquierda con 4 tarjetas de
estadísticas (`StatCard`: Entradas hoy, Salidas hoy, En parking, Recaudado) y
un bloque "Estado" (Cámara/Staging/Actualización), junto al feed en vivo a la
derecha. Esta HU es una prueba deliberada y acotada del flujo end-to-end:
crear la HU, implementarla localmente, verificar, y sólo después evaluar
publicarla. No se autoriza PR, merge ni deploy en esta etapa de creación.

## Criterios de aceptación

- [ ] El Dashboard ya no muestra los 4 `StatCard` (Entradas hoy, Salidas hoy,
  En parking, Recaudado).
- [ ] El Dashboard ya no muestra el bloque "Estado" (Cámara/Staging/
  Actualización).
- [ ] El feed en vivo (columna derecha) conserva su comportamiento: orden,
  polling cada 15 segundos, refresco tras acciones, `PhotoThumb` y `FeedRow`.
- [ ] El layout se adapta sin dejar espacio vacío ni columnas rotas en
  desktop y mobile.
- [ ] Las pestañas Historial y Reconciliación no cambian.
- [ ] Se documenta explícitamente si `stats` deja de pasarse a `Dashboard`
  desde `App`, sin retirar la llamada a `/api/stats` salvo autorización
  posterior separada.

## No-alcance

- Modificar el endpoint `/api/stats` o su contrato.
- Modificar Historial o Reconciliación.
- Retirar `stats` o la llamada a `/api/stats` de `App` (page.tsx).
- Publicar (commit/push/PR/merge/deploy) como parte de la creación de esta HU.
- Cambiar el componente compartido `StatCard` en sí; sólo se deja de invocar
  desde `Dashboard`.

## Código relacionado

- Backend: no requiere cambios. `/api/stats` sigue existiendo y siendo
  consumido por `App` (`page.tsx`); su contrato se preserva.
- Frontend: `adyac-camaras-frontend/src/features/dashboard/Dashboard.tsx`
  (elimina el bloque "Left: stats"); eventualmente
  `adyac-camaras-frontend/src/app/page.tsx` si se documenta un cambio en el
  uso de `stats`.
- Operación: no requiere cambios.

## Contratos que deben preservarse

- Endpoint `/api/stats` y su respuesta (se preserva en backend y en `App`
  aunque deje de renderizarse en `Dashboard`).
- Polling del feed cada 15 segundos (`DASHBOARD_REFRESH_MS`).
- Trazabilidad visual imagen–avistamiento–sesión en `FeedRow`/`PhotoThumb`.
- Interfaz pública de `Dashboard` hacia `App`, salvo cambio documentado.

## Impacto sobre funcionalidades existentes

Cambio visual/estructural acotado a una vista. No afecta lógica de negocio,
ALPR, cobro ni backend. El riesgo principal es de layout (el grid de 2
columnas queda con una sola) y de dejar props o llamadas sin uso si `stats`
deja de graficarse.

## Riesgos y datos

- Layout: `lg:grid-cols-[300px_1fr] lg:gap-6` fue diseñado para 2 columnas;
  al quitar la izquierda hay que decidir si el feed pasa a ancho completo u
  otro layout.
- Código potencialmente muerto: si `stats` deja de graficarse, evaluar (sin
  ejecutar en esta HU) si `App` debe seguir pidiendo `/api/stats`.
- Sin implicancias de datos sensibles ni ALPR: es remoción de UI en una vista
  ya autenticada, sin tocar datos de patentes ni evidencia.

## Pruebas de regresión

- Login válido/inválido sin cambios.
- Dashboard: feed en vivo mantiene orden, polling de 15s y refresco tras
  registrar/corregir patente.
- Verificación visual en tamaños desktop y mobile, sin huecos ni overflow.
- Historial y Reconciliación sin cambios.
- `npm run lint`, `npm exec tsc -- --noEmit`, suite de tests existente,
  `npm run build` en copia aislada si hay una `.next` activa sirviendo local.

## Propuesta técnica

1. En `Dashboard.tsx`, eliminar el `<div>` "Left: stats" completo (4
   `StatCard` + bloque "Estado").
2. Ajustar el contenedor externo: quitar `lg:grid-cols-[300px_1fr]
   lg:gap-6` y dejar el feed como bloque único, evaluando ancho completo.
3. Documentar si `stats` sigue siendo necesario como prop de `Dashboard`;
   no retirarlo de `App` en esta HU salvo autorización explícita adicional
   (evitar ampliar alcance).
4. Probar localmente en servidor de desarrollo, comparar visualmente
   antes/después y correr la regresión listada arriba.
5. Sólo tras validación local exitosa, y con autorización explícita
   adicional del usuario, continuar con commit/push — fuera del alcance de
   esta etapa de creación de HU.

## Evidencia de implementación

- Rama/worktree frontend: `agent/hu-003-simplificar-dashboard` en
  `.worktrees/frontend-hu003`, basada en `origin/main` (commit base
  `cf98218`).
- Commit:
  [`221900f`](https://github.com/anomvlito/adyac-camaras-frontend/commit/221900fac2f73a961a719fa4523e94b76f7ac4c7)
  — "Simplify Dashboard by removing stat cards and status block".
- Push: rama publicada en
  `https://github.com/anomvlito/adyac-camaras-frontend/tree/agent/hu-003-simplificar-dashboard`.
- PR: [#4](https://github.com/anomvlito/adyac-camaras-frontend/pull/4) —
  mergeado a `main` con merge commit
  [`5b97d50`](https://github.com/anomvlito/adyac-camaras-frontend/commit/5b97d503b57813772a7745c819943c182cd2c8d7).
- Deploy Vercel (producción, destino documentado del frontend): exitoso —
  `https://centralparking-epzaa5e94-fas-projects-aa4f98ac.vercel.app`.
- Smoke check post-deploy: `HTTP 200`, página de login carga correctamente.
- Hallazgo aparte, no bloqueante para esta HU: el workflow de GitHub Actions
  `Deploy to VPS` (`.github/workflows/deploy.yml`) falló en este mismo commit
  por falta de credenciales SSH (`can't connect without a private SSH key or
  password`) y además usa un path desactualizado
  (`/opt/services/adyac-camaras-frontend`, sin `centralparking/`). Es un
  problema preexistente de configuración, no introducido por HU-003 ni por su
  contenido; el usuario decidió cerrar esta HU igualmente porque el deploy
  real del frontend (Vercel) está verificado.
- `npm run lint`: correcto, 0 errores, 3 advertencias (`stats` sin uso en
  `page.tsx`, esperado; 2 preexistentes de `no-img-element`).
- `npm exec tsc -- --noEmit`: correcto.
- `npm test`: 5 archivos, 11 pruebas correctas (se actualizó
  `App.integration.test.tsx` para reflejar que ya no se muestra `$1.200`).
- `npm run build`: correcto en worktree aislado.
- `npm run test:e2e`: 4/4 escenarios correctos (desktop 1440×900 y mobile
  390×844); se actualizó `e2e/app.spec.ts` para verificar explícitamente
  que las estadísticas y el bloque "Estado" no son visibles.
