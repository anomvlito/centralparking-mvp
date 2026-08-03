# Matriz de regresión

Revisar las filas afectadas antes de implementar y registrar pruebas concretas
en la HU.

| Dominio | Contratos a preservar | Verificación mínima |
| --- | --- | --- |
| Autenticación | JWT, expiración, roles, sesión y errores 401/403 | Login, `/auth/me`, permisos admin y sesión vencida |
| Entradas/salidas | Estado de vehículos, sesiones y timestamps Chile | Entrada, salida, duplicado y corrección |
| ALPR | Normalización, confianza, estrategia y validación | Detección válida, sin detección y patente incierta |
| Staging | Deduplicación, promoción y evidencia elegida | Avistamientos repetidos y promoción expirada |
| FTP/watchdog | Archivo estable, archivo histórico y reintentos | Imagen, video, error del backend y reinicio |
| Historial | Filtros, paginación, corrección y revisión | Día actual, día histórico y edición auditada |
| Conciliación Excel | Importación, matching y discrepancias | Excel válido, inválido, duplicado y sin match |
| Frontend/API | URLs, payloads, estados y manejo de errores | Flujo feliz, 401, 403, 4xx/5xx y reconexión |
| Evidencia | Rutas, acceso y relación sesión/avistamiento | Imagen existente, faltante y no autorizada |
| Despliegue | Backend VPS y frontend Vercel separados | Health backend y preview/build frontend |
