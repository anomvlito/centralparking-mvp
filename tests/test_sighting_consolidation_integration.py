import datetime
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

RUN_DB_TESTS = os.environ.get("RUN_DB_INTEGRATION_TESTS") == "1"


class _NoCommitConnection:
    """Envuelve una conexión real de Postgres para que ``commit()`` nunca
    persista nada. ``consolidate_fuzzy_sightings`` escanea TODO el día (no
    IDs sintéticos puntuales, a diferencia del resto de
    test_reconciliation_integration.py), así que probar el modo activo
    contra la base real sin esto puede — y una vez lo hizo, durante el
    desarrollo de este mismo feature, con el diseño anterior — marcar
    avistamientos reales de producción como DISMISSED por error. Todo lo
    que la función bajo prueba escriba se revierte en tearDown() con un
    único rollback real, pase o falle el test.
    """

    def __init__(self, real_conn):
        self._real = real_conn

    def cursor(self, *args, **kwargs):
        return self._real.cursor(*args, **kwargs)

    def commit(self):
        pass

    def rollback(self):
        self._real.rollback()

    def close(self):
        pass


@unittest.skipUnless(
    RUN_DB_TESTS,
    "requiere RUN_DB_INTEGRATION_TESTS=1 y DATABASE_URL apuntando a un Postgres "
    "real (no hay entorno de test aislado; opt-in explícito a propósito, para "
    "no chocar con el DATABASE_URL dummy de test_openapi_contract.py ni correr "
    "contra una DB real sin que el desarrollador lo pida)",
)
class SightingConsolidationIntegrationTests(unittest.TestCase):
    """Ejercita consolidate_fuzzy_sightings contra Postgres real, dentro de
    una única transacción que siempre se revierte (ver _NoCommitConnection)
    — nunca persiste nada, ni siquiera si una aserción falla.
    """

    def setUp(self):
        import psycopg2
        import psycopg2.extras

        from api.database import DATABASE_URL

        self._real_conn = psycopg2.connect(
            DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor
        )
        self._wrapped_conn = _NoCommitConnection(self._real_conn)

        @contextmanager
        def _fake_db():
            yield self._wrapped_conn

        self._db_patcher = patch("api.database._db", _fake_db)
        self._db_patcher.start()

    def tearDown(self):
        self._db_patcher.stop()
        self._real_conn.rollback()
        self._real_conn.close()

    def _insert_staging(self, plate, confidence, detected_at):
        with self._real_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO staging_detections
                    (plate, confidence, quality_score, combined_score,
                     status, detected_at, expires_at)
                VALUES (%s,%s,%s,%s,'approved',%s,%s)
            """, (
                plate, confidence, confidence, confidence, detected_at,
                detected_at + datetime.timedelta(minutes=2),
            ))

    def _insert_promoted_detection(self, plate, logged_at, confidence):
        with self._real_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO detection_log
                    (plate, normalized_plate, action, status, confidence,
                     direction, match_status, source, logged_at, image_path)
                VALUES (%s,%s,'DETECTED','STAGING_AUTO',%s,'UNKNOWN',
                        'UNMATCHED','TEST',%s,'historico/test.jpg')
                RETURNING id
            """, (plate, plate, confidence, logged_at))
            return int(cur.fetchone()["id"])

    def _match_status(self, detection_id):
        with self._real_conn.cursor() as cur:
            cur.execute(
                "SELECT match_status, plate, image_path FROM detection_log WHERE id = %s",
                (detection_id,),
            )
            return cur.fetchone()

    def _today_cl(self):
        cl = datetime.timezone(datetime.timedelta(hours=-4))
        return datetime.datetime.now(cl).date().isoformat()

    def _seed_winner_and_loser(self, now):
        # Ganadora: 3 lecturas crudas de alta confianza (mismo patrón que el
        # caso real 2026-08-10) -> gana por cantidad, no por confianza pico.
        self._insert_staging("TSX123", 0.9989, now)
        self._insert_staging("TSX123", 0.9868, now + datetime.timedelta(seconds=20))
        self._insert_staging("TSX123", 0.9999, now + datetime.timedelta(seconds=30))
        # Perdedora: una sola lectura, pero con confianza pico más alta que
        # cualquier lectura individual de la ganadora.
        self._insert_staging("TSX128", 0.9991, now + datetime.timedelta(seconds=15))

        winner_id = self._insert_promoted_detection("TSX123", now, 0.9989)
        loser_id = self._insert_promoted_detection(
            "TSX128", now + datetime.timedelta(seconds=15), 0.9991
        )
        return winner_id, loser_id

    def test_shadow_mode_audits_without_dismissing(self):
        from api.core.config import SightingConsolidationSettings
        from api.database import consolidate_fuzzy_sightings

        now = datetime.datetime.now(datetime.timezone.utc)
        winner_id, loser_id = self._seed_winner_and_loser(now)

        settings = SightingConsolidationSettings(
            enabled=True, shadow_mode=True, max_distance=1,
            window_seconds=90, min_confidence=0.90,
        )
        with patch("api.database.SIGHTING_CONSOLIDATION_SETTINGS", settings):
            result = consolidate_fuzzy_sightings(self._today_cl())

        # No se asume groups_found exacto: corre contra Postgres real (no
        # hay entorno de test aislado), puede haber tráfico real del día.
        # dismissed sí debe ser exactamente 0: shadow_mode nunca dismissea.
        self.assertGreaterEqual(result["groups_found"], 1)
        self.assertEqual(result["dismissed"], 0)
        self.assertTrue(result["shadow_mode"])

        self.assertEqual(self._match_status(winner_id)["match_status"], "UNMATCHED")
        self.assertEqual(self._match_status(loser_id)["match_status"], "UNMATCHED")

        with self._real_conn.cursor() as cur:
            cur.execute(
                "SELECT event_type, details FROM audit_log "
                "WHERE plate = 'TSX123' ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
        self.assertEqual(row["event_type"], "SIGHTING_CONSOLID")
        self.assertLessEqual(
            len(row["event_type"]), 20,
            "event_type debe caber en audit_log.event_type VARCHAR(20) — "
            "ver incidente de VEHICLE_FILTER_EVALUATED (27+ horas en producción)",
        )
        self.assertFalse(row["details"]["applied"])
        self.assertEqual(row["details"]["winner_plate"], "TSX123")
        self.assertEqual(row["details"]["loser_plates"], ["TSX128"])
        self.assertEqual(row["details"]["loser_detection_ids"], [loser_id])

    def test_active_mode_dismisses_loser_keeps_winner_and_evidence_intact(self):
        from api.core.config import SightingConsolidationSettings
        from api.database import consolidate_fuzzy_sightings

        now = datetime.datetime.now(datetime.timezone.utc)
        winner_id, loser_id = self._seed_winner_and_loser(now)

        settings = SightingConsolidationSettings(
            enabled=True, shadow_mode=False, max_distance=1,
            window_seconds=90, min_confidence=0.90,
        )
        with patch("api.database.SIGHTING_CONSOLIDATION_SETTINGS", settings):
            result = consolidate_fuzzy_sightings(self._today_cl())

        self.assertFalse(result["shadow_mode"])
        self.assertGreaterEqual(result["dismissed"], 1)

        winner_row = self._match_status(winner_id)
        loser_row = self._match_status(loser_id)
        self.assertEqual(winner_row["match_status"], "UNMATCHED")
        self.assertEqual(loser_row["match_status"], "DISMISSED")
        # Evidencia (patente leída, imagen) nunca se sobrescribe ni se borra.
        self.assertEqual(loser_row["plate"], "TSX128")
        self.assertIsNotNone(loser_row["image_path"])

    def test_low_confidence_neighbor_is_never_touched_even_if_close(self):
        from api.core.config import SightingConsolidationSettings
        from api.database import consolidate_fuzzy_sightings

        now = datetime.datetime.now(datetime.timezone.utc)
        winner_id, _loser_id = self._seed_winner_and_loser(now)

        # TSX1Z3 está a distancia 1 de TSX123 y dentro de la ventana, pero
        # con confianza cruda 0.80 (< 0.90) — el filtro debe descartarla
        # ANTES de agrupar, así que su avistamiento promovido no se toca.
        stray_at = now + datetime.timedelta(seconds=10)
        self._insert_staging("TSX1Z3", 0.80, stray_at)
        stray_id = self._insert_promoted_detection("TSX1Z3", stray_at, 0.80)

        settings = SightingConsolidationSettings(
            enabled=True, shadow_mode=False, max_distance=1,
            window_seconds=90, min_confidence=0.90,
        )
        with patch("api.database.SIGHTING_CONSOLIDATION_SETTINGS", settings):
            consolidate_fuzzy_sightings(self._today_cl())

        self.assertEqual(self._match_status(stray_id)["match_status"], "UNMATCHED")
        self.assertEqual(self._match_status(winner_id)["match_status"], "UNMATCHED")

    def test_two_plates_beyond_distance_stay_independent(self):
        from api.core.config import SightingConsolidationSettings
        from api.database import consolidate_fuzzy_sightings

        now = datetime.datetime.now(datetime.timezone.utc)
        self._insert_staging("TSX999", 0.95, now)
        first_id = self._insert_promoted_detection("TSX999", now, 0.95)
        second_at = now + datetime.timedelta(seconds=5)
        self._insert_staging("TSX111", 0.95, second_at)
        second_id = self._insert_promoted_detection("TSX111", second_at, 0.95)

        settings = SightingConsolidationSettings(
            enabled=True, shadow_mode=False, max_distance=1,
            window_seconds=90, min_confidence=0.90,
        )
        with patch("api.database.SIGHTING_CONSOLIDATION_SETTINGS", settings):
            consolidate_fuzzy_sightings(self._today_cl())

        self.assertEqual(self._match_status(first_id)["match_status"], "UNMATCHED")
        self.assertEqual(self._match_status(second_id)["match_status"], "UNMATCHED")


if __name__ == "__main__":
    unittest.main()
