"""Clasificación de dirección exclusivamente por trayectoria vertical."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from api.core.config import DIRECTION_SETTINGS, DirectionSettings


@dataclass(frozen=True)
class DirectionEvaluation:
    direction: str
    reason: Optional[str]
    sample_count: int
    duration_seconds: float
    start_y: Optional[float]
    end_y: Optional[float]
    displacement: Optional[float]
    slope_per_second: Optional[float]
    consistency: Optional[float]
    config_version: str
    geometry_strategy: Optional[str]
    mode: str

    def to_dict(self) -> dict:
        return asdict(self)


class DirectionTracker:
    """Mantiene hasta ocho muestras ``(timestamp, center_y)`` por patente.

    ``record`` conserva el contrato compacto de resultado textual.
    ``evaluate`` entrega la evidencia tipada requerida para auditoría.
    """

    def __init__(
        self,
        settings: DirectionSettings | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.settings = settings or DIRECTION_SETTINGS
        self._clock = clock or time.monotonic
        self._history: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self._latest: dict[str, DirectionEvaluation] = {}

    def record(
        self,
        plate: str,
        center_y: float,
        timestamp: float | None = None,
        *,
        geometry_strategy: str | None = None,
    ) -> str:
        return self.evaluate(
            plate,
            center_y,
            timestamp,
            geometry_strategy=geometry_strategy,
        ).direction

    def evaluate(
        self,
        plate: str,
        center_y: float,
        timestamp: float | None = None,
        *,
        geometry_strategy: str | None = None,
    ) -> DirectionEvaluation:
        now = self._clock() if timestamp is None else float(timestamp)
        if not 0.0 <= center_y <= 1.0:
            return self._remember(
                plate,
                self._unknown(
                    "invalid_coordinate",
                    geometry_strategy=geometry_strategy,
                ),
            )

        history = self._history[plate]
        history[:] = [
            (sample_time, y)
            for sample_time, y in history
            if 0 <= now - sample_time <= self.settings.window_seconds
        ]
        if history and now <= history[-1][0]:
            return self._remember(
                plate,
                self._unknown(
                    "invalid_timestamp",
                    sample_count=len(history),
                    geometry_strategy=geometry_strategy,
                ),
            )

        history.append((now, center_y))
        if len(history) > self.settings.max_history:
            del history[: -self.settings.max_history]

        evaluation = self._classify(history, geometry_strategy)
        return self._remember(plate, evaluation)

    def _classify(
        self,
        history: list[tuple[float, float]],
        geometry_strategy: str | None,
    ) -> DirectionEvaluation:
        if len(history) < self.settings.min_samples:
            return self._unknown(
                "insufficient_samples",
                sample_count=len(history),
                history=history,
                geometry_strategy=geometry_strategy,
            )

        start_time, start_y = history[0]
        end_time, end_y = history[-1]
        duration = end_time - start_time
        if duration <= 0:
            return self._unknown(
                "invalid_timestamp",
                sample_count=len(history),
                history=history,
                geometry_strategy=geometry_strategy,
            )

        displacement = end_y - start_y
        slope = self._linear_regression_slope(history)
        consistency = self._consistency(history, displacement)

        if abs(displacement) < self.settings.min_displacement:
            reason = "insufficient_displacement"
        elif abs(slope) < self.settings.min_slope_per_second:
            reason = "insufficient_slope"
        elif consistency < self.settings.min_consistency:
            reason = "insufficient_consistency"
        else:
            reason = None

        if reason:
            direction = "UNKNOWN"
        else:
            movement_sign = 1 if slope > 0 else -1
            entry_sign = 1 if self.settings.entry_sign == "positive" else -1
            direction = (
                "APPROACHING" if movement_sign == entry_sign else "DEPARTING"
            )

        return DirectionEvaluation(
            direction=direction,
            reason=reason,
            sample_count=len(history),
            duration_seconds=round(duration, 6),
            start_y=round(start_y, 6),
            end_y=round(end_y, 6),
            displacement=round(displacement, 6),
            slope_per_second=round(slope, 6),
            consistency=round(consistency, 6),
            config_version=self.settings.version,
            geometry_strategy=geometry_strategy,
            mode=self.settings.mode,
        )

    @staticmethod
    def _linear_regression_slope(
        history: list[tuple[float, float]]
    ) -> float:
        origin = history[0][0]
        times = [timestamp - origin for timestamp, _ in history]
        values = [y for _, y in history]
        mean_time = sum(times) / len(times)
        mean_y = sum(values) / len(values)
        denominator = sum((value - mean_time) ** 2 for value in times)
        if denominator == 0:
            return 0.0
        return sum(
            (timestamp - mean_time) * (y - mean_y)
            for timestamp, y in zip(times, values)
        ) / denominator

    @staticmethod
    def _consistency(
        history: list[tuple[float, float]], displacement: float
    ) -> float:
        if displacement == 0:
            return 0.0
        expected = 1 if displacement > 0 else -1
        deltas = [
            current_y - previous_y
            for (_, previous_y), (_, current_y) in zip(history, history[1:])
        ]
        moving = [delta for delta in deltas if delta != 0]
        if not moving:
            return 0.0
        agreeing = sum(
            1 for delta in moving if (1 if delta > 0 else -1) == expected
        )
        return agreeing / len(moving)

    def _unknown(
        self,
        reason: str,
        *,
        sample_count: int = 0,
        history: list[tuple[float, float]] | None = None,
        geometry_strategy: str | None = None,
    ) -> DirectionEvaluation:
        history = history or []
        duration = history[-1][0] - history[0][0] if len(history) > 1 else 0.0
        return DirectionEvaluation(
            direction="UNKNOWN",
            reason=reason,
            sample_count=sample_count,
            duration_seconds=round(duration, 6),
            start_y=round(history[0][1], 6) if history else None,
            end_y=round(history[-1][1], 6) if history else None,
            displacement=(
                round(history[-1][1] - history[0][1], 6)
                if len(history) > 1
                else None
            ),
            slope_per_second=None,
            consistency=None,
            config_version=self.settings.version,
            geometry_strategy=geometry_strategy,
            mode=self.settings.mode,
        )

    def _remember(
        self, plate: str, evaluation: DirectionEvaluation
    ) -> DirectionEvaluation:
        self._latest[plate] = evaluation
        return evaluation

    def latest(self, plate: str) -> DirectionEvaluation | None:
        return self._latest.get(plate)

    def clear(self, plate: str) -> None:
        self._history.pop(plate, None)
        self._latest.pop(plate, None)

    def sample_count(self, plate: str) -> int:
        return len(self._history.get(plate, []))
