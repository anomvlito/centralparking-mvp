# Central Parking MVP 🅿️✨

## 📄 Introducción
**Central Parking MVP** es una solución de gestión de flujo vehicular diseñada para la captura, monitoreo y cobro automatizado en estacionamientos de alto tráfico. El sistema combina una interfaz de usuario moderna con un motor de Inteligencia Artificial de vanguardia para el Reconocimiento Automático de Patentes (ALPR).

---

## 🏗️ Metodología de Trabajo: Arquitectura Híbrida
Para este proyecto, hemos implementado una **Metodología de Cómputo Híbrido** explícita, diseñada para maximizar el rendimiento y la accesibilidad:

1.  **Frontend (Nube - Vercel):** La interfaz de usuario está construida en **Next.js 15**, desplegada globalmente en Vercel. Esto permite que los operadores accedan al sistema desde cualquier dispositivo (celular, tablet o laptop) con una latencia mínima en la UI.
2.  **Backend (Local - Servidor de IA):** Debido a que el procesamiento de imágenes mediante redes neuronales es intensivo en recursos, el núcleo de detección de patentes corre en un **servidor local (Python/FastAPI)**. Esto permite utilizar la potencia del hardware local (CPU/GPU) para ejecutar modelos ONNX sin las limitaciones de las funciones serverless de la nube.
3.  **Túnel de Conexión (Tunneling):** Ambos mundos se conectan mediante un túnel seguro (Cloudflare/Ngrok), permitiendo que la web de Vercel "hable" con la IA instalada en la locación física del estacionamiento.

---

## 🧠 Motor de IA e Inspiración: Repositorios Utilizados
El corazón del sistema se basa en la excelencia técnica de la comunidad de código abierto. Hemos utilizado e integrado profundamente el siguiente repositorio como base de nuestra inteligencia:

*   **[Fast-ALPR](file:///home/fabian/src/proyectos_web/central-parking/repos/fast-alpr):** Esta es nuestra principal fuente de inspiración y motor de ejecución. 
    *   Utilizamos su implementación de **YOLOv9-t** para la localización de la placa en tiempo real.
    *   Incorpoamos el modelo **CCT-XS-v2** para el OCR global de alta precisión.
    *   **Mejora de Detección:** Implementamos una lógica de "Doble Pasada" personalizada. Si la primera predicción falla, el backend aplica automáticamente una técnica de realce de contraste **CLAHE** (Contrast Limited Adaptive Histogram Equalization) para leer patentes en condiciones difíciles (fotos a pantallas, oscuridad o ángulos cerrados), inspirada en flujos de pre-procesamiento industrial.

---

## 🚀 Funcionalidades Principales

### 🌑 Control y Acciones
*   **Registro de Entrada:** Captura inmediata con "viewfinder" (visor) centrado para maximizar la tasa de éxito del OCR.
*   **Cobro de Salida:** Cálculo automático de tarifas basado en el tiempo de estancia exacto.
*   **Gestión de Eventos:** Selector rápido de tarifas fijas para convenios como "Matucana 100", "Premium" o "VIP".

### 📊 Monitor en Tiempo Real (Mapa de Planta)
*   Visualización de todos los autos actualmente dentro del recinto.
*   **Barra de Progreso de 4 Horas:** Exclusiva para tarifas normales, permite visualizar de un vistazo cuánto le queda a cada vehículo para cumplir el límite de cortesía o vigilancia estándar (240 minutos).
*   Alertas visuales: Verde (Seguro), Amarillo (Aviso), Rojo (Límite cumplido).

### 📈 Cierre y Estadísticas
*   **Cierre de Caja:** Reporte financiero instantáneo con los ingresos totales del día.
*   **Historial CSV Navegable:** Un log detallado de cada movimiento (Entrada, Salida, Anulación) que se lee directamente del archivo `history.csv` local.
*   **Limpieza Administrativa:** Función para borrar el historial del día con un solo clic, permitiendo reiniciar la operación administrativa sin afectar los autos vigilados actualmente.

---

## 💾 Persistencia de Datos
El sistema prioriza la redundancia y la simplicidad:
*   `parking_db.json`: Almacena el estado actual de los vehículos en planta. Si el servidor se apaga, los autos "vigilados" no se pierden.
*   `history.csv`: Registro histórico para auditoría manual y análisis de datos en Excel/Spreadsheets.

---

## 🛠️ Configuración y Despliegue

### Requisitos del Servidor Local
1.  Python 3.10+
2.  Dependencias: `fastapi`, `uvicorn`, `fast-alpr`, `opencv-python-headless`.
3.  Comando de ejecución:
    ```bash
    uvicorn api.detect:app --host 0.0.0.0 --port 8000 --reload
    ```

### Variables de Entorno (Vercel)
*   `NEXT_PUBLIC_API_URL`: Dirección de tu túnel público (ej. `https://tu-tunel.trycloudflare.com`). Note que este debe actualizarse si el túnel cambia.

---

## 💎 Diseño y UX
Priorizamos una estética **"Bold & Simple"**:
*   **Cero Itálicas:** Todo el texto es sólido y recto para máxima legibilidad profesional.
*   **Dark Mode Nativo:** Optimizado para reducir la fatiga visual del operador en cabina.
*   **Contención Total:** El diseño está estrictamente auditado para nunca desbordarse en pantallas pequeñas o celulares de gama media.

---
*Desarrollado con enfoque en operatividad táctica para Central Parking.*
