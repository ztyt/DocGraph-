import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar import __version__
from docgraph_sidecar.api import create_app
from fastapi.testclient import TestClient


class SkeletonTest(unittest.TestCase):
    def test_version_is_defined(self) -> None:
        self.assertEqual(__version__, "0.0.0")


class HealthApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

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


if __name__ == "__main__":
    unittest.main()
