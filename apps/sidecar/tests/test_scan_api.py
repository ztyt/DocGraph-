import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class ScanApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.scan_root = Path(self.temp_dir.name) / "docs"
        self.scan_root.mkdir()
        self.store = SettingsStore(self.data_dir)
        self.client = TestClient(create_app(settings_store=self.store))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_and_get_scan_job(self) -> None:
        create = self.client.post(
            "/api/scan/jobs",
            json={"root_path": str(self.scan_root), "compute_hash": True, "priority": 10},
        )

        self.assertEqual(create.status_code, 200)
        created = create.json()
        self.assertTrue(created["ok"])
        job = created["data"]
        self.assertTrue(job["job_id"].startswith("scan-"))
        self.assertEqual(job["job_status"], "queued")
        self.assertEqual(job["current_directory"], str(self.scan_root.resolve()))
        self.assertEqual(job["scanned_count"], 0)
        self.assertEqual(job["failed_count"], 0)
        self.assertEqual(job["ignored_count"], 0)

        status = self.client.get(f"/api/scan/jobs/{job['job_id']}")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["data"]["job_id"], job["job_id"])

    def test_scan_job_pause_and_resume(self) -> None:
        created = self.client.post(
            "/api/scan/jobs",
            json={"root_path": str(self.scan_root)},
        ).json()["data"]

        pause = self.client.post(f"/api/scan/jobs/{created['job_id']}/pause")
        resume = self.client.post(f"/api/scan/jobs/{created['job_id']}/resume")

        self.assertEqual(pause.status_code, 200)
        self.assertEqual(pause.json()["data"]["job_status"], "paused")
        self.assertEqual(resume.status_code, 200)
        self.assertEqual(resume.json()["data"]["job_status"], "queued")

    def test_invalid_scan_job_payload_returns_error_envelope(self) -> None:
        response = self.client.post("/api/scan/jobs", json={"root_path": str(self.scan_root / "x")})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "SCAN_JOB_VALIDATION_ERROR")
        self.assertIn("root_path", payload["error"]["details"])

    def test_missing_scan_job_returns_error_envelope(self) -> None:
        response = self.client.get("/api/scan/jobs/missing")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "SCAN_JOB_NOT_FOUND")

    def test_missing_scan_job_pause_returns_error_envelope(self) -> None:
        response = self.client.post("/api/scan/jobs/missing/pause")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "SCAN_JOB_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
