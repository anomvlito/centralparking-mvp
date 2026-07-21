# HU-002 — Modularizar el frontend preservando su comportamiento

**Actor:** `administrador`
**Estado:** `implementada`
**Feature relacionada:** [Modularización segura del frontend](../../features/done/modularizacion-segura-frontend.md)
**Issue:** [#19](https://github.com/anomvlito/centralparking-mvp/issues/19)
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `Done`

## Historia

Como **administrador**, quiero **que el frontend se organice en módulos sin
alterar sus flujos actuales**, para **reducir el riesgo de mantenimiento y
conservar la continuidad operativa de Central Parking**.

## Contexto y problema

El frontend productivo concentra en `src/app/page.tsx` aproximadamente 972
líneas, 16 componentes o funciones, 20 estados React, 6 efectos y 17 llamadas
HTTP. El archivo mezcla autenticación, almacenamiento local, cliente API,
polling, dashboard, historial, evidencia, revisión, registro manual y
conciliación Excel.

Aunque existen límites conceptuales entre componentes, mantener todas esas
responsabilidades en un solo módulo aumenta el riesgo de regresiones y hace
difícil probar cada flujo de manera aislada. La modularización debe ser una
refactorización de comportamiento equivalente, no un rediseño funcional.

## Respaldo y línea base

- Repositorio: `anomvlito/adyac-camaras-frontend`.
- Commit base remoto y recuperable:
  [`fd38cc1`](https://github.com/anomvlito/adyac-camaras-frontend/commit/fd38cc11aa03d40d69442b6cb6344696f6dae2ce).
- Archivo base: `src/app/page.tsx`.
- SHA-256 del archivo en ese commit:
  `527d75ccdf4bc3842f4600f3830102a0b2f47f5189bec5e7153d8306ac0553eb`.
- La implementación debe partir de una rama limpia basada en ese commit o en
  un descendiente verificado de `origin/main`; los cambios locales ajenos del
  worktree actual no forman parte del alcance.
- Si una regresión no puede resolverse dentro de la etapa en curso, se debe
  volver al último commit verde de la rama, conservando el commit base como
  referencia de comparación. No se desplegará ni reemplazará producción como
  parte incidental de la refactorización.

## Criterios de aceptación

- [x] Antes de extraer componentes se registra una línea base reproducible de
  lint, TypeScript, build aislado y flujos críticos.
- [x] Se incorporan pruebas de caracterización para autenticación, expiración
  401, mezcla de sesiones y avistamientos, filtros históricos y estados de
  conciliación.
- [x] `src/app/page.tsx` queda limitado a composición, navegación y
  coordinación de vistas; tipos, acceso HTTP, hooks y componentes de dominio
  viven en módulos con responsabilidades explícitas.
- [x] La ruta de acceso, los textos, controles y diseño observable permanecen
  equivalentes a la línea base salvo diferencias aprobadas y documentadas.
- [x] El login válido e inválido, persistencia JWT, cierre de sesión y
  recuperación ante sesión expirada conservan su comportamiento.
- [x] El dashboard conserva estadísticas, feed combinado, orden temporal,
  polling cada 15 segundos y actualización manual posterior a acciones.
- [x] Se preserva la distinción entre sesiones reales y avistamientos sin
  sesión, incluida la revisión humana y el registro manual de entrada/salida.
- [x] El historial conserva fecha, filtros, navegación, imágenes relacionadas,
  edición de patente y estados de revisión.
- [x] La conciliación conserva carga de Excel, fecha, comparación y categorías
  `camera_only`, `matched` y `excel_only`.
- [x] No cambian URLs, métodos, query strings, payloads, respuestas esperadas ni
  tratamiento 401/403 de la API.
- [x] Lint, TypeScript, pruebas automatizadas, build aislado y validación en
  navegador con datos sintéticos están correctos en tamaños móvil y
  escritorio.
- [x] La rama y el worktree están aislados y son recuperables; el cambio quedó
  publicado en un commit acotado y puede revertirse desde el merge de la HU.

## No-alcance

- Rediseñar la interfaz, cambiar colores, textos o navegación.
- Crear nuevas capacidades de estacionamiento, ALPR o conciliación.
- Modificar endpoints, modelos, base de datos, permisos o backend.
- Cambiar reglas de cobro o convertir detecciones inciertas en acciones
  automáticas.
- Reescribir la aplicación en otro framework o incorporar gestión global de
  estado sin una decisión arquitectónica separada.
- Desplegar, reiniciar servicios, borrar evidencia o publicar datos reales.

## Código relacionado

- Backend: no requiere cambios; sus contratos se usan como referencia de
  regresión, especialmente autenticación, historial, avistamientos, vehículos,
  entrada/salida y conciliación.
- Frontend: `../../../../adyac-camaras-frontend/src/app/page.tsx`,
  `../../../../adyac-camaras-frontend/src/lib/parking.ts` y
  `../../../../adyac-camaras-frontend/src/proxy.ts`.
- Operación: frontend desplegado en Vercel; no requiere cambios operativos para
  la refactorización.

## Contratos que deben preservarse

- `NEXT_PUBLIC_API_URL` y el fallback actual del backend.
- JWT en `localStorage` bajo `cp_auth` y evento `cp-auth-expired`.
- `POST /auth/login` y tratamiento global de respuestas 401.
- Endpoints de estadísticas, historial, avistamientos, vehículos,
  entrada/salida, corrección de patente, revisión y conciliación usados por el
  frontend actual.
- Polling del dashboard cada 15 segundos.
- Trazabilidad visual entre imagen, avistamiento, sesión y corrección manual.
- Separación entre frontend Vercel y backend del VPS.

## Impacto sobre funcionalidades existentes

La intención es impacto funcional cero. El cambio reduce acoplamiento interno,
permite pruebas focalizadas y facilita modificaciones futuras. El principal
riesgo es alterar accidentalmente efectos, dependencias, orden de solicitudes,
estados de carga o refrescos al mover código entre módulos.

## Riesgos y datos

- Pérdida de actualización automática por dependencias incorrectas de hooks.
- Duplicación de solicitudes o condiciones de carrera durante el polling.
- Ruptura de la recuperación 401 o de la persistencia de sesión.
- Confusión entre avistamientos probabilísticos y sesiones confirmadas.
- Asociación incorrecta de imágenes al extraer componentes.
- Inclusión accidental de cambios locales ajenos en la rama de trabajo.
- Las pruebas deben usar credenciales, patentes, imágenes y archivos Excel
  sintéticos; no se copiarán datos reales como fixtures.

## Pruebas de regresión

- Comparar el inventario de controles, textos y clases principales contra el
  commit base.
- Login sintético inválido, login válido en entorno autorizado, logout y 401
  por sesión expirada.
- Dashboard: estadísticas, feed combinado, orden, polling y refresco posterior
  a corrección o registro manual.
- Avistamiento sin sesión: registrar entrada y salida; validar que la revisión
  humana continúe siendo obligatoria.
- Sesión real: ampliar evidencia, corregir patente, marcar patente correcta y
  descartar duplicado.
- Historial: día actual, día anterior, filtros de entrada/salida y estado sin
  resultados.
- Conciliación con Excel sintético válido, inválido, duplicado y sin match.
- Errores 401, 403, 4xx/5xx y desconexión sin perder silenciosamente el estado.
- Ejecutar `npm run lint`, `npm exec tsc -- --noEmit`, la suite automatizada y
  `npm run build` en una copia aislada si existe una `.next` activa.
- Validar en navegador tamaños móvil y escritorio antes de declarar
  equivalencia funcional.

## Propuesta técnica

1. Crear primero pruebas de caracterización y utilidades de fixtures
   sintéticos.
2. Extraer tipos, configuración y cliente autenticado a `src/lib/`.
3. Extraer componentes compartidos de evidencia y operación a
   `src/components/parking/`.
4. Separar autenticación, dashboard, historial y conciliación bajo
   `src/features/`, manteniendo inicialmente las mismas props y efectos.
5. Extraer hooks sólo después de tener pruebas sobre solicitudes, polling y
   actualización de estado.
6. Dejar `src/app/page.tsx` como shell cliente sin cambiar las rutas visibles.
7. Implementar en commits pequeños; verificar y comparar contra la línea base
   después de cada etapa.

La elección definitiva de runner de pruebas y las fronteras públicas entre
módulos deben registrarse antes de implementación. Si introducen una decisión
durable o nuevas dependencias, corresponde documentarlas mediante ADR.

Decisión registrada en
[ADR-001 — Modularización incremental del frontend](../../decisiones/ADR-001-modularizacion-frontend.md).

## Evidencia de implementación

- Rama frontend: `agent/hu-002-modularizacion-segura`; commit
  [`9e87bbb`](https://github.com/anomvlito/adyac-camaras-frontend/commit/9e87bbb88bf0c522a70fdc6025e9818f1f8aeff3),
  [PR #3](https://github.com/anomvlito/adyac-camaras-frontend/pull/3) y merge
  [`cf98218`](https://github.com/anomvlito/adyac-camaras-frontend/commit/cf982184c7da8ed683b138555ba0b6cb6941827f).
- Documentación preparada en la rama
  `agent/hu-002-modularizacion-segura` de `centralparking-mvp`.
- Respaldo verificado: `fd38cc1`; SHA-256 de `page.tsx` coincide con la línea
  base documentada.
- `src/app/page.tsx`: 972 → 109 líneas.
- Módulos añadidos bajo `src/features/`, `src/components/parking/` y `src/lib/`.
- `npm run lint`: correcto, 0 errores y 2 advertencias preexistentes de
  `no-img-element`.
- `npm exec tsc -- --noEmit`: correcto.
- `npm test`: 5 archivos y 11 pruebas correctas.
- `npm run test:e2e`: 4 escenarios correctos en Chromium, combinando acceso y
  navegación autenticada sintética en escritorio (1440×900) y móvil
  (390×844).
- Contratos HTTP: 15 llamadas antes y 15 después, comparación exacta sin
  diferencias.
- `npm run build`: correcto en el worktree aislado; build final
  `2avv4awLO7Hppp5Glc5tv`.
- Firma semántica del acceso antes/después:
  `3ad0daa89856d8f27617e493b5c37fda5294448feacd1badee526455c162bae2`.
- Backend local: `/docs` respondió 200 y login sintético inválido respondió
  401.
- Mejora no visual encontrada por las pruebas: labels de usuario y contraseña
  vinculados a sus inputs mediante `htmlFor`/`id`.
- La validación móvil detectó que la navegación del encabezado se solapaba a
  390 px. Se corrigió compactando el espaciado y ocultando sólo el nombre de
  marca en pantallas menores a `sm`; los cuatro escenarios E2E pasaron después
  del ajuste y la presentación de escritorio se conserva.
- Vercel confirmó el despliegue del merge `cf98218`; la aplicación productiva
  `https://centralparking-mvp.vercel.app` respondió HTTP 200 y entregó los
  textos esperados `CentralParking`, `Ingresá con tu cuenta` e `Ingresar`.
