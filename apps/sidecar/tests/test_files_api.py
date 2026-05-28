import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class FilesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        initialize_database(data_dir=self.data_dir)
        self._insert_file(
            "file-alpha",
            "C:/docs/alpha.md",
            "alpha.md",
            ".md",
            "text",
            128,
            "2026-05-28T08:00:00+00:00",
            "discovered",
        )
        self._insert_file(
            "file-budget",
            "C:/docs/budget.xlsx",
            "budget.xlsx",
            ".xlsx",
            "office",
            2048,
            "2026-05-27T08:00:00+00:00",
            "indexed",
        )
        self.client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_files_api_returns_response_envelope(self) -> None:
        response = self.client.get("/api/files")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["total"], 2)
        self.assertEqual(payload["data"]["items"][0]["filename"], "alpha.md")
        self.assertEqual(payload["data"]["items"][0]["size_bytes"], 128)
        self.assertEqual(payload["data"]["items"][0]["file_status"], "discovered")
        self.assertEqual(payload["data"]["filters"]["limit"], 50)

    def test_files_api_filters_results(self) -> None:
        response = self.client.get(
            "/api/files",
            params={"type": "xlsx", "status": "indexed", "source": "office", "keyword": "budget"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["file_id"], "file-budget")
        self.assertEqual(data["filters"]["type"], "xlsx")

    def test_files_api_rejects_invalid_limit(self) -> None:
        response = self.client.get("/api/files", params={"limit": "nope"})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "FILES_QUERY_VALIDATION_ERROR")
        self.assertIn("limit", payload["error"]["details"])

    def _insert_file(
        self,
        file_id: str,
        path: str,
        filename: str,
        extension: str,
        source_type: str,
        size_bytes: int,
        modified_time: str,
        file_status: str,
    ) -> None:
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO files (
                  file_id,
                  path,
                  normalized_path,
                  filename,
                  extension,
                  source_type,
                  size_bytes,
                  modified_time,
                  file_status,
                  parse_status,
                  deleted_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)
                """,
                (
                    file_id,
                    path,
                    path.casefold(),
                    filename,
                    extension,
                    source_type,
                    size_bytes,
                    modified_time,
                    file_status,
                ),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
