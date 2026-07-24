# HU-009 — Observar y auditar decisiones del clasificador vertical

**Actor:** `auditor`  
**Estado:** `en-progreso`  
**Feature relacionada:** [Clasificación de entrada y salida por trayectoria vertical](../../features/in-progress/clasificacion-vertical-entrada-salida.md)  
**Issue:** [#27](https://github.com/anomvlito/centralparking-mvp/issues/27)  
**Project 4:** [Central Parking — Orquestación](https://github.com/users/anomvlito/projects/4) — `In progress` / `In Progress`  
**Creado por:** Codex, a solicitud del usuario  
**ADR relacionada:** [ADR-003 — Clasificar dirección exclusivamente por trayectoria vertical](../../decisiones/ADR-003-clasificacion-direccion-trayectoria-vertical.md)  
**HUs base:** [HU-007](../administrador/HU-007-clasificar-direccion-trayectoria-vertical.md), [HU-008](../administrador/HU-008-configurar-parametros-clasificador-vertical.md)

## Historia

Como **auditor**, quiero **consultar la evidencia y los factores que produjeron
cada resultado `APPROACHING`, `DEPARTING` o `UNKNOWN`**, para **medir errores,
reconstruir decisiones y verificar que una señal probabilística no se
transforme en una acción autoritativa sin revisión**.

## Contexto y problema

El clasificador anterior fue desconectado después de generar salidas falsas y
duplicados. Reactivar una señal direccional sin observabilidad repetiría la
incapacidad de distinguir entre:

- error OCR;
- geometría incorrecta;
- muestras insuficientes;
- desplazamiento o pendiente débiles;
- inconsistencia temporal;
- configuración invertida;
- error de integración con sesiones.

HU-007 define el algoritmo y HU-008 su configuración. Esta HU define la
evidencia mínima para medirlo antes de habilitar efectos y para auditarlo
después. No autoriza almacenar imágenes nuevas ni patentes en plataformas
externas.

## Criterios de aceptación

### Evidencia de cada evaluación

- [ ] Cada evaluación final genera un registro estructurado con identificador
  no ambiguo y timestamp de Chile.
- [ ] El registro incluye, como mínimo:
  - dirección resultante;
  - motivo de `UNKNOWN` o puerta que impidió clasificar;
  - cantidad de muestras;
  - duración de la secuencia;
  - `y_inicial`, `y_final` y desplazamiento;
  - pendiente normalizada/segundo;
  - consistencia;
  - umbrales/huella de configuración;
  - estrategia geométrica usada;
  - modo `observation_only`/activo;
  - referencias al avistamiento, imagen o sesión cuando existan.
- [ ] No se almacena `center_x`, tamaño ni zonas como factores del clasificador.
- [ ] Las muestras crudas solo se conservan si existe justificación, retención
  definida y acceso autorizado; de lo contrario se persiste el resumen.

### Motivos normalizados

- [ ] `UNKNOWN` diferencia al menos:

  ```text
  insufficient_samples
  expired_window
  invalid_coordinate
  insufficient_displacement
  insufficient_slope
  insufficient_consistency
  incompatible_geometry
  ```

- [ ] Errores técnicos se distinguen de una abstención normal.
- [ ] Los nombres son estables y están documentados para consultas.

### Privacidad y seguridad

- [ ] Logs generales no imprimen patentes completas ni rutas sensibles.
- [ ] Métricas agregadas no usan patente como label para evitar cardinalidad y
  exposición.
- [ ] El acceso a detalle está autenticado y autorizado para el actor
  correspondiente.
- [ ] La evidencia reutiliza relaciones existentes; no se copian imágenes sin
  necesidad.
- [ ] Se define retención para eventos detallados y agregados.
- [ ] Exportaciones y pruebas usan patentes anonimizadas.

### Métricas

- [ ] Se puede obtener, por período y versión de configuración:
  - total evaluado;
  - proporción `APPROACHING`/`DEPARTING`/`UNKNOWN`;
  - motivos de `UNKNOWN`;
  - decisiones en observación frente a activas;
  - correcciones/reconciliaciones posteriores;
  - tasa de desacuerdo con revisión humana cuando exista etiqueta.
- [ ] Confianza OCR y evidencia direccional se reportan separadamente.
- [ ] Las métricas no presentan `UNKNOWN` como fallo automáticamente.

### Modo sombra y activación

- [ ] Existe modo observación que calcula y registra dirección sin modificar
  sesiones ni conciliación.
- [ ] Se define un período/muestra mínima de evaluación antes de activar.
- [ ] La activación requiere evidencia documentada, configuración aprobada,
  regresión correcta y rollback probado.
- [ ] El sistema permite comparar qué habría decidido el clasificador con la
  resolución humana sin ejecutar esa decisión retrospectivamente.
- [ ] Un rollback no elimina la evidencia generada antes del cambio.

### Auditoría de efectos

- [ ] Si una dirección se usa en HU-004, el evento registra qué efecto se
  intentó y su resultado.
- [ ] Se puede rastrear:

  ```text
  imagen → avistamiento → evaluación direccional
         → conciliación/sesión → revisión/corrección
  ```

- [ ] Una corrección humana no sobrescribe la decisión original; agrega un
  evento relacionado.
- [ ] Ningún evento se marca como cobro, sanción o acceso autorizado solo por
  `APPROACHING`/`DEPARTING`.

## No-alcance

- Construir un dashboard visual completo salvo autorización posterior.
- Enviar imágenes, patentes o trayectorias a servicios externos.
- Usar patentes como etiquetas de métricas.
- Cambiar el algoritmo o sus umbrales.
- Corregir automáticamente decisiones con métricas.
- Borrar eventos históricos.
- Convertir `UNKNOWN` en error operativo.
- Autorizar cobro, sanción o acceso.

## Código relacionado

- Backend:
  - servicio/resultado de HU-007.
  - configuración/huella de HU-008.
  - `api/database.py::log_audit_event`.
  - `api/staging.py::_audit`, `/api/audit/log` y feedback.
  - `api/ftp_handler.py::_handle_auto_detection`.
  - repositorios de auditoría propuestos por HU-006.
- Frontend:
  - no requiere cambios para métricas backend.
  - HU-005 puede consumir evidencia revisable en una etapa separada.
- Operación:
  - logs de `centralparking.service` sin datos sensibles.
  - política de retención/backup existente a verificar.

## Contratos que deben preservarse

- `audit_log` y endpoints actuales no cambian silenciosamente.
- La trazabilidad existente no se elimina.
- Las correcciones siguen siendo auditadas.
- La respuesta de ALPR mantiene texto/confianza/estrategia.
- Los eventos direccionales son adicionales, no reemplazan avistamientos.
- Las rutas de evidencia siguen protegidas por los controles existentes.

Si se requiere un endpoint nuevo para consulta agregada o detalle, su contrato
debe definirse durante refinamiento con permisos y paginación; esta HU no
inventa uno sin revisar primero la capacidad de `/api/audit/log`.

## Impacto sobre funcionalidades existentes

Agregar auditoría puede aumentar escrituras y volumen de datos. Debe evitarse
registrar cada frame sin control; el evento final y, cuando sea necesario, un
resumen de la secuencia son preferibles. La instrumentación no puede retrasar
la ingesta FTP ni bloquear el pipeline si falla una métrica no crítica.

## Riesgos y datos

- Exposición de patentes en logs.
- Cardinalidad excesiva en métricas.
- Retención ilimitada.
- Auditoría dentro de una transacción separada que deje estados incoherentes.
- Instrumentación síncrona que degrade ALPR.
- Interpretar correcciones humanas incompletas como ground truth perfecto.
- Métricas agregadas que oculten errores por orientación/configuración.

## Pruebas de regresión

- Cada resultado genera el motivo correcto.
- `UNKNOWN` por cada puerta se distingue.
- No se registran X, tamaño ni zonas.
- Patentes se enmascaran en logs generales.
- Eventos enlazan IDs existentes sin duplicar imágenes.
- Modo sombra no modifica `parking_sessions`, `orphan_exits` ni cobros.
- Corrección agrega evento y conserva el original.
- Fallo del sink de métricas no pierde el avistamiento principal.
- Paginación/filtros de auditoría no rompen `/api/audit/log`.
- Retención elimina solo lo autorizado y nunca evidencia operativa protegida.
- Carga repetida no degrada de forma desproporcionada el pipeline.

## Propuesta técnica

1. Definir `DirectionEvaluation` tipado y serializable:

   ```json
   {
     "direction": "UNKNOWN",
     "reason": "insufficient_slope",
     "sample_count": 4,
     "duration_seconds": 2.8,
     "start_y": 0.31,
     "end_y": 0.35,
     "displacement": 0.04,
     "slope_per_second": 0.012,
     "consistency": 0.67,
     "config_version": "sha256:...",
     "geometry_strategy": "raw",
     "mode": "observation_only"
   }
   ```

2. No incluir patente en métricas agregadas; relacionar detalle mediante ID
   interno autorizado.
3. Persistir evento final en auditoría o tabla específica solo si el volumen y
   consultas lo justifican; decidirlo con medición, no por anticipación.
4. Separar logging operativo, auditoría durable y métricas agregadas.
5. Registrar la corrección humana como evento relacionado.
6. Definir criterio de activación y rollback antes de salir de modo sombra.

## Criterios sugeridos para evaluar activación

Los valores numéricos no se fijan en esta propuesta sin dataset representativo.
El refinamiento debe acordar:

- mínimo de secuencias etiquetadas;
- cobertura de entradas, salidas e inciertas;
- máximo tolerable de falsas salidas;
- máximo tolerable de falsas entradas;
- proporción aceptada de `UNKNOWN`;
- período sin regresiones de ingestión;
- responsable que aprueba parámetros;
- procedimiento de rollback.

## Dependencias

- Depende del resultado tipado de HU-007.
- Depende de versión/huella de HU-008.
- Debe existir antes de activar efectos productivos del clasificador.
- Complementa revisión/conciliación de HU-004 y HU-005.

## Evidencia de implementación

- Commit/PR: pendiente.
- Modelo de eventos: pendiente.
- Política de retención: pendiente.
- Métricas base: pendientes.
- Evaluación sombra: pendiente.
- Aprobación/rollback: pendientes.
