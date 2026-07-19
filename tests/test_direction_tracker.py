import unittest

from api.direction_tracker import DirectionTracker


class DirectionTrackerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.tracker = DirectionTracker(
            axis="y", entry_sign="positive", clock=lambda: self.now
        )

    def record(self, positions, sizes=None):
        result = "UNKNOWN"
        sizes = sizes or [None] * len(positions)
        for position, size in zip(positions, sizes):
            result = self.tracker.record("ABCD12", 0.5, position, size)
            self.now += 1
        return result

    def test_positive_consistent_movement_is_entry(self):
        self.assertEqual(self.record([0.10, 0.15, 0.22]), "APPROACHING")

    def test_negative_consistent_movement_is_exit(self):
        self.assertEqual(self.record([0.80, 0.74, 0.65]), "DEPARTING")

    def test_small_jitter_does_not_classify_direction(self):
        self.assertEqual(self.record([0.50, 0.52, 0.49, 0.51]), "UNKNOWN")

    def test_inconsistent_trajectory_is_not_classified(self):
        self.assertEqual(
            self.record([0.10, 0.25, 0.12, 0.30]),
            "UNKNOWN",
        )

    def test_axis_is_configurable(self):
        tracker = DirectionTracker(
            axis="x", entry_sign="negative", clock=lambda: self.now
        )
        result = "UNKNOWN"
        for position in [0.80, 0.72, 0.60]:
            result = tracker.record("EFGH34", position, 0.5)
            self.now += 1
        self.assertEqual(result, "APPROACHING")

    def test_growing_size_is_entry_even_without_lateral_movement(self):
        # Cámara casi de frente: la posición apenas se mueve (jitter < umbral)
        # pero el tamaño de la patente crece de forma consistente.
        result = self.record(
            positions=[0.50, 0.51, 0.49, 0.50],
            sizes=[0.03, 0.05, 0.07, 0.09],
        )
        self.assertEqual(result, "APPROACHING")

    def test_shrinking_size_is_exit_even_without_lateral_movement(self):
        result = self.record(
            positions=[0.50, 0.49, 0.51, 0.50],
            sizes=[0.09, 0.07, 0.05, 0.03],
        )
        self.assertEqual(result, "DEPARTING")

    def test_size_signal_ignored_when_incomplete_history(self):
        # Si alguna lectura no trae tamaño (p.ej. vino de una estrategia sin
        # geometría), no se usa el tamaño como señal para esa ventana.
        result = self.record(
            positions=[0.50, 0.51, 0.49, 0.50],
            sizes=[0.03, None, 0.07, 0.09],
        )
        self.assertEqual(result, "UNKNOWN")

    def test_position_wins_when_both_signals_present_and_agree(self):
        result = self.record(
            positions=[0.10, 0.15, 0.22],
            sizes=[0.03, 0.05, 0.07],
        )
        self.assertEqual(result, "APPROACHING")

    def test_stronger_signal_wins_when_signals_disagree(self):
        # Posición baja de forma mayormente consistente (3/4, DEPARTING) pero
        # el tamaño sube de forma perfectamente consistente (4/4, APPROACHING)
        # → gana la señal con mayor consistencia (tamaño).
        result = self.record(
            positions=[0.70, 0.65, 0.60, 0.55, 0.60],
            sizes=[0.03, 0.05, 0.07, 0.09, 0.11],
        )
        self.assertEqual(result, "APPROACHING")


if __name__ == "__main__":
    unittest.main()
