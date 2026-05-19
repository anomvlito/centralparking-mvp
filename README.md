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

*   **[Fast-ALPR](https://github.com/ankandrew/fast-alpr):** Esta es nuestra principal fuente de inspiración y motor de ejecución.
    *   Utilizamos su implementación de **YOLOv9-t** para la localización de la placa en tiempo real.
    *   Incorporamos el modelo **CCT-XS-v2** para el OCR global de alta precisión.

---

## 🔬 Pipeline de Detección de Patentes: Arquitectura Multi-Estrategia

El módulo `api/detect.py` implementa un **pipeline de 11 estrategias de pre-procesamiento** que se ejecutan en cascada. La primera estrategia que retorna un resultado válido "gana" (_fast path_), evitando cómputo innecesario.

### Modelo Base: YOLOv9 + CCT-XS-v2

Antes de cualquier estrategia, cada imagen pasa por dos etapas:

| Etapa | Modelo | Función |
|---|---|---|
| **Detección** | `yolo-v9-t-384-license-plate-end2end` | Localiza el bounding box de la patente dentro de la imagen |
| **OCR** | `cct-xs-v2-global-model` (ONNX) | Lee los caracteres dentro del bounding box detectado |

El umbral de detección está ajustado a **0.25** (más bajo de lo normal) para capturar patentes en condiciones difíciles. La confianza final se calcula como el promedio de las probabilidades por carácter (`statistics.mean(char_probs)`).

---

### Estrategias de Pre-procesamiento (en orden de ejecución)

#### 1. `raw` — Imagen directa
La imagen se envía al modelo sin ninguna transformación. Es la estrategia más rápida y funciona para fotos bien encuadradas con buena iluminación. Si tiene éxito, el pipeline se detiene aquí.

#### 2. `clahe` — Realce de Contraste Adaptativo
```
Espacio: BGR → LAB → (aplica CLAHE al canal L) → BGR
Parámetros: clipLimit=3.0, tileGridSize=(8×8)
```
**CLAHE** (Contrast Limited Adaptive Histogram Equalization) opera en el canal de luminosidad del espacio LAB, evitando saturar los colores. Es la estrategia clave para fotos tomadas **a pantallas de CCTV**, entornos oscuros o con iluminación despareja. Inspirada en flujos de pre-procesamiento industrial para ALPR.

#### 3. `sharpen` — Enfoque por Unsharp Masking
```
resultado = imagen × 1.5 − GaussianBlur(imagen) × 0.5
```
Implementa la técnica clásica de _unsharp masking_: resta una versión borrosa de la imagen a sí misma para amplificar los bordes. Efectivo cuando la foto viene **movida, tomada en ángulo o con lente de mala calidad**.

#### 4. `deskew` — Corrección de Perspectiva
```
Canny → findContours → approxPolyDP (4 vértices) → warpPerspective
```
Detecta el contorno rectangular dominante en la imagen y aplica una transformación de perspectiva (_warpPerspective_) para "aplanar" la placa. Resuelve el caso en que el operador **fotografía la patente en diagonal** — los caracteres quedan inclinados y el OCR falla. Solo se activa si se encuentra un cuadrilátero con al menos 10px de ancho y 5px de alto.

#### 5. `deskew+clahe` — Perspectiva + Contraste
Combinación secuencial: primero corrige la perspectiva, luego aplica CLAHE. Cubre el caso más difícil: **foto diagonal tomada a una pantalla oscura**.

#### 6. `bilateral+clahe` — Denoising + Contraste
```
bilateralFilter(d=9, sigmaColor=75, sigmaSpace=75) → CLAHE
```
El filtro bilateral reduce el ruido de compresión JPEG preservando los bordes duros de los caracteres (a diferencia de un blur gaussiano que los destruiría). Luego CLAHE recupera el contraste. Ideal para **imágenes muy comprimidas o capturadas con cámaras de baja calidad**.

#### 7. `grayscale_eq` — Escala de Grises + Ecualización
```
BGR → GRAY → equalizeHist → BGR (3 canales)
```
Convierte a escala de grises y ecualiza el histograma globalmente para normalizar el contraste entre los caracteres y el fondo de la placa. Inspirada en el flujo de ParkingAPP, que convierte a GRAY antes del matching por SIFT. Funciona bien cuando la placa tiene **caracteres muy claros sobre fondo muy oscuro o viceversa**.

#### 8. `center_crop` — Recorte del Centro (60%)
```
Recorta un margen del 20% en cada lado → resize a dimensión original
```
Elimina el 20% exterior de la imagen en todos los lados, conservando el 60% central, y lo redimensiona al tamaño original. Resuelve el caso en que el operador **tomó la foto de lejos** y la patente está en el centro pero el contexto de la escena confunde al detector.

#### 9. `center_crop+clahe` — Recorte + Contraste
Combinación: recorte central seguido de CLAHE. Cubre **fotos de lejos tomadas a pantallas**.

#### 10. `upscale` — Amplificación 2× Bicúbica
```
resize(width×2, height×2, interpolation=INTER_CUBIC)
```
Dobla las dimensiones de la imagen con interpolación bicúbica. YOLOv9 fue entrenado a resolución 384px — si la imagen original es muy pequeña, la patente queda con **muy pocos píxeles y el modelo pierde precisión**. El upscale 2× compensa esto.

#### 11. `upscale+clahe` — Amplificación + Contraste
La combinación final y más costosa: amplifica primero para dar más píxeles al modelo, luego aplica CLAHE para mejorar el contraste. Es el último recurso antes de declarar que la patente no es detectable.

---

### Resumen del Pipeline

```
Imagen de entrada
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  Estrategia 1:  raw              → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 2:  clahe            → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 3:  sharpen          → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 4:  deskew           → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 5:  deskew+clahe     → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 6:  bilateral+clahe  → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 7:  grayscale_eq     → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 8:  center_crop      → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 9:  center_crop+clahe→ YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 10: upscale          → YOLOv9+CCT ──→ ✅ FIN │
│  Estrategia 11: upscale+clahe    → YOLOv9+CCT ──→ ✅ FIN │
└──────────────────────────────────────────────────────────┘
       │
       ▼ (todas fallaron)
  { plate: null, error: "no_detection" }
```

La primera estrategia que encuentre al menos **4 caracteres alfanuméricos** con confianza positiva detiene el pipeline y retorna el resultado.

---

### Pipeline de Video: Filtrado en 3 Niveles

El módulo `api/video_processor.py` aplica tres capas de filtrado para procesar grabaciones CCTV sin consumir recursos innecesariamente:

| Nivel | Técnica | Condición de descarte |
|---|---|---|
| **Tier 1 — Skip Frames** | Procesa 1 de cada 10 cuadros | `frame_count % 10 != 0` |
| **Tier 2 — Detección de Movimiento** | `BackgroundSubtractorMOG2` (history=50, varThreshold=50) | Menos del 2% de píxeles con movimiento |
| **Tier 3 — Validación Cruzada** | Buffer de confirmaciones consecutivas | La patente debe aparecer en ≥2 cuadros seguidos |

**Tier 1** reduce el cómputo en ~90% al saltarse cuadros repetitivos. **Tier 2** descarta escenas estáticas donde no hay ningún vehículo en movimiento, evitando "patentes fantasma" en letreros o fondos fijos. **Tier 3** exige que el mismo texto de patente sea reconocido de forma consistente antes de registrarlo como evento real, eliminando lecturas espurias por artefactos de compresión de video.

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

### 🎥 Procesamiento de Video Offline (Auditoría Batch)
*   **Lectura de archivos CCTV:** Interfaz para cargar grabaciones en video (MP4, AVI, MOV).
*   **Mecanismo "Anti-Fatiga" de IA (3-Tiered Filtering):**
    *   **Skip-Frames:** Solo se procesa 1 cada 10 cuadros, optimizando la velocidad exponencialmente.
    *   **Detección de Movimiento:** Un algoritmo evalúa con `BackgroundSubtractorMOG2` si algún objeto del tamaño de un auto se está moviendo. Si la escena es estática, se evita accionar la IA.
    *   **Validación Cruzada:** Para evitar falsos positivos ("Patentes fantasma"), el motor debe observar la misma secuencia de letras de manera consistente durante al menos 2 validaciones previas antes de aceptarla como ingreso real.
*   **Conciliación de Datos (Work In Progress):** Construído sobre la métrica de cruzar e invalidar patentes. Servirá próximamente para comparar los listados del cliente contra lo detectado por la IA.

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
3.  Comando de ejecución (Importante: Ejecutar desde la carpeta `centralparking-mvp`):
    ```bash
    cd centralparking-mvp
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
