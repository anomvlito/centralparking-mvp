import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://contract-test.invalid/db")

from api.schemas.parking import CarEntry
from api.services import parking


class ParkingServiceTests(unittest.TestCase):
    @patch.object(parking, "log_to_db")
    @patch.object(parking, "upsert_vehicle")
    @patch.object(parking, "now_cl")
    def test_entry_preserves_response_contract(
        self, now_cl, upsert_vehicle, log_to_db
    ):
        now_cl.return_value.timestamp.return_value = 1234.5
        response = parking.register_entry(
            CarEntry(
                plate="SYNTH01",
                isEvent=False,
                eventFee=None,
                imagePath=None,
            )
        )
        self.assertEqual(
            response,
            {
                "plate": "SYNTH01",
                "entryTime": 1234500.0,
                "isEvent": False,
                "eventFee": None,
            },
        )
        upsert_vehicle.assert_called_once_with(
            "SYNTH01",
            1234500.0,
            False,
            None,
            image_path=None,
        )

    @patch.object(parking, "vehicle_exists", return_value=False)
    def test_missing_exit_preserves_not_found_signal(self, _vehicle_exists):
        with self.assertRaisesRegex(LookupError, "Plate not in parking"):
            parking.register_exit("SYNTH02")


if __name__ == "__main__":
    unittest.main()
