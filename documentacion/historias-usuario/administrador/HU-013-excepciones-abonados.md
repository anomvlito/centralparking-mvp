# HU-013: Gestión de Patentes Mensuales (Excepciones)

## Resumen
**Como** administrador del sistema
**Quiero** gestionar una lista de patentes de "abonados mensuales" en una pestaña separada
**Para que** el sistema reconozca estos vehículos automáticamente como excepciones, no los mezcle con el tráfico regular en el dashboard principal, y soporte lectura parcial (fuzzy matching) en caso de errores de OCR.

## Criterios de Aceptación
1. **Frontend (Dashboard de Admin):**
   - Existe una nueva pestaña o sección exclusiva para administradores (ej. `/admin/abonados`).
   - El administrador puede ver una tabla con las patentes marcadas como abonados.
   - Puede agregar una nueva patente y eliminar una existente.
2. **Backend (API y BD):**
   - Existe una tabla `monthly_plates` en la base de datos para almacenar estas patentes (campos: id, plate, created_at).
   - Existen endpoints CRUD para esta tabla protegidos por autenticación de administrador (`/api/abonados`).
3. **Pipeline de Detección (ALPR):**
   - Cuando una patente entra por FTP, el pipeline consulta la base de datos de abonados (reemplazando la lista temporal en memoria).
   - Se utiliza lógica *fuzzy*: si la patente leída tiene igual longitud y coincide en 4 o más caracteres en la misma posición con un abonado, se clasifica automáticamente como abonado.
   - Las detecciones de abonados se marcan como `IGNORED_MONTHLY` y NO pasan al flujo regular de conciliación de estancias, evitando ensuciar el Dashboard.
4. **Segunda Etapa (Futura, Fuera de esta iteración inmediata):**
   - Limpieza hacia atrás de la base de datos de estancias y detecciones previas asociadas a estas patentes.

## Regresiones a probar
- Vehículos regulares siguen pasando al flujo normal de entrada/salida.
- La tabla de estancias completas y pendientes en el Dashboard no se rompe por la existencia de detecciones ignoradas.
- La vista de abonados solo es accesible por un usuario admin validado.

## Notas Técnicas
- Reemplazar la función `is_monthly_exception` hardcodeada en `api/ftp_handler.py` por una consulta a la base de datos, preferiblemente con caché o consulta rápida (ya que se invoca por cada detección).
