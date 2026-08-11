import datetime
import os
import tempfile
import unittest
from unittest.mock import patch

from api.core.config import SightingConsolidationSettings
from api.database import _archive_discarded_image, _cluster_staging_reads, _majority_plate

_T0 = datetime.datetime(2026, 8, 10, 11, 16, 25, tzinfo=datetime.timezone.utc)


def _read(plate, confidence, offset_seconds):
    return {
        "plate": plate,
        "confidence": confidence,
        "detected_at": _T0 + datetime.timedelta(seconds=offset_seconds),
    }


class SightingConsolidationSettingsTests(unittest.TestCase):
    def test_defaults_are_disabled_and_shadow_mode(self):
        settings = SightingConsolidationSettings.from_env({})
        self.assertFalse(settings.enabled)
        self.assertTrue(settings.shadow_mode)
        self.assertEqual(settings.mode, "disabled")
        self.assertEqual(settings.min_confidence, 0.90)
        self.assertFalse(settings.archive_discarded_images)

    def test_archive_discarded_images_defaults_off_even_when_active(self):
        settings = SightingConsolidationSettings.from_env({
            "SIGHTING_CONSOLIDATION_ENABLED": "true",
            "SIGHTING_CONSOLIDATION_SHADOW_MODE": "false",
        })
        self.assertFalse(settings.archive_discarded_images)

    def test_archive_discarded_images_reads_env_flag(self):
        settings = SightingConsolidationSettings.from_env({
            "SIGHTING_CONSOLIDATION_ENABLED": "true",
            "SIGHTING_CONSOLIDATION_SHADOW_MODE": "false",
            "SIGHTING_CONSOLIDATION_ARCHIVE_ENABLED": "true",
        })
        self.assertTrue(settings.archive_discarded_images)

    def test_invalid_shadow_mode_configuration_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "SHADOW_MODE"):
            SightingConsolidationSettings(enabled=False, shadow_mode=False)

    def test_invalid_min_confidence_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "MIN_CONFIDENCE"):
            SightingConsolidationSettings(enabled=True, shadow_mode=True, min_confidence=1.5)

    def test_active_mode_requires_enabled_and_not_shadow(self):
        settings = SightingConsolidationSettings(enabled=True, shadow_mode=False)
        self.assertEqual(settings.mode, "active")


class MajorityPlateTests(unittest.TestCase):
    def test_most_frequent_plate_wins_even_with_lower_single_confidence(self):
        """Caso real 2026-08-10: PCYD65 (correcta) aparece 3 veces con
        confianza cruda hasta 0.9999; PCYD55 (incorrecta) aparece 1 vez con
        0.9991 — mayor que CUALQUIER lectura individual de PCYD65 tomada
        sola, pero pierde por cantidad de repeticiones."""
        cluster = [
            _read("PCYD65", 0.9989, 0),
            _read("PCYD55", 0.9991, 15),
            _read("PCYD65", 0.9868, 20),
            _read("PCYD65", 0.9999, 30),
        ]
        self.assertEqual(_majority_plate(cluster), "PCYD65")

    def test_tie_in_count_breaks_by_average_confidence(self):
        cluster = [
            _read("AAA111", 0.99, 0),
            _read("AAA111", 0.98, 5),
            _read("BBB222", 0.95, 10),
            _read("BBB222", 0.91, 15),
        ]
        self.assertEqual(_majority_plate(cluster), "AAA111")


class ClusterStagingReadsTests(unittest.TestCase):
    def test_real_burst_2026_08_10_groups_high_confidence_misreads_under_correct_plate(self):
        """Lecturas crudas reales de staging_detections (ids 20939-20950),
        ya filtradas a confianza >= 0.90 (min_confidence por defecto) —
        20941/20946/20948/20949 quedan afuera del filtro antes de agrupar,
        y PCY8655 (7 caracteres) también quedaría excluido por longitud."""
        reads = [
            _read("PCYD65", 0.9989, 0),
            _read("CCYD65", 0.9480, 5),
            _read("PCYD55", 0.9991, 15),
            _read("PCYD65", 0.9868, 20),
            _read("HCYD63", 0.9556, 25),
            _read("PCYD65", 0.9999, 30),
            _read("CCYD65", 0.9464, 40),
            _read("PCYI65", 0.9355, 54),
        ]
        clusters = _cluster_staging_reads(reads, window_seconds=90, max_distance=1)

        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(len(cluster), 7)  # HCYD63 queda afuera (distancia 2)
        self.assertEqual(_majority_plate(cluster), "PCYD65")
        distinct = {r["plate"] for r in cluster}
        self.assertEqual(distinct, {"PCYD65", "CCYD65", "PCYD55", "PCYI65"})
        self.assertNotIn("HCYD63", distinct)

    def test_two_real_plates_beyond_max_distance_are_not_merged(self):
        reads = [_read("AAA111", 0.95, 0), _read("ZZZ999", 0.95, 5)]
        clusters = _cluster_staging_reads(reads, window_seconds=90, max_distance=1)
        self.assertEqual(clusters, [])

    def test_similar_plates_outside_window_are_not_merged(self):
        reads = [_read("ABC123", 0.95, 0), _read("ABC128", 0.95, 120)]
        clusters = _cluster_staging_reads(reads, window_seconds=90, max_distance=1)
        self.assertEqual(clusters, [])

    def test_repeated_identical_plate_alone_is_not_a_group(self):
        reads = [_read("ABC123", 0.95, 0), _read("ABC123", 0.96, 5)]
        clusters = _cluster_staging_reads(reads, window_seconds=90, max_distance=1)
        self.assertEqual(clusters, [])

    def test_malformed_length_plate_is_excluded_from_clustering(self):
        reads = [_read("PCYD65", 0.99, 0), _read("PCY8655", 0.90, 44)]
        clusters = _cluster_staging_reads(reads, window_seconds=90, max_distance=1)
        self.assertEqual(clusters, [])


class ArchiveDiscardedImageTests(unittest.TestCase):
    """Aislado con directorios temporales (FTP_ROOT/FTP_DISCARDED_DIR
    monkeypatcheados) — nunca toca /ftp real. Ver ADR-006."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ftp_root = os.path.join(self._tmp.name, "ftp")
        self.discarded_dir = os.path.join(self._tmp.name, "ftp", "descartadas")
        os.makedirs(os.path.join(self.ftp_root, "historico", "2026-08-10"))
        self._patchers = [
            patch("api.database.FTP_ROOT", self.ftp_root),
            patch("api.database.FTP_DISCARDED_DIR", self.discarded_dir),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self._tmp.cleanup()

    def _write_source(self, filename="10-15-30_PCYD65_2026-08-10.jpg"):
        path = os.path.join(self.ftp_root, "historico", "2026-08-10", filename)
        with open(path, "wb") as f:
            f.write(b"fake-jpg-bytes")
        return path, f"historico/2026-08-10/{filename}"

    def test_moves_file_and_returns_new_relative_path(self):
        src_path, image_path = self._write_source()
        result = _archive_discarded_image(image_path)
        self.assertEqual(result, "descartadas/2026-08-10/10-15-30_PCYD65_2026-08-10.jpg")
        self.assertFalse(os.path.exists(src_path))
        self.assertTrue(os.path.isfile(
            os.path.join(self.discarded_dir, "2026-08-10", "10-15-30_PCYD65_2026-08-10.jpg")
        ))

    def test_none_image_path_is_a_noop(self):
        self.assertIsNone(_archive_discarded_image(None))

    def test_missing_file_returns_none_without_creating_dirs(self):
        result = _archive_discarded_image("historico/2026-08-10/no-existe.jpg")
        self.assertIsNone(result)
        self.assertFalse(os.path.isdir(self.discarded_dir))

    def test_unexpected_path_shape_is_left_untouched(self):
        # Ya archivada por una corrida anterior, o cualquier forma que no
        # sea "historico/{fecha}/{archivo}".
        src_path, _ = self._write_source()
        already_archived = "descartadas/2026-08-10/10-15-30_PCYD65_2026-08-10.jpg"
        result = _archive_discarded_image(already_archived)
        self.assertIsNone(result)
        self.assertTrue(os.path.isfile(src_path))

    def test_path_traversal_is_rejected(self):
        result = _archive_discarded_image("../../../../etc/passwd")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
