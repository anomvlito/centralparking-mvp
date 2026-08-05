import datetime
import os
import unittest

RUN_DB_TESTS = os.environ.get("RUN_DB_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(
    RUN_DB_TESTS,
    "requiere RUN_DB_INTEGRATION_TESTS=1 y DATABASE_URL apuntando a un "
    "Postgres real (mismo criterio que test_reconciliation_integration.py)",
)
class StagingPromoteLoggedAtTests(unittest.TestCase):
    """staging_promote_expired() debe preservar staging_detections.detected_at
    (la hora real en que se guardó la mejor foto) como detection_log.logged_at,
    en vez de dejar que log_to_db() use now() al momento de la promoción.

    Antes de este fix, toda detección quedaba con logged_at ~120-150s después
    de su hora real (el TTL de staging), y si el backend estuvo caído, con el
    backlog completo promovido de una sola vez al reiniciar, quedaba con
    logged_at igual a la hora de reinicio (hasta horas de diferencia)."""

    PLATE = "TESTLOG9"

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
                cur.execute(
                    "DELETE FROM detection_log WHERE plate = %s", (self.PLATE,)
                )

    def _insert_expired_staging_row(self, detected_at):
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO staging_detections
                        (plate, confidence, quality_score, combined_score,
                         sharpness, contrast_score, brightness_score,
                         ocr_clarity, strategy, status, expires_at,
                         image_path, detected_at)
                    VALUES (%s, 0.9, 0.9, 0.9, 0.5, 0.5, 0.5, 0.9,
                            'raw', 'pending', %s, NULL, %s)
                    RETURNING id
                    """,
                    (
                        self.PLATE,
                        detected_at + datetime.timedelta(seconds=1),
                        detected_at,
                    ),
                )
                return cur.fetchone()["id"]

    def test_promoted_detection_keeps_real_detection_time(self):
        from api.staging import staging_promote_expired

        # Simula una detección real ocurrida hace 3 horas, muy por fuera del
        # TTL normal de 2 minutos — como si el backend hubiera estado caído
        # y recién ahora (al reiniciar) corriera la promoción pendiente.
        real_time = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(hours=3)
        self._insert_expired_staging_row(real_time)

        promoted = staging_promote_expired()
        self.assertGreaterEqual(promoted, 1)

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT logged_at FROM detection_log WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                logged_at = cur.fetchone()["logged_at"]

        delta = abs((logged_at - real_time).total_seconds())
        self.assertLess(
            delta, 5,
            f"logged_at debería preservar la hora real de detección "
            f"({real_time}), no la hora de promoción; delta={delta}s",
        )

    def test_log_to_db_without_logged_at_still_defaults_to_now(self):
        from api.database import log_to_db

        before = datetime.datetime.now(datetime.timezone.utc)
        log_to_db(self.PLATE, "DETECTED", status="STAGING_AUTO")
        after = datetime.datetime.now(datetime.timezone.utc)

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT logged_at FROM detection_log WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                logged_at = cur.fetchone()["logged_at"]

        self.assertGreaterEqual(logged_at, before - datetime.timedelta(seconds=1))
        self.assertLessEqual(logged_at, after + datetime.timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
