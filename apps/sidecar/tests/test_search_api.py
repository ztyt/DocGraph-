import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.indexer.fts import rebuild_fts
from docgraph_sidecar.retrieval.fts_search import build_match_query
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class SearchApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        initialize_database(data_dir=self.data_dir)
        self._insert_file(
            "file-alpha",
            "alpha.md",
            ".md",
            "text",
            "2026-05-28T08:00:00+00:00",
        )
        self._insert_file(
            "file-budget",
            "budget.xlsx",
            ".xlsx",
            "office",
            "2026-05-27T08:00:00+00:00",
        )
        self._insert_file(
            "file-old",
            "old.txt",
            ".txt",
            "text",
            "2026-05-01T08:00:00+00:00",
        )
        self._insert_file(
            "file-deleted",
            "deleted.txt",
            ".txt",
            "text",
            "2026-05-29T08:00:00+00:00",
            deleted=True,
        )
        self._insert_chunk("chunk-alpha-1", "file-alpha", 0, "Alpha project kickoff notes.", "Alpha")
        self._insert_chunk("chunk-alpha-2", "file-alpha", 1, "Budget owner is North Center.", "Budget")
        self._insert_chunk("chunk-budget-1", "file-budget", 0, "Alpha camera budget sheet.", "Sheet1")
        self._insert_chunk("chunk-old-1", "file-old", 0, "Alpha archived material.", "Archive")
        self._insert_chunk("chunk-deleted-1", "file-deleted", 0, "Alpha deleted material.", "Deleted")
        rebuild_fts(data_dir=self.data_dir)
        self.client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_api_returns_grouped_results_with_snippets(self) -> None:
        response = self.client.get("/api/search", params={"q": "alpha", "limit": 10})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["filters"]["q"], "alpha")
        self.assertEqual(data["filters"]["limit"], 10)
        self.assertEqual({item["file_id"] for item in data["items"]}, {
            "file-alpha",
            "file-budget",
            "file-old",
        })
        first = data["items"][0]
        self.assertIn("file_id", first)
        self.assertIn("filename", first)
        self.assertIn("path", first)
        self.assertIn("extension", first)
        self.assertIn("modified_time", first)
        self.assertIn("snippet", first)
        self.assertIn("bm25_score", first)
        self.assertGreaterEqual(len(first["matched_chunks"]), 1)
        self.assertIn("<mark>Alpha</mark>", first["snippet"])

    def test_search_api_filters_by_type_source_and_time(self) -> None:
        response = self.client.get(
            "/api/search",
            params={
                "q": "alpha",
                "type": "xlsx",
                "source": "office",
                "modified_from": "2026-05-20T00:00:00+00:00",
                "modified_to": "2026-05-28T23:59:59+00:00",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["file_id"], "file-budget")
        self.assertEqual(data["filters"]["type"], "xlsx")
        self.assertEqual(data["filters"]["source"], "office")

    def test_search_api_paginates_file_results_after_grouping(self) -> None:
        first_page = self.client.get("/api/search", params={"q": "alpha", "limit": 1, "offset": 0})
        second_page = self.client.get("/api/search", params={"q": "alpha", "limit": 1, "offset": 1})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        first_data = first_page.json()["data"]
        second_data = second_page.json()["data"]
        self.assertEqual(first_data["total"], 3)
        self.assertEqual(second_data["total"], 3)
        self.assertEqual(len(first_data["items"]), 1)
        self.assertEqual(len(second_data["items"]), 1)
        self.assertNotEqual(
            first_data["items"][0]["file_id"],
            second_data["items"][0]["file_id"],
        )

    def test_search_api_rejects_missing_query(self) -> None:
        response = self.client.get("/api/search")

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "SEARCH_QUERY_VALIDATION_ERROR")
        self.assertIn("q", payload["error"]["details"])

    def test_search_api_rejects_invalid_limit(self) -> None:
        response = self.client.get("/api/search", params={"q": "alpha", "limit": "1000"})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "SEARCH_QUERY_VALIDATION_ERROR")
        self.assertIn("limit", payload["error"]["details"])

    def test_match_query_ignores_fts_syntax_punctuation(self) -> None:
        self.assertEqual(build_match_query('alpha OR "budget"*'), '"alpha" "OR" "budget"')

    def _insert_file(
        self,
        file_id: str,
        filename: str,
        extension: str,
        source_type: str,
        modified_time: str,
        *,
        deleted: bool = False,
    ) -> None:
        path = f"C:/docs/{filename}"
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
                VALUES (?, ?, ?, ?, ?, ?, ?, 'indexed', 'parsed', ?)
                """,
                (
                    file_id,
                    path,
                    path.casefold(),
                    filename,
                    extension,
                    source_type,
                    modified_time,
                    1 if deleted else 0,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _insert_chunk(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        text: str,
        heading: str,
    ) -> None:
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO chunks (
                  chunk_id,
                  file_id,
                  chunk_index,
                  heading,
                  text
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (chunk_id, file_id, chunk_index, heading, text),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
