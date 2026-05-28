import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.indexer.fts import rebuild_fts, reindex_file_chunks
from docgraph_sidecar.parser.registry import ParserRegistry
from docgraph_sidecar.parser.text import TextMarkdownParser
from docgraph_sidecar.settings_store import SettingsStore
from docgraph_sidecar.workers.parse_worker import ParseWorker
from fastapi.testclient import TestClient


class FtsIndexerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "data"
        initialize_database(data_dir=self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reindex_file_chunks_replaces_existing_fts_rows(self) -> None:
        self._insert_file("file-alpha", filename="alpha.md")
        self._insert_chunk("chunk-old", "file-alpha", 0, "obsolete text")
        reindex_file_chunks(data_dir=self.data_dir, file_id="file-alpha")
        self._replace_chunks("file-alpha", [("chunk-new", 0, "fresh alpha project text", "Plan")])

        result = reindex_file_chunks(data_dir=self.data_dir, file_id="file-alpha")

        self.assertEqual(result.file_id, "file-alpha")
        self.assertEqual(result.indexed_chunk_count, 1)
        self.assertEqual(result.indexed_file_count, 1)

        connection = connect(data_dir=self.data_dir)
        try:
            stale = connection.execute(
                "SELECT COUNT(*) FROM fts_chunks WHERE fts_chunks MATCH 'obsolete'"
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT file_id, chunk_id
                FROM fts_chunks
                WHERE fts_chunks MATCH 'fresh'
                """
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(stale, 0)
        self.assertEqual([(row["file_id"], row["chunk_id"]) for row in rows], [
            ("file-alpha", "chunk-new")
        ])

    def test_rebuild_fts_indexes_all_non_deleted_files_and_clears_stale_rows(self) -> None:
        self._insert_file("file-alpha", filename="alpha.md")
        self._insert_file("file-beta", filename="beta.txt")
        self._insert_file("file-deleted", filename="deleted.txt", deleted=True)
        self._insert_chunk("chunk-alpha", "file-alpha", 0, "alpha project budget")
        self._insert_chunk("chunk-beta", "file-beta", 0, "beta meeting notes")
        self._insert_chunk("chunk-deleted", "file-deleted", 0, "deleted secret text")
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO fts_chunks (file_id, chunk_id, filename, heading, text)
                VALUES ('stale-file', 'stale-chunk', 'stale.txt', '', 'stale text')
                """
            )
            connection.commit()
        finally:
            connection.close()

        result = rebuild_fts(data_dir=self.data_dir)

        self.assertEqual(result.file_id, None)
        self.assertEqual(result.indexed_chunk_count, 2)
        self.assertEqual(result.indexed_file_count, 2)

        connection = connect(data_dir=self.data_dir)
        try:
            all_rows = connection.execute(
                "SELECT file_id, chunk_id FROM fts_chunks ORDER BY file_id"
            ).fetchall()
            deleted_count = connection.execute(
                "SELECT COUNT(*) FROM fts_chunks WHERE fts_chunks MATCH 'deleted'"
            ).fetchone()[0]
            stale_count = connection.execute(
                "SELECT COUNT(*) FROM fts_chunks WHERE fts_chunks MATCH 'stale'"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual([(row["file_id"], row["chunk_id"]) for row in all_rows], [
            ("file-alpha", "chunk-alpha"),
            ("file-beta", "chunk-beta"),
        ])
        self.assertEqual(deleted_count, 0)
        self.assertEqual(stale_count, 0)

    def test_rebuild_fts_api_returns_response_envelope(self) -> None:
        self._insert_file("file-alpha", filename="alpha.md")
        self._insert_chunk("chunk-alpha", "file-alpha", 0, "alpha searchable text")
        client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

        response = client.post("/api/db/rebuild-fts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["indexed_chunk_count"], 1)
        self.assertEqual(payload["data"]["indexed_file_count"], 1)
        self.assertIsNone(payload["data"]["file_id"])
        self.assertIsNotNone(payload["data"]["rebuilt_at"])

    def test_cli_rebuild_fts_outputs_result_json(self) -> None:
        self._insert_file("file-alpha", filename="alpha.md")
        self._insert_chunk("chunk-alpha", "file-alpha", 0, "alpha searchable text")
        app_path = Path(__file__).resolve().parents[1] / "app.py"

        result = subprocess.run(
            [sys.executable, str(app_path), "rebuild-fts", "--data-dir", str(self.data_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["indexed_chunk_count"], 1)
        self.assertEqual(payload["indexed_file_count"], 1)

    def test_parse_worker_indexes_chunks_into_fts(self) -> None:
        docs = self.root / "docs"
        docs.mkdir()
        path = docs / "alpha.md"
        path.write_text("# Alpha\n\nBudget searchable paragraph.", encoding="utf-8")
        self._insert_file("file-alpha", filename="alpha.md", path=path, extension=".md")
        worker = ParseWorker(data_dir=self.data_dir, registry=ParserRegistry([TextMarkdownParser()]))
        worker.enqueue_file_parse("file-alpha")

        result = worker.run_once()

        self.assertEqual(result.task_status, "done")
        connection = connect(data_dir=self.data_dir)
        try:
            rows = connection.execute(
                """
                SELECT file_id, chunk_id
                FROM fts_chunks
                WHERE fts_chunks MATCH 'searchable'
                """
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file_id"], "file-alpha")

    def _insert_file(
        self,
        file_id: str,
        *,
        filename: str,
        path: Path | None = None,
        extension: str = ".txt",
        deleted: bool = False,
    ) -> None:
        resolved_path = path or (self.root / filename)
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
                VALUES (?, ?, ?, ?, ?, 'text', 'indexed', 'parsed', ?)
                """,
                (
                    file_id,
                    str(resolved_path),
                    str(resolved_path).casefold(),
                    filename,
                    extension,
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
        heading: str | None = None,
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

    def _replace_chunks(self, file_id: str, chunks: list[tuple[str, int, str, str | None]]) -> None:
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            connection.executemany(
                """
                INSERT INTO chunks (
                  chunk_id,
                  file_id,
                  chunk_index,
                  text,
                  heading
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [(chunk_id, file_id, chunk_index, text, heading) for chunk_id, chunk_index, text, heading in chunks],
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
