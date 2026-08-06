import datetime
import os
import unittest

RUN_DB_TESTS = os.environ.get("RUN_DB_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(
    RUN_DB_TESTS,
    "requiere RUN_DB_INTEGRATION_TESTS=1 y DATABASE_URL apuntando a un "
    "Postgres real (mismo criterio que test_staging_logged_at.py)",
)
class StagingSubmitDetectedAtTests(unittest.TestCase):
    """staging_submit() debe aceptar un detected_at explícito (usado por el
    flujo de video, que lo deriva del mtime del .mp4 al llegar por FTP, en
    vez de dejar que la fila use now() al momento en que termina de
    procesarse — potencialmente varios minutos después de la captura real
    si la cola de video está ocupada)."""

    PLATE = "TESTVID8"

    def setUp(self):
        from api.database import _db

        self._db = _db

    def tearDown(self):
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM staging_detections WHERE plate = %s",
                    (self.PLATE,),
                )

    def _quality(self):
        return {
            "quality_score": 0.9, "combined_score": 0.9, "sharpness": 0.5,
            "contrast_score": 0.5, "brightness_score": 0.5, "ocr_clarity": 0.9,
        }

    def test_explicit_detected_at_is_preserved(self):
        from api.staging import staging_submit

        real_time = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(minutes=5)
        staging_submit(
            self.PLATE, 0.95, self._quality(), "raw", detected_at=real_time
        )

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT detected_at FROM staging_detections WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                detected_at = cur.fetchone()["detected_at"]

        delta = abs((detected_at - real_time).total_seconds())
        self.assertLess(
            delta, 5,
            f"detected_at debería preservar la hora real pasada "
            f"({real_time}), no now(); delta={delta}s",
        )

    def test_without_detected_at_still_defaults_to_now(self):
        from api.staging import staging_submit

        before = datetime.datetime.now(datetime.timezone.utc)
        staging_submit(self.PLATE, 0.95, self._quality(), "raw")
        after = datetime.datetime.now(datetime.timezone.utc)

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT detected_at FROM staging_detections WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                detected_at = cur.fetchone()["detected_at"]

        self.assertGreaterEqual(detected_at, before - datetime.timedelta(seconds=1))
        self.assertLessEqual(detected_at, after + datetime.timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
