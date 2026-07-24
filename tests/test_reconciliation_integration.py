import datetime
import os
import unittest

RUN_DB_TESTS = os.environ.get("RUN_DB_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(
    RUN_DB_TESTS,
    "requiere RUN_DB_INTEGRATION_TESTS=1 y DATABASE_URL apuntando a un Postgres "
    "real (no hay entorno de test aislado; opt-in explícito a propósito, para "
    "no chocar con el DATABASE_URL dummy de test_openapi_contract.py ni correr "
    "contra una DB real sin que el desarrollador lo pida)",
)
class ReconciliationIntegrationTests(unittest.TestCase):
    """Ejercita reconcile_detection_events contra Postgres real.

    Los tests de tests/test_reconciliation_service.py mockean la capa de DB
    y no detectan errores de esquema (enums, longitud de columnas). Este test
    usa una patente sintética obvia y limpia todo lo que crea, incluso si
    una aserción falla.
    """

    PLATE = "TESTFX99"

    def setUp(self):
        from api.database import _db

        self._db = _db
        self.entry_id = None
        self.exit_id = None
        self.stay_id = None

    def tearDown(self):
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE detection_log SET linked_session_id = NULL "
                    "WHERE plate = %s",
                    (self.PLATE,),
                )
                cur.execute(
                    "DELETE FROM parking_sessions WHERE plate = %s",
                    (self.PLATE,),
                )
                cur.execute(
                    "DELETE FROM audit_log WHERE plate = %s", (self.PLATE,)
                )
                cur.execute(
                    "DELETE FROM detection_log WHERE plate = %s",
                    (self.PLATE,),
                )
                cur.execute(
                    "DELETE FROM vehicles WHERE plate = %s", (self.PLATE,)
                )

    def _insert_detection(self, logged_at):
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO detection_log
                        (plate, normalized_plate, action, status, confidence,
                         direction, match_status, source, logged_at)
                    VALUES (%s,%s,'DETECTED','TEST',0.9,'UNKNOWN',
                            'UNMATCHED','TEST',%s)
                    RETURNING id
                    """,
                    (self.PLATE, self.PLATE, logged_at),
                )
                return int(cur.fetchone()["id"])

    def test_manual_reconciliation_persists_valid_source_and_audit_event(self):
        from api.database import reconcile_detection_events

        now = datetime.datetime.now(datetime.timezone.utc)
        self.entry_id = self._insert_detection(now - datetime.timedelta(minutes=5))
        self.exit_id = self._insert_detection(now - datetime.timedelta(minutes=1))

        result = reconcile_detection_events(self.entry_id, self.exit_id, self.PLATE)
        self.stay_id = result["stay_id"]

        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT source FROM parking_sessions WHERE id = %s",
                    (self.stay_id,),
                )
                self.assertEqual(cur.fetchone()["source"], "manual")

                cur.execute(
                    "SELECT event_type FROM audit_log WHERE plate = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (self.PLATE,),
                )
                self.assertEqual(cur.fetchone()["event_type"], "STAY_RECONCILED")


if __name__ == "__main__":
    unittest.main()
