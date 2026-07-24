import os
import unittest
from unittest.mock import patch

from api.core.config import DirectionSettings
from api.direction_tracker import DirectionTracker


class DirectionSettingsTests(unittest.TestCase):
    def test_defaults_are_disabled_and_observation_only(self):
        settings = DirectionSettings.from_env({})
        self.assertFalse(settings.enabled)
        self.assertTrue(settings.observation_only)
        self.assertEqual(settings.mode, "disabled")

    def test_hash_changes_with_relevant_parameter(self):
        default = DirectionSettings()
        changed = DirectionSettings(min_displacement=0.12)
        self.assertNotEqual(default.version, changed.version)

    def test_invalid_enabled_configuration_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "MIN_SAMPLES"):
            DirectionSettings.from_env(
                {
                    "DIRECTION_ENABLED": "true",
                    "DIRECTION_MIN_SAMPLES": "2",
                }
            )

    def test_legacy_axis_and_size_variables_do_not_affect_settings(self):
        baseline = DirectionSettings.from_env({})
        with_legacy = DirectionSettings.from_env(
            {
                "DIRECTION_AXIS": "x",
                "DIRECTION_SIZE_MIN_DISPLACEMENT": "0.99",
            }
        )
        self.assertEqual(baseline, with_legacy)

    def test_invalid_thresholds_are_inert_while_disabled(self):
        settings = DirectionSettings.from_env(
            {
                "DIRECTION_ENABLED": "false",
                "DIRECTION_MIN_SAMPLES": "not-a-number",
                "DIRECTION_MIN_DISPLACEMENT": "invalid",
            }
        )
        self.assertEqual(settings, DirectionSettings())


class DirectionTrackerTests(unittest.TestCase):
    def setUp(self):
        self.settings = DirectionSettings(
            enabled=True,
            observation_only=True,
            window_seconds=15,
            min_samples=3,
            max_history=8,
            min_displacement=0.08,
            min_slope_per_second=0.01,
            min_consistency=0.67,
            entry_sign="positive",
        )
        self.tracker = DirectionTracker(self.settings)

    def evaluate(self, positions, times=None):
        times = times or list(range(len(positions)))
        evaluation = None
        for timestamp, position in zip(times, positions):
            evaluation = self.tracker.evaluate(
                "SYNTH01",
                position,
                timestamp,
                geometry_strategy="raw",
            )
        return evaluation

    def test_positive_regular_movement_is_entry(self):
        result = self.evaluate([0.10, 0.15, 0.22])
        self.assertEqual(result.direction, "APPROACHING")
        self.assertIsNone(result.reason)

    def test_negative_regular_movement_is_exit(self):
        result = self.evaluate([0.80, 0.74, 0.65])
        self.assertEqual(result.direction, "DEPARTING")

    def test_entry_sign_can_be_inverted(self):
        tracker = DirectionTracker(
            DirectionSettings(
                enabled=True,
                observation_only=True,
                entry_sign="negative",
            )
        )
        direction = "UNKNOWN"
        for timestamp, y in enumerate([0.80, 0.74, 0.65]):
            direction = tracker.record("SYNTH02", y, timestamp)
        self.assertEqual(direction, "APPROACHING")

    def test_zero_one_and_two_samples_are_unknown(self):
        self.assertEqual(
            self.tracker.evaluate("SYNTH01", 0.1, 0).reason,
            "insufficient_samples",
        )
        self.assertEqual(
            self.tracker.evaluate("SYNTH01", 0.2, 1).reason,
            "insufficient_samples",
        )

    def test_small_displacement_is_unknown(self):
        result = self.evaluate([0.50, 0.52, 0.54])
        self.assertEqual(result.direction, "UNKNOWN")
        self.assertEqual(result.reason, "insufficient_displacement")

    def test_large_but_inconsistent_movement_is_unknown(self):
        result = self.evaluate([0.10, 0.25, 0.12, 0.30])
        self.assertEqual(result.direction, "UNKNOWN")
        self.assertEqual(result.reason, "insufficient_consistency")

    def test_irregular_timestamps_use_slope_per_second(self):
        result = self.evaluate([0.10, 0.15, 0.30], [0.0, 0.5, 3.0])
        self.assertEqual(result.direction, "APPROACHING")
        self.assertGreater(result.slope_per_second, 0)

    def test_duplicate_or_unordered_timestamp_is_rejected(self):
        self.tracker.evaluate("SYNTH01", 0.1, 1)
        result = self.tracker.evaluate("SYNTH01", 0.2, 1)
        self.assertEqual(result.reason, "invalid_timestamp")
        self.assertEqual(self.tracker.sample_count("SYNTH01"), 1)

    def test_coordinate_outside_normalized_range_is_rejected(self):
        result = self.tracker.evaluate("SYNTH01", 1.01, 0)
        self.assertEqual(result.reason, "invalid_coordinate")
        self.assertEqual(self.tracker.sample_count("SYNTH01"), 0)

    def test_history_expires_by_window(self):
        self.tracker.evaluate("SYNTH01", 0.1, 0)
        result = self.tracker.evaluate("SYNTH01", 0.3, 16)
        self.assertEqual(result.reason, "insufficient_samples")
        self.assertEqual(result.sample_count, 1)

    def test_history_is_bounded(self):
        for timestamp in range(12):
            self.tracker.evaluate("SYNTH01", min(0.05 * timestamp, 0.95), timestamp)
        self.assertEqual(self.tracker.sample_count("SYNTH01"), 8)

    def test_evaluation_contains_auditable_evidence_without_plate(self):
        result = self.evaluate([0.10, 0.15, 0.22])
        payload = result.to_dict()
        self.assertNotIn("plate", payload)
        self.assertEqual(payload["geometry_strategy"], "raw")
        self.assertEqual(payload["mode"], "observation_only")
        self.assertTrue(payload["config_version"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
