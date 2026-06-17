# HU-016 — Captura de Patentes mediante Tecla Espacio

**Tipo:** historia-usuario  
**Actor:** operador  
**Estado:** propuesta  
**Última actualización:** 2026-06-17  
**Feature relacionada:** [docs/features/captura-teclado.md](file:///Users/fabianortega/src/centralparking-mvp/docs/features/captura-teclado.md)

## Historia

Como **operador del estacionamiento**, quiero **poder realizar la captura de la patente presionando la tecla Espacio cuando la cámara está activa**, para **agilizar el flujo de entrada y salida sin depender exclusivamente del mouse o interfaz táctil**.

## Criterios de aceptación

- [ ] **Activación Contextual:** La tecla Espacio solo debe disparar la función `capture()` cuando el modal de la cámara esté abierto (`isCameraOpen` es `true`).
- [ ] **Prevención de Comportamientos por Defecto:** Al presionar Espacio, se debe evitar el scroll de la página o la activación de otros elementos enfocados (`event.preventDefault()`).
- [ ] **Exclusión con Entrada Manual:** Si el campo de entrada manual (`showManualInput`) está visible y enfocado por el cursor, presionar Espacio debe comportarse normalmente (permitir escribir espacios en el texto) y NO debe disparar la captura de la cámara.
- [ ] **Control de Concurrencia:** Si el análisis de imagen está en curso (`isAnalyzing` es `true`), la tecla Espacio debe ignorarse para evitar múltiples peticiones concurrentes a la API de IA.
- [ ] **Foco del Navegador:** El listener de teclado debe registrarse a nivel global (`window` / `document`) mientras la cámara esté activa para asegurar la captura sin importar el foco secundario.
- [ ] **Efecto de Feedback:** Se debe proporcionar una señal visual o de interacción (por ejemplo, simular el clic en el botón de captura) al presionar la tecla.

## Resolución Técnica e Implementación (Propuesta)

**Implementado en:** *[Pendiente]*

### Frontend (`adyac-camaras-frontend`)
- Escuchar eventos `keydown` en `page.tsx` mediante un hook `useEffect` condicionado a `isCameraOpen`.
- Validar que `document.activeElement` no sea un campo de entrada (`input`, `textarea`) antes de ejecutar `capture()`.
- Asegurar que `isAnalyzing` sea `false` antes de disparar la acción.
- Limpiar el event listener cuando la cámara se cierre o se desmonte el componente.
