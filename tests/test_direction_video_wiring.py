import datetime
import os
import unittest

from api.core.config import DirectionSettings
from api.direction_tracker import DirectionTracker
from api.services.direction import DirectionService


class VideoReplayPatternTests(unittest.TestCase):
    """Verifica el patrón usado en video_processor.py (HU-010): registrar
    todas las muestras intermedias de un cluster sin auditar (tracker.record)
    y disparar observe() solo con la última — reflejando la trayectoria
    completa en exactamente un evento de auditoría por vehículo, no uno por
    frame (HU-009: "evitar registrar cada frame sin control")."""

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
        self.audit_calls = []
        self.service = DirectionService(
            settings=self.settings,
            tracker=self.tracker,
            audit_sink=lambda plate, event, details: self.audit_calls.append(
                (plate, event, details)
            ),
        )

    def _replay(self, plate, samples, **observe_kwargs):
        for timestamp, center_y, geometry in samples[:-1]:
            self.tracker.record(
                plate, center_y, timestamp, geometry_strategy=geometry
            )
        last_timestamp, last_y, last_geometry = samples[-1]
        return self.service.observe(
            plate=plate,
            center_y=last_y,
            timestamp=last_timestamp,
            geometry_strategy=last_geometry,
            **observe_kwargs,
        )

    def test_replay_produces_one_audit_event_reflecting_full_trajectory(self):
        samples = [
            (0.0, 0.10, "raw"),
            (1.0, 0.15, "raw"),
            (2.0, 0.22, "raw"),
        ]
        result = self._replay(
            "SYNTHVID1", samples, source="video", ocr_confidence=0.9
        )

        self.assertEqual(result.direction, "APPROACHING")
        self.assertEqual(result.sample_count, 3)
        self.assertEqual(len(self.audit_calls), 1)
        plate, event_type, details = self.audit_calls[0]
        self.assertEqual(plate, "SYNTHVID1")
        self.assertEqual(event_type, "DIRECTION_EVALUATED")
        self.assertEqual(details["sample_count"], 3)
        self.assertEqual(details["source"], "video")

    def test_replay_with_single_sample_matches_photo_behavior(self):
        result = self._replay(
            "SYNTHVID2", [(0.0, 0.10, "raw")], source="video", ocr_confidence=0.9
        )
        self.assertEqual(result.reason, "insufficient_samples")
        self.assertEqual(len(self.audit_calls), 1)

    def test_disabled_settings_skip_replay_entirely(self):
        disabled = DirectionSettings()
        self.assertFalse(disabled.enabled)
        # video_processor.py chequea direction_service.settings.enabled antes
        # de llamar a record()/observe(); acá se documenta el contrato que
        # ese guard depende de.


RUN_DB_TESTS = os.environ.get("RUN_DB_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(
    RUN_DB_TESTS,
    "requiere RUN_DB_INTEGRATION_TESTS=1 y DATABASE_URL apuntando a un "
    "Postgres real (mismo criterio que test_reconciliation_integration.py)",
)
class StagingPromoteDirectionWiringTests(unittest.TestCase):
    """HU-010 parte B: staging_promote_expired() debe propagar la última
    evaluación conocida de direction_service.tracker hacia
    detection_log.direction, en vez del default 'UNKNOWN' de log_to_db."""

    PLATE = "TESTVID9"

    def setUp(self):
        from api.database import _db
        from api.services.direction import direction_service

        self._db = _db
        self.direction_service = direction_service
        self.staging_id = None

    def tearDown(self):
        self.direction_service.tracker.clear(self.PLATE)
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM staging_detections WHERE plate = %s",
                    (self.PLATE,),
                )
                cur.execute(
                    "DELETE FROM detection_log WHERE plate = %s", (self.PLATE,)
                )

    def test_promoted_detection_uses_latest_known_direction(self):
        for timestamp, center_y in [(0.0, 0.10), (1.0, 0.15), (2.0, 0.22)]:
            self.direction_service.tracker.record(
                self.PLATE, center_y, timestamp, geometry_strategy="raw"
            )
        latest = self.direction_service.tracker.latest(self.PLATE)
        self.assertEqual(latest.direction, "APPROACHING")

        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=1
        )
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO staging_detections
                        (plate, confidence, quality_score, combined_score,
                         sharpness, contrast_score, brightness_score,
                         ocr_clarity, strategy, status, expires_at, image_path)
                    VALUES (%s, 0.9, 0.9, 0.9, 0.5, 0.5, 0.5, 0.9,
                            'raw', 'pending', %s, NULL)
                    RETURNING id
                    """,
                    (self.PLATE, past),
                )
                self.staging_id = cur.fetchone()["id"]

        from api.staging import staging_promote_expired

        promoted = staging_promote_expired()
        self.assertGreaterEqual(promoted, 1)

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT direction FROM detection_log WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                row = cur.fetchone()
        self.assertEqual(row["direction"], "APPROACHING")

    def test_promoted_detection_without_prior_evaluation_stays_unknown(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=1
        )
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO staging_detections
                        (plate, confidence, quality_score, combined_score,
                         sharpness, contrast_score, brightness_score,
                         ocr_clarity, strategy, status, expires_at, image_path)
                    VALUES (%s, 0.9, 0.9, 0.9, 0.5, 0.5, 0.5, 0.9,
                            'raw', 'pending', %s, NULL)
                    RETURNING id
                    """,
                    (self.PLATE, past),
                )
                self.staging_id = cur.fetchone()["id"]

        from api.staging import staging_promote_expired

        staging_promote_expired()

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT direction FROM detection_log WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                row = cur.fetchone()
        self.assertEqual(row["direction"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
