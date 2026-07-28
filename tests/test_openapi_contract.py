import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql://contract-test.invalid/db")
sys.modules["fast_alpr"] = None

from api.detect import app


class OpenAPIContractTests(unittest.TestCase):
    def test_existing_paths_are_preserved_and_not_duplicated(self):
        schema = app.openapi()
        expected = {
            "/api/cars",
            "/api/history",
            "/api/history/{session_id}/plate",
            "/api/history/{session_id}/review",
            "/api/clear-history",
            "/api/stats",
            "/api/detect",
            "/api/entry",
            "/api/exit/{plate}",
            "/api/cars/{plate}",
            "/api/ftp/image",
            "/api/ftp/video",
            "/api/ftp/events",
            "/api/monitor/images",
            "/api/monitor/review",
            "/api/monitor/file/{folder}/{date}/{filename}",
            "/api/video/upload",
            "/api/video/results/{video_id}",
            "/api/staging/deduplicate",
            "/api/staging/status",
            "/api/sightings",
            "/api/sightings/{plate}",
            "/api/audit/feedback",
            "/api/audit/log",
            "/api/excel/upload",
            "/api/excel/reconcile",
            "/api/excel/imports",
            "/auth/login",
            "/auth/me",
            "/auth/password",
            "/auth/users",
            "/auth/users/{user_id}",
        }
        self.assertTrue(expected.issubset(schema["paths"]))
        operation_ids = [
            operation["operationId"]
            for path in schema["paths"].values()
            for method, operation in path.items()
            if method.lower()
            in {"get", "post", "put", "patch", "delete", "options", "head"}
        ]
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_direction_diagnostics_are_additive(self):
        schema = app.openapi()
        self.assertIn("/api/audit/direction/config", schema["paths"])
        self.assertIn("/api/audit/direction/metrics", schema["paths"])

    def test_detection_and_stay_contracts_are_additive(self):
        schema = app.openapi()
        self.assertIn("/api/detections", schema["paths"])
        self.assertIn("/api/stays", schema["paths"])
        self.assertIn("/api/stays/reconcile", schema["paths"])
        self.assertIn("/api/stay-proposals", schema["paths"])
        self.assertIn("/api/monitor/review/promote", schema["paths"])
        self.assertIn("/api/detections/{detection_id}", schema["paths"])


if __name__ == "__main__":
    unittest.main()
