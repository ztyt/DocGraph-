import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class FileDetailApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        initialize_database(data_dir=self.data_dir)
        self._insert_file("file-alpha", "C:/docs/alpha.md", "alpha.md", ".md", "text")
        self._insert_chunk(
            "chunk-alpha-1",
            "file-alpha",
            0,
            "heading",
            "Alpha",
            "Alpha Project",
            "Alpha Project",
        )
        self._insert_chunk(
            "chunk-alpha-2",
            "file-alpha",
            1,
            "paragraph",
            "Alpha Project",
            "Alpha Project > Budget",
            "Budget owner is North Center.",
        )
        self.client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_file_detail_returns_metadata_and_chunks(self) -> None:
        response = self.client.get("/api/files/file-alpha")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertEqual(data["file"]["file_id"], "file-alpha")
        self.assertEqual(data["file"]["filename"], "alpha.md")
        self.assertEqual(data["file"]["path"], "C:/docs/alpha.md")
        self.assertEqual(data["file"]["parse_status"], "parsed")
        self.assertEqual(data["chunk_count"], 2)
        self.assertEqual(data["chunks"][0]["chunk_id"], "chunk-alpha-1")
        self.assertEqual(data["chunks"][0]["heading"], "Alpha")
        self.assertEqual(data["chunks"][1]["section_path"], "Alpha Project > Budget")
        self.assertIn("Budget owner", data["chunks"][1]["text"])

    def test_file_detail_missing_file_returns_not_found_envelope(self) -> None:
        response = self.client.get("/api/files/missing")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "FILE_NOT_FOUND")
        self.assertEqual(payload["error"]["details"]["file_id"], "missing")

    def _insert_file(
        self,
        file_id: str,
        path: str,
        filename: str,
        extension: str,
        source_type: str,
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
                VALUES (?, ?, ?, ?, ?, ?, 128, '2026-05-28T08:00:00+00:00', 'indexed', 'parsed', 0)
                """,
                (file_id, path, path.casefold(), filename, extension, source_type),
            )
            connection.commit()
        finally:
            connection.close()

    def _insert_chunk(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        chunk_type: str,
        heading: str,
        section_path: str,
        text: str,
    ) -> None:
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO chunks (
                  chunk_id,
                  file_id,
                  chunk_index,
                  chunk_type,
                  heading,
                  section_path,
                  text,
                  token_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 4)
                """,
                (chunk_id, file_id, chunk_index, chunk_type, heading, section_path, text),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
