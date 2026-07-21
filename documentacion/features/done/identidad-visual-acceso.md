# Feature — Identidad visual del acceso

**Etapa Project 4:** `Done`
**HUs relacionadas:** [HU-001 — Identificar el acceso con un botón lila](../../historias-usuario/operador/HU-001-boton-ingresar-lila.md)
**Issues:** [#17](https://github.com/anomvlito/centralparking-mvp/issues/17)

## Problema

La acción principal de la pantalla de acceso necesita una identidad visual
explícita y comprobable sin alterar el flujo de autenticación.

## Resultado esperado

El botón “Ingresar” se distingue mediante la paleta lila acordada, conserva
legibilidad en sus estados y mantiene intacto el comportamiento del login.

## Alcance

- Color normal y hover del botón principal de acceso.
- Conservación de los estados de carga y deshabilitado.
- Verificación visual y regresión mínima del formulario.

## No-alcance

- Unificar o reemplazar la paleta índigo del resto de la aplicación.
- Cambiar componentes, textos, autenticación o contratos API.
- Realizar despliegues.

## Contratos

- Frontend productivo en `adyac-camaras-frontend/src/app/page.tsx`.
- El contrato `POST /auth/login` y su manejo de respuestas no cambian.
- El ajuste no debe propagarse a otros botones o indicadores.

## Riesgos

- Contraste insuficiente o cambio accidental de otros elementos visuales.
- Confundir esta prueba acotada con una migración completa de identidad visual.

## Criterio de cierre

La HU relacionada cumple sus criterios de aceptación, supera lint y se valida
visualmente en los estados normal, hover y deshabilitado, sin regresiones en el
inicio de sesión.
