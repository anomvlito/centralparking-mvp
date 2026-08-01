import datetime
import unittest
from unittest.mock import patch

from api.schemas.reconciliation import ReconcileStayRequest
from api.database import (
    _add_operational_day_overlap,
    _operational_day_bounds,
    _stay_from_row,
    auto_reconcile_exact_matches,
    build_stay_proposals,
    get_stay_proposals,
    is_duplicate_duration,
    is_valid_plate,
    normalize_plate,
    plate_matches_exclusion,
    reconcile_detection_events,
)
from api.services import reconciliation


class ReconciliationServiceTests(unittest.TestCase):
    def _event(self, event_id, plate, at, confidence=0.9, direction="UNKNOWN"):
        return {
            "detection_id": event_id,
            "detected_plate": plate,
            "normalized_plate": plate,
            "detected_at": at,
            "confidence": confidence,
            "image_url": None,
            "direction": direction,
            "match_status": "UNMATCHED",
            "stay_id": None,
            "source": "TEST",
        }

    def test_plate_format_is_exactly_six_after_normalization(self):
        self.assertEqual(normalize_plate("ab-cd 12"), "ABCD12")
        self.assertTrue(is_valid_plate("ab-cd 12"))
        self.assertFalse(is_valid_plate("ABC12"))
        self.assertFalse(is_valid_plate("ABCDEFG"))

    def test_exclusion_matches_exact_and_one_ocr_character_only(self):
        self.assertTrue(plate_matches_exclusion("ABC123", "ABC123", 1))
        self.assertTrue(plate_matches_exclusion("ABC128", "ABC123", 1))
        self.assertFalse(plate_matches_exclusion("ABC189", "ABC123", 1))

    def test_duplicate_duration_covers_zero_and_one_displayed_minute(self):
        entry = datetime.datetime(2026, 7, 28, 10, 0)
        self.assertTrue(
            is_duplicate_duration(entry, entry + datetime.timedelta(seconds=59))
        )
        self.assertTrue(
            is_duplicate_duration(entry, entry + datetime.timedelta(seconds=119))
        )
        self.assertFalse(
            is_duplicate_duration(entry, entry + datetime.timedelta(minutes=2))
        )

    def test_exact_proposal_is_read_only_pair(self):
        events = [
            self._event(1, "ABC123", "2026-07-28T08:00:00-04:00"),
            self._event(2, "ABC123", "2026-07-28T10:00:00-04:00"),
        ]
        proposals = build_stay_proposals(events)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["match_type"], "EXACT")
        self.assertEqual(proposals[0]["duration_minutes"], 120)

    def test_fuzzy_proposal_requires_distance_one_and_window(self):
        events = [
            self._event(1, "ABC123", "2026-07-28T08:00:00-04:00"),
            self._event(2, "ABC128", "2026-07-28T10:00:00-04:00"),
            self._event(3, "ZZZ999", "2026-07-30T12:00:00-04:00"),
        ]
        proposals = build_stay_proposals(events)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["match_type"], "FUZZY")
        self.assertEqual(proposals[0]["distance"], 1)

    @patch("api.database.get_detection_events")
    def test_one_minute_proposals_are_not_returned_to_dashboard(self, get_events):
        get_events.side_effect = [[
            self._event(1, "ABC123", "2026-07-28T10:00:00-04:00"),
            self._event(2, "ABC128", "2026-07-28T10:01:59-04:00"),
        ], []]

        self.assertEqual(get_stay_proposals("2026-07-28"), [])

    @patch("api.database.get_stay_proposals")
    @patch("api.database.reconcile_detection_events")
    @patch("api.database.consolidate_short_entry_duplicates")
    def test_auto_reconciliation_discards_one_minute_fuzzy_proposal(
        self, consolidate, reconcile, get_proposals
    ):
        consolidate.return_value = 0
        get_proposals.return_value = [{
            "entry": {"detection_id": 1},
            "exit": {"detection_id": 2},
            "resolved_plate": "ABC123",
            "match_type": "FUZZY",
            "duration_minutes": 1,
        }]
        reconcile.return_value = {"status": "DUPLICATE"}

        result = auto_reconcile_exact_matches("2026-07-28")

        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["entry_duplicates"], 0)
        reconcile.assert_called_once_with(1, 2, "ABC123", match_type="FUZZY")
        get_proposals.assert_called_once_with(
            date="2026-07-28", limit=200, include_duplicate_duration=True
        )

    def test_reconciliation_rejects_non_six_character_plate_before_db(self):
        with self.assertRaisesRegex(ValueError, "exactamente 6"):
            reconcile_detection_events(1, 2, "ABC12")

    def test_operational_day_uses_chile_boundaries(self):
        day_start, day_end = _operational_day_bounds("2026-07-28")

        self.assertEqual(day_start.isoformat(), "2026-07-28T00:00:00-04:00")
        self.assertEqual(day_end.isoformat(), "2026-07-29T00:00:00-04:00")

    def test_operational_day_rejects_invalid_date(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            _operational_day_bounds("28-07-2026")

    def test_stay_date_filter_uses_interval_overlap(self):
        conditions = []
        params = []

        _add_operational_day_overlap(conditions, params, "2026-07-28")

        self.assertEqual(
            conditions,
            [
                "COALESCE(entry_time, exit_time) < %s",
                "COALESCE(exit_time, entry_time, 'infinity'::timestamptz) >= %s",
            ],
        )
        self.assertEqual(params[0].isoformat(), "2026-07-29T00:00:00-04:00")
        self.assertEqual(params[1].isoformat(), "2026-07-28T00:00:00-04:00")

    def test_technical_close_is_not_reported_as_twenty_hour_stay(self):
        entry = datetime.datetime(
            2026, 7, 23, 10, 0, tzinfo=datetime.timezone.utc
        )
        row = {
            "id": 9,
            "plate": "TEST12",
            "entry_time": entry,
            "exit_time": entry + datetime.timedelta(hours=20),
            "session_status": "AUTO_CLOSED",
            "entry_detection_id": None,
            "exit_detection_id": None,
            "match_type": "UNRESOLVED",
            "match_confidence": None,
            "entry_image_path": None,
            "exit_image_path": None,
            "fee": 0,
        }

        stay = _stay_from_row(row)

        self.assertEqual(stay["status"], "NEEDS_REVIEW")
        self.assertIsNone(stay["duration_minutes"])

    @patch.object(reconciliation, "get_parking_stays")
    def test_completed_stays_are_delegated_without_using_cars(self, get_stays):
        get_stays.return_value = [{"stay_id": 7, "duration_minutes": 42}]

        result = reconciliation.list_stays(
            limit=25, status="COMPLETED", date="2026-07-24", plate="TEST12"
        )

        self.assertEqual(result[0]["duration_minutes"], 42)
        get_stays.assert_called_once_with(
            limit=25,
            status="COMPLETED",
            date="2026-07-24",
            plate="TEST12",
        )

    @patch.object(reconciliation, "reconcile_detection_events")
    def test_manual_reconciliation_preserves_distinct_detection_ids(self, reconcile):
        reconcile.return_value = {
            "stay_id": 8,
            "entry_detection_id": 10,
            "exit_detection_id": 11,
            "match_type": "MANUAL",
        }
        request = ReconcileStayRequest(
            entry_detection_id=10,
            exit_detection_id=11,
            resolved_plate="TEST12",
        )

        result = reconciliation.reconcile_stay(request)

        self.assertEqual(result["match_type"], "MANUAL")
        reconcile.assert_called_once_with(
            entry_detection_id=10,
            exit_detection_id=11,
            resolved_plate="TEST12",
        )

    @patch.object(reconciliation, "dismiss_detection_event")
    def test_dismiss_is_non_destructive_repository_action(self, dismiss):
        dismiss.return_value = {
            "detection_id": 12,
            "match_status": "DISMISSED",
        }

        result = reconciliation.dismiss_detection(12)

        self.assertEqual(result["match_status"], "DISMISSED")
        dismiss.assert_called_once_with(12)

    @patch.object(reconciliation, "set_detection_direction")
    def test_set_direction_delegates_to_repository(self, set_direction):
        set_direction.return_value = {
            "detection_id": 13,
            "direction": "APPROACHING",
        }

        result = reconciliation.set_direction(13, "APPROACHING")

        self.assertEqual(result["direction"], "APPROACHING")
        set_direction.assert_called_once_with(13, "APPROACHING")


if __name__ == "__main__":
    unittest.main()
