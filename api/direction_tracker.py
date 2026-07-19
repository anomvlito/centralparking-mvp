"""Seguimiento temporal de patentes para clasificar entrada y salida.

Combina dos señales geométricas porque cuál de las dos sirve depende del
ángulo de la cámara respecto al flujo de autos:

  - posición (center_x/center_y): útil cuando el auto cruza el cuadro
    lateralmente — el centro de la patente se desplaza de un lado a otro.
  - tamaño (bbox normalizado de la patente): útil cuando el auto se mueve
    de frente hacia/desde la cámara — ahí la posición casi no cambia, pero
    el tamaño aparente crece o se achica de forma marcada.

Cada lectura evalúa ambas señales con la misma lógica estadística (ventana
temporal + mínimo de muestras + umbral de consistencia) y se usa la que
efectivamente muestre una tendencia clara. Si ninguna la muestra, o si el
ángulo de la cámara es intermedio y ninguna señal es lo bastante limpia,
el resultado es UNKNOWN.
"""

import os
import time
from collections import defaultdict
from typing import NamedTuple, Optional


class _Trend(NamedTuple):
    sign: int
    consistency: float


class DirectionTracker:
    WINDOW_SEC = float(os.environ.get("DIRECTION_WINDOW_SEC", "15"))
    MIN_SAMPLES = max(2, int(os.environ.get("DIRECTION_MIN_SAMPLES", "3")))
    MAX_HISTORY = max(MIN_SAMPLES, int(os.environ.get("DIRECTION_MAX_HISTORY", "8")))

    # Posición: rango típico 0-1 con desplazamientos grandes cuando el auto
    # cruza el cuadro.
    POSITION_MIN_DISPLACEMENT = float(os.environ.get("DIRECTION_MIN_DISPLACEMENT", "0.08"))
    POSITION_MIN_CONSISTENCY = float(os.environ.get("DIRECTION_MIN_CONSISTENCY", "0.67"))

    # Tamaño: el bbox de una patente ocupa una fracción mucho más chica del
    # cuadro, así que el umbral de desplazamiento es más bajo.
    SIZE_MIN_DISPLACEMENT = float(os.environ.get("DIRECTION_SIZE_MIN_DISPLACEMENT", "0.03"))
    SIZE_MIN_CONSISTENCY = float(os.environ.get("DIRECTION_SIZE_MIN_CONSISTENCY", "0.67"))

    def __init__(self, axis: str = None, entry_sign: str = None, clock=None):
        configured_axis = (axis or os.environ.get("DIRECTION_AXIS", "y")).lower()
        if configured_axis not in {"x", "y"}:
            raise ValueError("DIRECTION_AXIS debe ser 'x' o 'y'")
        configured_sign = (entry_sign or os.environ.get(
            "DIRECTION_ENTRY_SIGN", "positive"
        )).lower()
        if configured_sign not in {"positive", "negative"}:
            raise ValueError("DIRECTION_ENTRY_SIGN debe ser 'positive' o 'negative'")

        self.axis = configured_axis
        self.entry_sign = 1 if configured_sign == "positive" else -1
        self._clock = clock or time.monotonic
        # plate -> [(timestamp, position, size_or_None)]
        self._history = defaultdict(list)

    def record(self, plate: str, center_x: float, center_y: float,
               size: float = None) -> str:
        if not (0.0 <= center_x <= 1.0 and 0.0 <= center_y <= 1.0):
            return "UNKNOWN"

        now = self._clock()
        position = center_x if self.axis == "x" else center_y
        history = self._history[plate]
        history[:] = [
            (t, p, s) for t, p, s in history if now - t <= self.WINDOW_SEC
        ]
        history.append((now, position, size))
        if len(history) > self.MAX_HISTORY:
            del history[:-self.MAX_HISTORY]

        return self._classify(history)

    @staticmethod
    def _trend(values: list[float], min_displacement: float,
               min_consistency: float) -> Optional[_Trend]:
        if len(values) < 2:
            return None

        displacement = values[-1] - values[0]
        if abs(displacement) < min_displacement:
            return None

        deltas = [
            current - previous
            for previous, current in zip(values, values[1:])
            if current != previous
        ]
        if not deltas:
            return None

        movement_sign = 1 if displacement > 0 else -1
        consistency = sum(
            1 for delta in deltas if (1 if delta > 0 else -1) == movement_sign
        ) / len(deltas)
        if consistency < min_consistency:
            return None

        return _Trend(movement_sign, consistency)

    def _classify(self, history: list[tuple[float, float, Optional[float]]]) -> str:
        if len(history) < self.MIN_SAMPLES:
            return "UNKNOWN"

        positions = [position for _, position, _ in history]
        sizes = [size for _, _, size in history if size is not None]
        # El tamaño solo es comparable si todas las lecturas de la ventana lo
        # traen (si alguna estrategia sin geometría se coló, se descarta).
        if len(sizes) != len(history):
            sizes = []

        position_trend = self._trend(
            positions, self.POSITION_MIN_DISPLACEMENT, self.POSITION_MIN_CONSISTENCY
        )
        size_trend = self._trend(
            sizes, self.SIZE_MIN_DISPLACEMENT, self.SIZE_MIN_CONSISTENCY
        ) if sizes else None

        candidates = []
        if position_trend:
            direction = "APPROACHING" if position_trend.sign == self.entry_sign else "DEPARTING"
            candidates.append((position_trend.consistency, direction))
        if size_trend:
            # Tamaño creciendo = auto acercándose a la cámara = entrando,
            # sin importar el eje/signo configurado para la posición.
            direction = "APPROACHING" if size_trend.sign > 0 else "DEPARTING"
            candidates.append((size_trend.consistency, direction))

        if not candidates:
            return "UNKNOWN"

        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1]

    def clear(self, plate: str):
        self._history.pop(plate, None)

    def sample_count(self, plate: str) -> int:
        return len(self._history.get(plate, []))
