# Feature — Registro de ingreso/salida de abonados

**Etapa Project 4:** `In progress`
**HU:** [HU-014](../../historias-usuario/administrador/HU-014-registro-ingreso-salida-abonados.md)

Los abonados (`plate_exclusions`) dejan de descartarse sin rastro: pasan por
el mismo pipeline de staging/detección que un vehículo regular (foto,
deduplicación, `detection_log`), marcados aparte para no mezclarse con el
Dashboard ni la conciliación de estadías pagas. `CYLF87` (dueño del
estacionamiento) es la única excepción que se sigue descartando por
completo. Solo backend en esta iteración — el frontend queda para un
trabajo posterior.
