# HU-001 — Identificar el acceso con un botón lila

**Actor:** `operador`
**Estado:** `implementada`
**Feature relacionada:** [Identidad visual del acceso](../../features/done/identidad-visual-acceso.md)
**Issue:** [#17](https://github.com/anomvlito/centralparking-mvp/issues/17)
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `Done`

## Historia

Como **operador**, quiero **ver el botón “Ingresar” en color lila**, para
**identificar claramente la acción principal de acceso a Central Parking**.

## Contexto y problema

La pantalla de acceso del frontend productivo presenta actualmente el botón
“Ingresar” con fondo índigo. Se solicita una prueba visual acotada que cambie
únicamente ese botón a una tonalidad lila, conservando su legibilidad y todos
los estados funcionales del inicio de sesión.

## Criterios de aceptación

- [x] En su estado normal, el botón “Ingresar” usa el color lila
  `violet-600`.
- [x] Al pasar el puntero sobre un botón habilitado, el fondo cambia a
  `violet-700`.
- [x] El texto permanece blanco y legible sobre los estados normal y hover.
- [x] Mientras se procesa el formulario, el botón conserva el texto
  “Ingresando...”, permanece deshabilitado y mantiene la atenuación visual
  existente.
- [x] Enviar credenciales válidas, inválidas o enfrentar un error de conexión
  conserva el comportamiento actual.
- [x] El cambio se limita al botón “Ingresar” y no altera otros elementos
  índigo de la pantalla o de la aplicación.

## No-alcance

- Cambiar el color del logotipo, bordes de foco, pestañas, filtros u otros
  botones.
- Rediseñar la pantalla de acceso o modificar textos, tipografía y espaciado.
- Modificar autenticación, roles, tokens, sesiones, API o backend.
- Desplegar el frontend en Vercel.

## Código relacionado

- Backend: no requiere cambios; se preserva `POST /auth/login`.
- Frontend:
  `../../../../adyac-camaras-frontend/src/app/page.tsx`, componente
  `LoginPage`.
- Operación: no requiere cambios.

## Contratos que deben preservarse

- El formulario continúa enviando `username` y `password` a
  `POST /auth/login`.
- Se preservan el estado deshabilitado, el indicador “Ingresando...” y los
  mensajes actuales de autenticación y conexión.
- No cambia la persistencia del token ni la navegación posterior al acceso.

## Impacto sobre funcionalidades existentes

El impacto esperado es exclusivamente visual. El flujo de autenticación y los
demás controles que usan la paleta índigo deben permanecer sin cambios.

## Riesgos y datos

- Riesgo bajo de regresión visual por modificar accidentalmente una clase
  compartida o más de un control.
- Debe verificarse contraste suficiente entre el texto blanco y el fondo lila.
- No se requieren datos reales, credenciales reales ni cambios relacionados
  con ALPR, evidencia o patentes.

## Pruebas de regresión

- Ejecutar `npm run lint` en `adyac-camaras-frontend`.
- Inspeccionar en navegador los estados normal, hover y deshabilitado del
  botón “Ingresar”.
- Probar el formulario con credenciales sintéticas inválidas y verificar que
  se conserve el mensaje existente sin registrar datos sensibles.
- Verificar que el cambio no afecte el logotipo ni otros botones índigo.

## Propuesta técnica

En `LoginPage`, sustituir únicamente las clases Tailwind `bg-indigo-600` y
`hover:bg-indigo-700` del botón `type="submit"` por `bg-violet-600` y
`hover:bg-violet-700`. Conservar todas las demás clases y la lógica del
componente.

## Evidencia de implementación

- Commit frontend:
  [`c674a31`](https://github.com/anomvlito/adyac-camaras-frontend/commit/c674a31)
  en `agent/hu-001-boton-ingresar-lila`; PR no solicitado.
- Código: el botón `type="submit"` de `LoginPage` usa `bg-violet-600` y
  `hover:bg-violet-700`; no se modificó su lógica ni otro elemento índigo.
- `git diff --check`: correcto.
- `npm exec tsc -- --noEmit`: correcto.
- Contraste calculado con texto blanco: `violet-600` 5.70:1 y `violet-700`
  7.10:1.
- `npm run lint`: correcto, 0 errores; conserva 2 advertencias conocidas de
  `no-img-element`.
- `npm run build`: correcto en una copia aislada, sin reemplazar la `.next` del
  proceso local activo.
- Validación renderizada: el HTML servido por el build aislado contiene el
  botón “Ingresar” con `bg-violet-600 hover:bg-violet-700`.
- Regresión de autenticación local: `/docs` respondió 200 y
  `POST /auth/login` con credenciales sintéticas inválidas respondió 401; la
  lógica del formulario no cambió.
