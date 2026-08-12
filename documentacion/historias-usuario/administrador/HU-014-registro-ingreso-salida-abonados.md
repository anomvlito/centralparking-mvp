# HU-014: Registro de ingreso y salida de abonados

## Resumen
**Como** administrador del sistema
**Quiero** que los avistamientos de patentes de abonados (`plate_exclusions`)
queden registrados con su foto en una sección propia, separada del tráfico
regular
**Para que** exista trazabilidad de ingreso/salida de los abonados sin
mezclarlos con el Dashboard ni el flujo de conciliación de estadías pagas.

## Contexto

Hoy `plate_exclusions` (ver [HU-013](HU-013-excepciones-abonados.md)) trata
a todo abonado exactamente igual: `_handle_auto_detection` corta el flujo
apenas lee la patente, no guarda foto, no crea fila en `detection_log`, y
solo deja un evento `IGNORED_MONTHLY` en el log auxiliar de FTP. Eso incluye
tanto a los abonados mensuales reales como a `CYLF87`, la patente del dueño
del estacionamiento.

El dueño (`CYLF87`) debe seguir sin dejar ningún rastro — ese comportamiento
no cambia. El resto de los abonados sí debe quedar con registro fotográfico
de cada ingreso/salida, en una sección aparte que un administrador pueda
revisar, sin que ensucien el Dashboard de tráfico regular ni sus propuestas
de conciliación.

## Criterios de Aceptación

1. **Pipeline de detección:**
   - `CYLF87` (comparado por patente normalizada, no por quién la cargó) se
     sigue descartando por completo: sin foto, sin fila en `detection_log`,
     acción `IGNORED_MONTHLY` sin cambios.
   - Cualquier otro match contra `plate_exclusions` pasa por el mismo
     pipeline que un vehículo regular hoy: `staging_submit` (piso de
     confianza, deduplicación de foto por ventana), promoción a
     `detection_log` con `match_status = UNMATCHED` (no `DISMISSED`), foto
     guardada en `/ftp/historico/{fecha}` igual que cualquier otra
     detección.
   - Cada fila de `detection_log`/`staging_detections` para estas
     detecciones queda marcada (`is_subscriber`) y asociada a la patente de
     abonado que matcheó (`subscriber_plate`), para poder filtrarla y saber
     a quién corresponde incluso si el OCR leyó una variante.
2. **Separación del flujo regular:**
   - Las consultas existentes del Dashboard (`/api/detections`,
     `/api/stay-proposals`, etc.) siguen excluyendo a los abonados por
     defecto — comportamiento actual sin cambios para el tráfico regular.
   - Nuevos endpoints (solo backend en esta iteración, ver Fuera de
     alcance) exponen el registro de abonados: detecciones crudas y
     propuestas de ingreso/salida emparejadas, reusando exactamente la
     misma lógica de emparejamiento (`build_stay_proposals`: EXACT/FUZZY,
     mínimo de 5 minutos) que ya se usa para el tráfico regular.
   - Solo un administrador puede consultar estos endpoints.

## Fuera de alcance (esta iteración)

- Frontend: no se agrega ninguna pestaña/sección visual todavía. Los
  endpoints quedan listos para que un futuro trabajo de frontend los
  consuma.
- No se crean `parking_sessions` para abonados (no hay cobro ni cierre
  formal de estadía) — el "registro" es la lista de avistamientos y sus
  propuestas de emparejamiento entrada/salida, consultada por fecha, igual
  que hoy existe para el tráfico regular antes de conciliarse.
- No se migran ni reprocesan detecciones históricas ya descartadas como
  `IGNORED_MONTHLY` antes de este cambio (esa foto nunca se guardó, no hay
  nada que recuperar).

## Regresiones a probar

- `CYLF87` sigue sin generar foto ni fila en `detection_log`.
- Vehículos regulares (sin match en `plate_exclusions`) siguen su flujo
  actual sin cambios: staging, `detection_log`, Dashboard, propuestas de
  conciliación.
- El Dashboard y `/api/stay-proposals` no muestran detecciones de abonados.
- Un abonado detectado dos veces dentro de la ventana de staging sigue
  compitiendo por la mejor foto igual que un auto regular.
- Los endpoints nuevos requieren rol administrador.

## Notas Técnicas

- `api/ftp_handler.py::_handle_auto_detection`: reemplazar el corte
  temprano por `is_plate_excluded` por una consulta que devuelva el match
  completo (`plate_exclusions` row o `None`), para poder distinguir
  `CYLF87` del resto.
- `api/staging.py::staging_submit` / `staging_promote_expired`: propagar
  `is_subscriber`/`subscriber_plate` de punta a punta hasta
  `log_to_db`.
- `api/database.py::log_to_db`: cuando `is_subscriber=True`, no aplicar el
  marcado automático `DISMISSED` por exclusión (ese chequeo sigue intacto
  para todo el resto de los llamadores, que no pasan el flag).
- Reusar `build_stay_proposals` sin modificarlo: ya trae el piso de 5
  minutos, EXACT/FUZZY y la resolución de patente por confianza que se
  ajustaron para el tráfico regular.

## Implementación (2026-08-12)

- `find_plate_exclusion_match(cur, normalized)` / `get_plate_exclusion_match(plate)`
  en `api/database.py`: devuelven la fila de `plate_exclusions` que
  matchea, o `None` — reemplaza el uso de `is_plate_excluded` (bool) dentro
  de `_handle_auto_detection`, que ahora sí necesita saber CUÁL abonado
  matcheó, no solo si matcheó.
- `detection_log`/`staging_detections` ganan `is_subscriber BOOLEAN` y
  `subscriber_plate VARCHAR(6)` (migración idempotente en `init_db()`).
- `get_detection_events(..., subscribers: bool = False)`: nuevo parámetro,
  default `False` preserva el comportamiento actual de toda consulta
  existente sin tocarla.
- `get_subscriber_stay_proposals(date, limit)`: mismo `build_stay_proposals`
  sin modificar, alimentado con `get_detection_events(subscribers=True)`.
- Endpoints nuevos, admin-only: `GET /api/subscribers/detections`,
  `GET /api/subscribers/stay-proposals`.
- Tests: `tests/test_subscriber_registry.py` — unitarios (mock de cursor y
  de `staging_submit`) para el corte owner-vs-abonado en
  `_handle_auto_detection`, y de integración (gateados por
  `RUN_DB_INTEGRATION_TESTS=1`, sin correr contra la base de producción)
  para `staging_promote_expired`/`log_to_db`.
