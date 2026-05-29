import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class EntitiesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        initialize_database(data_dir=self.data_dir)
        self._insert_file("file-alpha", "C:/docs/alpha.md", "alpha.md")
        self._insert_chunk("chunk-alpha-1", "file-alpha", 0, "Alpha project budget.")
        self.client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_file_entities_returns_empty_supported_type_envelope(self) -> None:
        response = self.client.get("/api/files/file-alpha/entities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertEqual(data["file_id"], "file-alpha")
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)
        self.assertEqual(
            data["supported_types"],
            ["PROJECT", "ORG", "LOCATION", "DEVICE", "MONEY", "DATE", "ID_CODE"],
        )

    def test_file_entities_returns_supported_entities_with_evidence(self) -> None:
        self._insert_entity(
            "entity-project-alpha",
            "Alpha Project",
            "alpha project",
            "PROJECT",
            0.92,
        )
        self._insert_entity(
            "entity-org-north",
            "North Center",
            "north center",
            "ORG",
            0.87,
        )
        self._insert_entity(
            "entity-person-hidden",
            "Jane Doe",
            "jane doe",
            "PERSON",
            0.7,
        )
        self._link_entity(
            "file-alpha",
            "entity-project-alpha",
            "chunk-alpha-1",
            "Alpha Project budget kickoff.",
            0.91,
        )
        self._link_entity(
            "file-alpha",
            "entity-org-north",
            "chunk-alpha-1",
            "Owner: North Center.",
            0.82,
        )
        self._link_entity(
            "file-alpha",
            "entity-person-hidden",
            "chunk-alpha-1",
            "Jane Doe",
            0.7,
        )

        response = self.client.get("/api/files/file-alpha/entities")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 2)
        self.assertEqual([item["entity_type"] for item in data["items"]], ["ORG", "PROJECT"])
        self.assertEqual(data["items"][0]["entity_text"], "North Center")
        self.assertEqual(data["items"][0]["evidence_chunk_id"], "chunk-alpha-1")
        self.assertEqual(data["items"][0]["evidence_confidence"], 0.82)
        self.assertEqual(data["items"][1]["normalized_text"], "alpha project")

    def test_file_entities_missing_file_returns_not_found(self) -> None:
        response = self.client.get("/api/files/missing/entities")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "FILE_NOT_FOUND")
        self.assertEqual(payload["error"]["details"]["file_id"], "missing")

    def _insert_file(self, file_id: str, path: str, filename: str) -> None:
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
                  file_status,
                  parse_status,
                  deleted_flag
                )
                VALUES (?, ?, ?, ?, '.md', 'text', 'indexed', 'parsed', 0)
                """,
                (file_id, path, path.casefold(), filename),
            )
            connection.commit()
        finally:
            connection.close()

    def _insert_chunk(self, chunk_id: str, file_id: str, chunk_index: int, text: str) -> None:
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
                  text
                )
                VALUES (?, ?, ?, 'paragraph', 'Alpha', ?)
                """,
                (chunk_id, file_id, chunk_index, text),
            )
            connection.commit()
        finally:
            connection.close()

    def _insert_entity(
        self,
        entity_id: str,
        entity_text: str,
        normalized_text: str,
        entity_type: str,
        confidence: float,
    ) -> None:
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO entities (
                  entity_id,
                  entity_text,
                  normalized_text,
                  entity_type,
                  confidence,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, '2026-05-29T00:00:00+00:00')
                """,
                (entity_id, entity_text, normalized_text, entity_type, confidence),
            )
            connection.commit()
        finally:
            connection.close()

    def _link_entity(
        self,
        file_id: str,
        entity_id: str,
        evidence_chunk_id: str,
        evidence_text: str,
        confidence: float,
    ) -> None:
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO file_entities (
                  file_id,
                  entity_id,
                  evidence_chunk_id,
                  evidence_text,
                  confidence,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, '2026-05-29T00:00:00+00:00')
                """,
                (file_id, entity_id, evidence_chunk_id, evidence_text, confidence),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
