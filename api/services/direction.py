"""Caso de uso de observación direccional y auditoría durable."""

from __future__ import annotations

from collections.abc import Callable

from api.core.config import DIRECTION_SETTINGS, DirectionSettings
from api.direction_tracker import DirectionEvaluation, DirectionTracker

AuditSink = Callable[[str | None, str, dict], None]


class DirectionService:
    def __init__(
        self,
        settings: DirectionSettings | None = None,
        tracker: DirectionTracker | None = None,
        audit_sink: AuditSink | None = None,
    ):
        self.settings = settings or DIRECTION_SETTINGS
        self.tracker = tracker or DirectionTracker(self.settings)
        self._audit_sink = audit_sink

    def observe(
        self,
        *,
        plate: str,
        center_y: float | None,
        timestamp: float | None = None,
        geometry_strategy: str | None = None,
        source: str | None = None,
        ocr_confidence: float | None = None,
        sighting_id: int | None = None,
        image_path: str | None = None,
    ) -> DirectionEvaluation | None:
        """Evalúa sin ejecutar efectos de estacionamiento.

        Con ``enabled=false`` el flujo anterior permanece intacto. En modo
        observación se audita el resultado, pero tampoco se mutan sesiones.
        El modo activo queda reservado para el caso de uso de conciliación de
        HU-004; este servicio por sí mismo nunca abre ni cierra sesiones.
        """

        if not self.settings.enabled or center_y is None:
            return None

        evaluation = self.tracker.evaluate(
            plate,
            center_y,
            timestamp,
            geometry_strategy=geometry_strategy,
        )
        details = {
            **evaluation.to_dict(),
            "source": source,
            "ocr_confidence": ocr_confidence,
            "sighting_id": sighting_id,
            "image_path": image_path,
            "effect": "none",
        }
        if self._audit_sink is not None:
            try:
                self._audit_sink(plate, "DIRECTION_EVALUATED", details)
            except Exception:
                # La telemetría no puede perder el avistamiento principal.
                pass
        return evaluation


def _database_audit_sink(plate: str | None, event_type: str, details: dict) -> None:
    from api.database import log_audit_event

    log_audit_event(plate, event_type, details)


direction_service = DirectionService(audit_sink=_database_audit_sink)
