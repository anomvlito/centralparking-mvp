# Feature — Clasificación de entrada y salida por trayectoria vertical

**Etapa Project 4:** `In progress`  
**HUs relacionadas:** [HU-007](../../historias-usuario/administrador/HU-007-clasificar-direccion-trayectoria-vertical.md), [HU-008](../../historias-usuario/administrador/HU-008-configurar-parametros-clasificador-vertical.md), [HU-009](../../historias-usuario/auditor/HU-009-observar-decisiones-clasificador-vertical.md)  
**ADRs:** [ADR-001](../../decisiones/ADR-001-reactivar-direction-tracker-acotado.md), [ADR-003](../../decisiones/ADR-003-clasificacion-direccion-trayectoria-vertical.md)  
**Issues:** [#25](https://github.com/anomvlito/centralparking-mvp/issues/25), [#26](https://github.com/anomvlito/centralparking-mvp/issues/26), [#27](https://github.com/anomvlito/centralparking-mvp/issues/27)

## Problema

`DirectionTracker` está desconectado y acepta X/Y/tamaño. La instalación real
tiene cámara alta, un mismo sector, imagen truncada y desplazamiento vertical.
Conciliación necesita una señal revisable sin repetir las salidas falsas y
duplicados del uso autoritativo anterior.

## Resultado esperado

Clasificador exclusivamente por pendiente de `y(t)`, con desplazamiento,
regresión, consistencia, configuración validada, evidencia auditable y
`UNKNOWN` preservado.

## Alcance

- Confirmar sistema de coordenadas del recorte.
- Normalizar contra la imagen realmente inferida.
- Historial de 3 a 8 muestras por patente.
- Regresión con timestamps, desplazamiento y consistencia.
- Signo de entrada explícito.
- Pruebas sintéticas, configuración y observabilidad.
- Integración acotada según ADR-001.

## Exclusiones

- Zonas o cruces de zonas.
- X o tamaño del bbox.
- Límites `0.35`/`0.65` o recorrido completo.
- Cobro, sanción, acceso o dirección forzada.
- Soporte genérico para otras cámaras.

## Dependencias y orden

1. HU-006 establece una frontera ALPR estable.
2. HU-007 implementa el algoritmo sin habilitación autoritativa.
3. HU-008 gobierna parámetros.
4. HU-009 permite medir y auditar.
5. Activación solo con regresión, observabilidad, revisión y rollback.

## Contratos

- `center_y` pertenece al sistema documentado.
- Se preservan `APPROACHING`, `DEPARTING`, `UNKNOWN`.
- `UNKNOWN` conserva el avistamiento/evidencia para revisión y no abre ni
  cierra sesiones ni crea `orphan_exits`.
- La dirección no altera texto/confianza OCR.
- La evidencia conserva imagen, avistamiento y sesión.
- Los endpoints actuales no cambian.

## Criterio de cierre

Tres HUs verificadas con datos sintéticos/anonimizados, coordenadas
documentadas, resultados auditables, `UNKNOWN` y revisión preservados, y uso
productivo limitado por ADR-001 con rollback comprobado.
