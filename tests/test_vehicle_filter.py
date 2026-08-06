import unittest
from unittest.mock import patch

import numpy as np

from api.core.config import VehicleFilterSettings
from api import vehicle_detector


class VehicleFilterSettingsTests(unittest.TestCase):
    def test_defaults_are_disabled_and_shadow_mode(self):
        settings = VehicleFilterSettings.from_env({})
        self.assertFalse(settings.enabled)
        self.assertTrue(settings.shadow_mode)
        self.assertEqual(settings.mode, "disabled")

    def test_invalid_enabled_configuration_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "CONF_THRESH"):
            VehicleFilterSettings.from_env({
                "VEHICLE_FILTER_ENABLED": "true",
                "VEHICLE_FILTER_CONF_THRESH": "1.5",
            })

    def test_invalid_threshold_is_inert_while_disabled(self):
        settings = VehicleFilterSettings.from_env({
            "VEHICLE_FILTER_ENABLED": "false",
            "VEHICLE_FILTER_CONF_THRESH": "not-a-number",
        })
        self.assertEqual(settings, VehicleFilterSettings())

    def test_active_mode_requires_enabled_and_not_shadow(self):
        settings = VehicleFilterSettings(enabled=True, shadow_mode=False)
        self.assertEqual(settings.mode, "active")


class PassesVehicleFilterTests(unittest.TestCase):
    def setUp(self):
        self.img = np.zeros((10, 10, 3), dtype=np.uint8)

    def test_disabled_always_proceeds_without_scoring(self):
        with patch.object(
            vehicle_detector, "VEHICLE_FILTER_SETTINGS", VehicleFilterSettings()
        ), patch.object(vehicle_detector, "vehicle_score") as mock_score:
            result = vehicle_detector.passes_vehicle_filter(self.img, "image")
        self.assertTrue(result)
        mock_score.assert_not_called()

    def test_shadow_mode_proceeds_even_without_vehicle_but_audits(self):
        settings = VehicleFilterSettings(enabled=True, shadow_mode=True)
        with patch.object(
            vehicle_detector, "VEHICLE_FILTER_SETTINGS", settings
        ), patch.object(
            vehicle_detector, "vehicle_score", return_value=0.1
        ), patch.object(vehicle_detector, "log_audit_event") as mock_audit:
            result = vehicle_detector.passes_vehicle_filter(self.img, "video")
        self.assertTrue(result, "shadow_mode nunca debe bloquear el pipeline")
        mock_audit.assert_called_once()
        _, event_type, details = mock_audit.call_args[0]
        self.assertEqual(event_type, "VEHICLE_FILTER_EVALUATED")
        self.assertTrue(details["shadow_mode"])
        self.assertEqual(details["source"], "video")

    def test_active_mode_blocks_when_no_vehicle(self):
        settings = VehicleFilterSettings(enabled=True, shadow_mode=False)
        with patch.object(
            vehicle_detector, "VEHICLE_FILTER_SETTINGS", settings
        ), patch.object(
            vehicle_detector, "vehicle_score", return_value=0.1
        ), patch.object(vehicle_detector, "log_audit_event") as mock_audit:
            result = vehicle_detector.passes_vehicle_filter(self.img, "image")
        self.assertFalse(result)
        mock_audit.assert_called_once()

    def test_active_mode_proceeds_when_vehicle_present(self):
        settings = VehicleFilterSettings(
            enabled=True, shadow_mode=False, conf_threshold=0.35
        )
        with patch.object(
            vehicle_detector, "VEHICLE_FILTER_SETTINGS", settings
        ), patch.object(
            vehicle_detector, "vehicle_score", return_value=0.9
        ), patch.object(vehicle_detector, "log_audit_event") as mock_audit:
            result = vehicle_detector.passes_vehicle_filter(self.img, "image")
        self.assertTrue(result)
        mock_audit.assert_not_called()


class VehicleScoreFailOpenTests(unittest.TestCase):
    def test_unavailable_model_never_blocks(self):
        with patch.object(
            vehicle_detector, "HAS_VEHICLE_FILTER", False
        ), patch.object(vehicle_detector, "_session", None):
            score = vehicle_detector.vehicle_score(
                np.zeros((10, 10, 3), dtype=np.uint8)
            )
        self.assertEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
