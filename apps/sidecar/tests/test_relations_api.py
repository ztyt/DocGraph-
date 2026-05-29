import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.indexer.fts import rebuild_fts
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class RelationCandidatesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        initialize_database(data_dir=self.data_dir)
        self._insert_file(
            "file-alpha",
            "C:/docs/alpha/alpha_plan.md",
            "alpha_plan.md",
            "2026-05-28T08:00:00+00:00",
        )
        self._insert_file(
            "file-budget",
            "C:/docs/alpha/budget.xlsx",
            "budget.xlsx",
            "2026-05-27T08:00:00+00:00",
            extension=".xlsx",
            source_type="office",
        )
        self._insert_file(
            "file-entity",
            "C:/docs/reports/north_report.md",
            "north_report.md",
            "2026-05-01T08:00:00+00:00",
        )
        self._insert_file(
            "file-time",
            "C:/docs/other/timeline.txt",
            "timeline.txt",
            "2026-05-29T08:00:00+00:00",
        )
        self._insert_file(
            "file-name",
            "C:/docs/archive/alpha_plan_notes.txt",
            "alpha_plan_notes.txt",
            "2026-04-10T08:00:00+00:00",
        )
        self._insert_file(
            "file-fts",
            "C:/docs/evidence/camera_notes.txt",
            "camera_notes.txt",
            "2026-03-10T08:00:00+00:00",
        )
        self._insert_chunk("chunk-source", "file-alpha", 0, "Alpha Project camera budget rollout.")
        self._insert_chunk("chunk-budget", "file-budget", 0, "Budget rows for Alpha rollout.")
        self._insert_chunk("chunk-entity", "file-entity", 0, "North Center report.")
        self._insert_chunk("chunk-time", "file-time", 0, "Timeline update.")
        self._insert_chunk("chunk-name", "file-name", 0, "Archived plan notes.")
        self._insert_chunk("chunk-fts", "file-fts", 0, "Camera deployment notes for field rollout.")
        self._insert_entity("entity-alpha", "Alpha Project", "alpha project", "PROJECT")
        self._link_entity("file-alpha", "entity-alpha", "chunk-source")
        self._link_entity("file-entity", "entity-alpha", "chunk-entity")
        rebuild_fts(data_dir=self.data_dir)
        self.client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_relation_candidates_recalls_by_all_sources_and_persists(self) -> None:
        response = self.client.post(
            "/api/relations/candidates/file-alpha",
            params={"per_source_limit": 5},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertEqual(data["source_file_id"], "file-alpha")
        self.assertEqual(
            data["candidate_sources"],
            ["same_folder", "fts_overlap", "same_entity", "time_window", "filename_similarity"],
        )
        sources = {item["candidate_source"] for item in data["items"]}
        self.assertTrue(
            {
                "same_folder",
                "fts_overlap",
                "same_entity",
                "time_window",
                "filename_similarity",
            }.issubset(sources)
        )
        same_entity = next(item for item in data["items"] if item["candidate_source"] == "same_entity")
        self.assertEqual(same_entity["target_file_id"], "file-entity")
        self.assertEqual(same_entity["payload"]["entities"], ["Alpha Project"])
        self.assertGreater(same_entity["raw_score"], 0)

        connection = connect(data_dir=self.data_dir)
        try:
            rows = connection.execute(
                """
                SELECT candidate_source, payload_json
                FROM relation_candidates
                WHERE source_file_id = 'file-alpha'
                """
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(len(rows), data["total"])
        self.assertTrue(any(row["candidate_source"] == "same_folder" for row in rows))
        self.assertTrue(all(isinstance(json.loads(row["payload_json"]), dict) for row in rows))

    def test_build_relation_candidates_rejects_bad_limit(self) -> None:
        response = self.client.post(
            "/api/relations/candidates/file-alpha",
            params={"per_source_limit": 500},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "RELATION_CANDIDATE_ERROR")

    def test_build_relation_candidates_missing_file_returns_not_found(self) -> None:
        response = self.client.post("/api/relations/candidates/missing")

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
        modified_time: str,
        *,
        extension: str = ".txt",
        source_type: str = "text",
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
                  modified_time,
                  file_status,
                  parse_status,
                  deleted_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'indexed', 'parsed', 0)
                """,
                (file_id, path, path.casefold(), filename, extension, source_type, modified_time),
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
                VALUES (?, ?, ?, 'paragraph', 'Evidence', ?)
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
                VALUES (?, ?, ?, ?, 0.9, '2026-05-29T00:00:00+00:00')
                """,
                (entity_id, entity_text, normalized_text, entity_type),
            )
            connection.commit()
        finally:
            connection.close()

    def _link_entity(self, file_id: str, entity_id: str, chunk_id: str) -> None:
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
                VALUES (?, ?, ?, 'Alpha Project', 0.9, '2026-05-29T00:00:00+00:00')
                """,
                (file_id, entity_id, chunk_id),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
