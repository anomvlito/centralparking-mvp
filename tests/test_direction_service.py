import unittest

from api.core.config import DirectionSettings
from api.direction_tracker import DirectionTracker
from api.services.direction import DirectionService


class DirectionServiceTests(unittest.TestCase):
    def test_disabled_mode_preserves_pipeline_and_does_not_audit(self):
        events = []
        service = DirectionService(
            settings=DirectionSettings(),
            audit_sink=lambda *args: events.append(args),
        )
        result = service.observe(plate="SYNTH01", center_y=0.25)
        self.assertIsNone(result)
        self.assertEqual(events, [])

    def test_observation_mode_audits_without_effect(self):
        events = []
        settings = DirectionSettings(enabled=True, observation_only=True)
        service = DirectionService(
            settings=settings,
            tracker=DirectionTracker(settings),
            audit_sink=lambda *args: events.append(args),
        )
        for timestamp, y in enumerate([0.10, 0.15, 0.22]):
            result = service.observe(
                plate="SYNTH01",
                center_y=y,
                timestamp=timestamp,
                geometry_strategy="raw",
                source="image",
                ocr_confidence=0.91,
            )

        self.assertEqual(result.direction, "APPROACHING")
        self.assertEqual(len(events), 3)
        plate, event_type, details = events[-1]
        self.assertEqual(plate, "SYNTH01")
        self.assertEqual(event_type, "DIRECTION_EVALUATED")
        self.assertEqual(details["effect"], "none")
        self.assertEqual(details["mode"], "observation_only")

    def test_audit_failure_does_not_fail_primary_observation(self):
        settings = DirectionSettings(enabled=True, observation_only=True)
        service = DirectionService(
            settings=settings,
            audit_sink=lambda *_: (_ for _ in ()).throw(RuntimeError("sink")),
        )
        result = service.observe(
            plate="SYNTH01",
            center_y=0.2,
            timestamp=0,
        )
        self.assertEqual(result.direction, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
