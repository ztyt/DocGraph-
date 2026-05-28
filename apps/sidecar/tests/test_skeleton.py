import unittest
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar import __version__
from docgraph_sidecar.api import create_app
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class SkeletonTest(unittest.TestCase):
    def test_version_is_defined(self) -> None:
        self.assertEqual(__version__, "0.0.0")


class HealthApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = SettingsStore(Path(self.temp_dir.name))
        self.client = TestClient(create_app(settings_store=self.store))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_health_uses_response_envelope(self) -> None:
        response = self.client.get("/api/health", headers={"x-trace-id": "test-trace"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["trace_id"], "test-trace")
        self.assertIsInstance(payload["elapsed_ms"], int)
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertEqual(payload["data"]["service"], "docgraph-sidecar")
        self.assertFalse(payload["data"]["features"]["llm"])

    def test_system_info_uses_response_envelope(self) -> None:
        response = self.client.get("/api/system/info")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["error"])
        self.assertTrue(payload["trace_id"].startswith("dg-"))
        self.assertEqual(payload["data"]["service"], "docgraph-sidecar")
        self.assertIn("python_version", payload["data"])

    def test_localhost_dev_ports_are_allowed_by_cors(self) -> None:
        response = self.client.options(
            "/api/health",
            headers={
                "origin": "http://localhost:5174",
                "access-control-request-method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5174")

    def test_settings_can_be_read_and_updated(self) -> None:
        response = self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["privacy_mode"], "local")
        self.assertEqual(payload["data"]["retrieval_backend"], "fts")
        self.assertEqual(payload["data"]["graph_node_cap"], 50)

        update = self.client.put(
            "/api/settings",
            json={
                "privacy_mode": "half_cloud",
                "retrieval_backend": "rrf",
                "graph_node_cap": 80,
                "max_workers_parse": 3,
            },
        )

        self.assertEqual(update.status_code, 200)
        updated = update.json()["data"]
        self.assertEqual(updated["privacy_mode"], "half_cloud")
        self.assertEqual(updated["retrieval_backend"], "rrf")
        self.assertEqual(updated["graph_node_cap"], 80)
        self.assertEqual(updated["max_workers_parse"], 3)

    def test_invalid_settings_return_error_envelope(self) -> None:
        response = self.client.put("/api/settings", json={"graph_node_cap": 500})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "SETTINGS_VALIDATION_ERROR")
        self.assertIn("graph_node_cap", payload["error"]["details"])

    def test_invalid_settings_file_falls_back_to_defaults(self) -> None:
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text('{"graph_node_cap": 999}', encoding="utf-8")

        response = self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["graph_node_cap"], 50)

    def test_features_can_be_read_and_updated(self) -> None:
        response = self.client.put("/api/features", json={"llm": True, "ocr": True})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["data"]["llm"])
        self.assertTrue(payload["data"]["ocr"])
        self.assertFalse(payload["data"]["vector_search"])

        health = self.client.get("/api/health").json()
        self.assertTrue(health["data"]["features"]["llm"])
        self.assertTrue(health["data"]["features"]["ocr"])

    def test_db_snapshot_status_and_restore_api(self) -> None:
        status = self.client.get("/api/db/status")

        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["data"]["exists"])
        self.assertEqual(status.json()["data"]["schema_version"], "003_task_queue_contract")

        snapshot = self.client.post("/api/db/snapshot")
        self.assertEqual(snapshot.status_code, 200)
        snapshot_data = snapshot.json()["data"]
        self.assertEqual(snapshot_data["status"], "created")
        self.assertTrue(snapshot_data["snapshot_id"].startswith("snap-"))

        restore = self.client.post(f"/api/db/restore/{snapshot_data['snapshot_id']}")
        self.assertEqual(restore.status_code, 200)
        self.assertEqual(restore.json()["data"]["status"], "restored")

    def test_missing_snapshot_returns_error_envelope(self) -> None:
        response = self.client.post("/api/db/restore/missing")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "SNAPSHOT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
