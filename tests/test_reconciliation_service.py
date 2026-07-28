import datetime
import unittest
from unittest.mock import patch

from api.schemas.reconciliation import ReconcileStayRequest
from api.database import (
    _add_operational_day_overlap,
    _operational_day_bounds,
    _stay_from_row,
)
from api.services import reconciliation


class ReconciliationServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
