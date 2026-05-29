import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class ProfileApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        initialize_database(data_dir=self.data_dir)
        self._insert_file("file-alpha", "C:/docs/alpha.md", "alpha.md", ".md", "text")
        self._insert_chunk(
            "chunk-alpha-1",
            "file-alpha",
            0,
            "Alpha Project",
            "Alpha Project",
            "Alpha Project kickoff notes for local search.",
        )
        self._insert_chunk(
            "chunk-alpha-2",
            "file-alpha",
            1,
            "Budget",
            "Alpha Project > Budget",
            "Budget owner is North Center.",
        )
        self.client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_get_profile_returns_empty_state_before_build(self) -> None:
        response = self.client.get("/api/files/file-alpha/profile")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["file_id"], "file-alpha")
        self.assertEqual(payload["data"]["status"], "missing")
        self.assertIsNone(payload["data"]["profile"])

    def test_build_profile_generates_rule_profile_and_persists_it(self) -> None:
        build_response = self.client.post("/api/profile/build/file-alpha")

        self.assertEqual(build_response.status_code, 200)
        build_payload = build_response.json()
        profile = build_payload["data"]["profile"]
        self.assertTrue(build_payload["ok"])
        self.assertEqual(build_payload["data"]["status"], "ready")
        self.assertEqual(profile["central_idea"], "Alpha Project")
        self.assertEqual(profile["document_role"], "text_document")
        self.assertEqual(profile["generated_by"], "rules:vc031")
        self.assertEqual(profile["evidence_chunks"][0]["chunk_id"], "chunk-alpha-1")
        self.assertIn("heading", profile["evidence_chunks"][0]["source"])
        self.assertGreater(profile["evidence_chunks"][0]["score"], 0)
        self.assertGreaterEqual(profile["profile_confidence"], 0.7)
        self.assertIn("Alpha", profile["keywords"])

        get_response = self.client.get("/api/files/file-alpha/profile")
        self.assertEqual(get_response.status_code, 200)
        saved = get_response.json()["data"]
        self.assertEqual(saved["status"], "ready")
        self.assertEqual(saved["profile"]["central_idea"], "Alpha Project")

        connection = connect(data_dir=self.data_dir)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM document_profiles WHERE file_id = 'file-alpha'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_profile_endpoints_return_not_found_for_missing_file(self) -> None:
        for method, path in (
            ("get", "/api/files/missing/profile"),
            ("post", "/api/profile/build/missing"),
        ):
            response = getattr(self.client, method)(path)

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
                  page_no,
                  sheet_name,
                  slide_no,
                  heading,
                  section_path,
                  text,
                  token_count
                )
                VALUES (?, ?, ?, 'paragraph', NULL, NULL, NULL, ?, ?, ?, 6)
                """,
                (chunk_id, file_id, chunk_index, heading, section_path, text),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
