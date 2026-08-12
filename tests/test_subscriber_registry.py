import datetime
import os
import unittest
from unittest.mock import MagicMock, patch

from api.database import find_plate_exclusion_match, get_subscriber_stay_proposals

# api.detect debe importarse antes que api.ftp_handler: detect.py hace
# `from .ftp_handler import router`, así que si algo importa
# api.ftp_handler primero (directo), Python encuentra ese módulo a medio
# inicializar cuando ftp_handler.py a su vez hace `from api.detect import
# ...` (mismo orden de carga que usa el entrypoint real, uvicorn
# api.detect:app).
import api.detect  # noqa: F401
from api.ftp_handler import OWNER_EXCLUDED_PLATE, _handle_auto_detection

RUN_DB_TESTS = os.environ.get("RUN_DB_INTEGRATION_TESTS") == "1"


class FakeCursor:
    """Cursor mínimo para probar find_plate_exclusion_match sin Postgres real."""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        pass

    def fetchall(self):
        return self._rows


class FindPlateExclusionMatchTests(unittest.TestCase):
    def test_returns_none_without_exclusions(self):
        cur = FakeCursor([])
        self.assertIsNone(find_plate_exclusion_match(cur, "ABC123"))

    def test_returns_matching_row_within_distance(self):
        cur = FakeCursor([
            {"normalized_plate": "ABC123", "max_distance": 1},
        ])
        match = find_plate_exclusion_match(cur, "ABC128")
        self.assertEqual(match["normalized_plate"], "ABC123")

    def test_returns_none_outside_distance(self):
        cur = FakeCursor([
            {"normalized_plate": "ABC123", "max_distance": 0},
        ])
        self.assertIsNone(find_plate_exclusion_match(cur, "ABC128"))


class SubscriberStayProposalsTests(unittest.TestCase):
    @patch("api.database.get_detection_events")
    def test_requests_subscriber_events_only(self, get_events):
        get_events.return_value = []

        get_subscriber_stay_proposals("2026-08-12")

        get_events.assert_called_once_with(
            limit=500, match_status="UNMATCHED", date="2026-08-12",
            subscribers=True,
        )


class HandleAutoDetectionSubscriberTests(unittest.TestCase):
    """HU-014: CYLF87 (dueño) se sigue descartando por completo; cualquier
    otro match contra plate_exclusions pasa a registrarse marcado como
    abonado, en vez de descartarse sin rastro."""

    def setUp(self):
        self.find_similar_patch = patch(
            "api.ftp_handler.find_similar_active_session", return_value=None
        )
        self.find_similar_patch.start()
        self.addCleanup(self.find_similar_patch.stop)

        self.direction_patch = patch("api.ftp_handler.direction_service")
        mock_direction = self.direction_patch.start()
        mock_direction.observe.return_value = None
        self.addCleanup(self.direction_patch.stop)

        self.staging_patch = patch("api.ftp_handler.staging_submit")
        self.staging_submit = self.staging_patch.start()
        self.staging_submit.return_value = {
            "status": "pending", "action": "first_in_window",
            "combined_score": 0.9, "image_path": None,
        }
        self.addCleanup(self.staging_patch.stop)

    @patch("api.ftp_handler.get_plate_exclusion_match")
    def test_owner_plate_is_fully_discarded(self, get_match):
        get_match.return_value = {
            "normalized_plate": OWNER_EXCLUDED_PLATE, "max_distance": 1,
        }

        result = _handle_auto_detection(
            OWNER_EXCLUDED_PLATE, "image", 0.99, "raw"
        )

        self.assertEqual(result["action"], "IGNORED_MONTHLY")
        self.assertFalse(result["registered"])
        self.staging_submit.assert_not_called()

    @patch("api.ftp_handler.get_plate_exclusion_match")
    def test_other_exclusion_is_registered_as_subscriber(self, get_match):
        get_match.return_value = {
            "normalized_plate": "ABC123", "max_distance": 1,
        }

        result = _handle_auto_detection("ABC128", "image", 0.95, "raw")

        self.assertEqual(result["action"], "STAGED")
        self.staging_submit.assert_called_once()
        _, kwargs = self.staging_submit.call_args
        self.assertTrue(kwargs["is_subscriber"])
        self.assertEqual(kwargs["subscriber_plate"], "ABC123")

    @patch("api.ftp_handler.get_plate_exclusion_match")
    def test_regular_plate_is_not_marked_as_subscriber(self, get_match):
        get_match.return_value = None

        result = _handle_auto_detection("ZZZ999", "image", 0.95, "raw")

        self.assertEqual(result["action"], "STAGED")
        self.staging_submit.assert_called_once()
        _, kwargs = self.staging_submit.call_args
        self.assertFalse(kwargs["is_subscriber"])
        self.assertIsNone(kwargs["subscriber_plate"])


@unittest.skipUnless(
    RUN_DB_TESTS,
    "requiere RUN_DB_INTEGRATION_TESTS=1 y DATABASE_URL apuntando a un "
    "Postgres real (mismo criterio que test_staging_logged_at.py)",
)
class SubscriberPipelineIntegrationTests(unittest.TestCase):
    """Ejercita staging_promote_expired()/log_to_db() reales para confirmar
    que un avistamiento de abonado queda UNMATCHED (no DISMISSED) y marcado,
    mientras que el chequeo automático de exclusión sigue intacto para
    llamadores que no pasan is_subscriber (ver test_log_to_db_without_
    subscriber_flag_still_dismisses_excluded_plate)."""

    PLATE = "TESTSUB"
    EXCLUDED_PLATE = "TSTSUB"

    def setUp(self):
        from api.database import _db

        self._db = _db
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO plate_exclusions
                        (normalized_plate, max_distance, active, created_by)
                    VALUES (%s, 0, true, 'test_subscriber_registry')
                    ON CONFLICT (normalized_plate) DO UPDATE
                    SET active = true
                    """,
                    (self.EXCLUDED_PLATE,),
                )

    def tearDown(self):
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM staging_detections WHERE plate = %s",
                    (self.PLATE,),
                )
                cur.execute(
                    "DELETE FROM detection_log WHERE plate = %s", (self.PLATE,)
                )
                cur.execute(
                    "DELETE FROM plate_exclusions WHERE normalized_plate = %s",
                    (self.EXCLUDED_PLATE,),
                )

    def test_promoted_subscriber_detection_is_unmatched_not_dismissed(self):
        from api.staging import staging_promote_expired

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO staging_detections
                        (plate, confidence, quality_score, combined_score,
                         sharpness, contrast_score, brightness_score,
                         ocr_clarity, strategy, status, expires_at,
                         image_path, detected_at, is_subscriber,
                         subscriber_plate)
                    VALUES (%s, 0.9, 0.9, 0.9, 0.5, 0.5, 0.5, 0.9,
                            'raw', 'pending', now() - INTERVAL '1 minute',
                            NULL, now(), true, %s)
                    """,
                    (self.PLATE, self.EXCLUDED_PLATE),
                )

        promoted = staging_promote_expired()
        self.assertGreaterEqual(promoted, 1)

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT match_status, is_subscriber, subscriber_plate "
                    "FROM detection_log WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                row = cur.fetchone()

        self.assertEqual(row["match_status"], "UNMATCHED")
        self.assertTrue(row["is_subscriber"])
        self.assertEqual(row["subscriber_plate"], self.EXCLUDED_PLATE)

    def test_log_to_db_without_subscriber_flag_still_dismisses_excluded_plate(self):
        from api.database import log_to_db

        log_to_db(self.EXCLUDED_PLATE, "ENTRY")

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT match_status FROM detection_log "
                    "WHERE plate = %s ORDER BY id DESC LIMIT 1",
                    (self.EXCLUDED_PLATE,),
                )
                row = cur.fetchone()

        self.assertEqual(row["match_status"], "DISMISSED")

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM detection_log WHERE plate = %s",
                    (self.EXCLUDED_PLATE,),
                )


if __name__ == "__main__":
    unittest.main()
