import unittest
from unittest.mock import patch

from api.schemas.reconciliation import ReconcileStayRequest
from api.services import reconciliation


class ReconciliationServiceTests(unittest.TestCase):
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
