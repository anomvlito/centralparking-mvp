# Ordenamiento sutil de Sesiones Completas

## Problema
En el Dashboard de 3 columnas para la conciliación de registros, la columna de "Sesiones Completas" lista las estancias finalizadas del día. Actualmente no hay un control explícito para ordenar estos registros, lo que dificulta la búsqueda o revisión cuando el operador quiere priorizar ver los vehículos que acaban de salir versus los que acaban de entrar.

## Solución
Añadir un filtro o selector visualmente sutil (minimalista) en la cabecera de la columna "Sesiones Completas" que permita al usuario alternar el ordenamiento entre:
1. **Horario de Entrada** (más reciente a más antiguo, y viceversa).
2. **Horario de Salida** (más reciente a más antiguo, y viceversa).

## Consideraciones Técnicas
- **Frontend (`adyac-camaras-frontend`):** 
  - Añadir un control UI de ordenamiento (ej. un icono interactivo o un menú desplegable muy limpio) en la cabecera de la columna de sesiones completas (`src/features/dashboard/Dashboard.tsx`).
  - Como ya existe la navegación por días (HU-005), el arreglo de sesiones del día ya está en memoria local en el cliente. El ordenamiento puede y debe hacerse de manera óptima directamente en el frontend usando Javascript (ej. `Array.sort()`), sin necesidad de recargar ni hacer nuevas peticiones a la API.
- **Backend (`centralparking-mvp`):**
  - Ningún impacto. El endpoint actual que sirve los registros del día continuará enviando la data tal cual, delegando la responsabilidad de presentación al frontend.

## Criterios de Aceptación Preliminares
- [ ] En la columna "Sesiones Completas", el operador ve un control para ordenar que se integra armónicamente (sutil) con la interfaz actual.
- [ ] El operador puede ordenar la lista usando como criterio la hora de "Entrada" o la hora de "Salida".
- [ ] El cambio de orden refresca la lista de inmediato en el navegador.

## Siguientes Pasos
- Convertir esto en una Historia de Usuario (HU) formal si se aprueba el diseño.
- Agregar al Kanban (Project 4) en estado "Todo".
