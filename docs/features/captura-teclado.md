# Feature: Captura de Patentes por Teclado

**Tipo:** feature  
**Estado:** borrador  
**Última actualización:** 2026-06-17  
**Autor:** Antigravity (AI Coding Assistant)

## Descripción

Esta funcionalidad permite a los operadores interactuar con la interfaz del capturador de cámaras utilizando accesos directos de teclado, específicamente la barra espaciadora (tecla Espacio), para disparar la toma de fotografías de patentes y su envío a la API de IA.

## Motivación

En ambientes de alta demanda, los operarios de estacionamiento prefieren el uso del teclado sobre el ratón para minimizar la fatiga y agilizar la entrada/salida de autos. Permitir que la tecla más accesible (Espacio) dispare la captura optimiza significativamente la ergonomía de la aplicación.

## Alcance

### Qué incluye:
- Atajo de teclado (tecla Espacio) para realizar capturas de cámara.
- Prevención de scroll lateral o vertical nativo al usar Espacio mientras la cámara está abierta.
- Regulación del estado para evitar dobles capturas accidentales.

### Qué NO incluye:
- Capturas automáticas basadas en detección de movimiento.
- Múltiples atajos configurables por el usuario.

## Comportamiento esperado

1. El operador hace clic en "ENTRADA" o "SALIDA" abriendo la cámara.
2. El operador apunta la cámara física.
3. Presiona la barra espaciadora.
4. El sistema previene el scroll, muestra la retroalimentación de captura y llama a la API.
5. Si el operador abre la búsqueda manual e intenta escribir, la barra espaciadora escribe el espacio normal.

## Arquitectura técnica

### Frontend
- Componente: [src/app/page.tsx](file:///Users/fabianortega/src/adyac-camaras-frontend/src/app/page.tsx)
- hook `useEffect` con listener global `keydown`:
  ```ts
  useEffect(() => {
    if (!isCameraOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        // Evitar comportamiento si está en un input o textarea
        if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") {
          return;
        }
        e.preventDefault();
        if (!isAnalyzing) {
          capture();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isCameraOpen, isAnalyzing, capture]);
  ```
