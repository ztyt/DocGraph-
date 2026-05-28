import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.core.tasks import TaskQueue
from docgraph_sidecar.parser.base import BaseParser, ParseContext, ParseResult, ParserError
from docgraph_sidecar.parser.registry import ParserRegistry
from docgraph_sidecar.parser.text import TextMarkdownParser
from docgraph_sidecar.settings_store import SettingsStore
from docgraph_sidecar.workers.parse_worker import PARSE_TASK_TYPE, ParseWorker
from fastapi.testclient import TestClient


class FailingParser(BaseParser):
    name = "failing-parser"
    supported_extensions = (".txt",)

    def parse(self, context: ParseContext) -> ParseResult:
        raise ParserError(
            "Temporary parser failure.",
            error_code="TEMP_PARSE_ERROR",
            parser_name=self.name,
            retryable=True,
            details={"kind": "temporary"},
        )


class SlowParser(BaseParser):
    name = "slow-parser"
    supported_extensions = (".txt",)

    def parse(self, context: ParseContext) -> ParseResult:
        time.sleep(0.05)
        return ParseResult(parser_name=self.name, file_id=context.file_id)


class ParseWorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "data"
        self.docs = self.root / "docs"
        self.docs.mkdir()
        initialize_database(data_dir=self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_once_parses_file_and_writes_elements_and_chunks(self) -> None:
        path = self.docs / "alpha.md"
        path.write_text("# Alpha\n\nBudget paragraph.", encoding="utf-8")
        self._insert_file("file-alpha", path, extension=".md", source_type="text")
        worker = ParseWorker(data_dir=self.data_dir, registry=ParserRegistry([TextMarkdownParser()]))
        task = worker.enqueue_file_parse("file-alpha", task_id="parse-alpha")

        result = worker.run_once()

        self.assertIsNotNone(result)
        self.assertEqual(task.task_id, "parse-alpha")
        self.assertEqual(result.task_status, "done")
        self.assertEqual(result.file_status, "indexed")
        self.assertEqual(result.parse_status, "parsed")
        self.assertEqual(result.parser_name, "text-markdown")
        self.assertEqual(result.element_count, 2)
        self.assertEqual(result.chunk_count, 2)

        connection = connect(data_dir=self.data_dir)
        try:
            file_row = connection.execute(
                "SELECT file_status, parse_status, last_error_code FROM files WHERE file_id = ?",
                ("file-alpha",),
            ).fetchone()
            elements = connection.execute(
                "SELECT element_type, text FROM document_elements ORDER BY element_index"
            ).fetchall()
            chunks = connection.execute(
                "SELECT chunk_type, heading, text FROM chunks ORDER BY chunk_index"
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(file_row["file_status"], "indexed")
        self.assertEqual(file_row["parse_status"], "parsed")
        self.assertIsNone(file_row["last_error_code"])
        self.assertEqual([(row["element_type"], row["text"]) for row in elements], [
            ("heading", "Alpha"),
            ("paragraph", "Budget paragraph."),
        ])
        self.assertEqual(chunks[1]["heading"], "Alpha")

    def test_retry_api_enqueues_parse_task_with_response_envelope(self) -> None:
        path = self.docs / "alpha.txt"
        path.write_text("alpha", encoding="utf-8")
        self._insert_file("file-alpha", path, extension=".txt", source_type="text")
        client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

        response = client.post("/api/parse/retry/file-alpha")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["file_id"], "file-alpha")
        self.assertEqual(payload["data"]["task"]["task_type"], PARSE_TASK_TYPE)
        self.assertEqual(payload["data"]["task"]["task_status"], "queued")

        connection = connect(data_dir=self.data_dir)
        try:
            row = connection.execute(
                "SELECT file_status, parse_status FROM files WHERE file_id = 'file-alpha'"
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(row["file_status"], "queued_parse")
        self.assertEqual(row["parse_status"], "queued")

    def test_retry_api_returns_not_found_for_missing_file(self) -> None:
        client = TestClient(create_app(settings_store=SettingsStore(self.data_dir)))

        response = client.post("/api/parse/retry/missing")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "FILE_NOT_FOUND")

    def test_missing_source_file_is_classified_as_non_retryable_failure(self) -> None:
        self._insert_file("file-missing", self.docs / "missing.txt", extension=".txt", source_type="text")
        worker = ParseWorker(data_dir=self.data_dir, registry=ParserRegistry([TextMarkdownParser()]))
        worker.enqueue_file_parse("file-missing", max_attempts=3)

        result = worker.run_once()

        self.assertEqual(result.task_status, "failed")
        self.assertEqual(result.file_status, "parse_failed")
        self.assertEqual(result.parse_status, "failed")
        self.assertEqual(result.error_code, "FILE_NOT_FOUND")

        connection = connect(data_dir=self.data_dir)
        try:
            file_row = connection.execute(
                "SELECT file_status, parse_status, last_error_code FROM files WHERE file_id = ?",
                ("file-missing",),
            ).fetchone()
            error_row = connection.execute(
                "SELECT error_code, retryable, parser_name FROM parse_errors"
            ).fetchone()
            task = TaskQueue(data_dir=self.data_dir).list(status="failed")[0]
        finally:
            connection.close()

        self.assertEqual(file_row["file_status"], "parse_failed")
        self.assertEqual(file_row["parse_status"], "failed")
        self.assertEqual(file_row["last_error_code"], "FILE_NOT_FOUND")
        self.assertEqual(error_row["error_code"], "FILE_NOT_FOUND")
        self.assertEqual(error_row["retryable"], 0)
        self.assertEqual(error_row["parser_name"], "filesystem")
        self.assertEqual(task.last_error_code, "FILE_NOT_FOUND")

    def test_retryable_parser_error_requeues_then_fails_at_max_attempts(self) -> None:
        path = self.docs / "temporary.txt"
        path.write_text("temporary", encoding="utf-8")
        self._insert_file("file-temp", path, extension=".txt", source_type="text")
        worker = ParseWorker(data_dir=self.data_dir, registry=ParserRegistry([FailingParser()]))
        worker.enqueue_file_parse("file-temp", max_attempts=2)

        first = worker.run_once()
        second = worker.run_once()

        self.assertEqual(first.task_status, "queued")
        self.assertEqual(first.file_status, "queued_parse")
        self.assertEqual(first.parse_status, "queued")
        self.assertEqual(first.error_code, "TEMP_PARSE_ERROR")
        self.assertEqual(second.task_status, "failed")
        self.assertEqual(second.file_status, "parse_failed")
        self.assertEqual(second.parse_status, "failed")

        connection = connect(data_dir=self.data_dir)
        try:
            parse_error_count = connection.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(parse_error_count, 2)

    def test_timeout_is_classified_as_retryable_parse_timeout(self) -> None:
        path = self.docs / "slow.txt"
        path.write_text("slow", encoding="utf-8")
        self._insert_file("file-slow", path, extension=".txt", source_type="text")
        worker = ParseWorker(data_dir=self.data_dir, registry=ParserRegistry([SlowParser()]))
        worker.enqueue_file_parse("file-slow", max_attempts=1, timeout_seconds=0.01)

        result = worker.run_once()

        self.assertEqual(result.task_status, "failed")
        self.assertEqual(result.file_status, "parse_failed")
        self.assertEqual(result.error_code, "PARSE_TIMEOUT")

        connection = connect(data_dir=self.data_dir)
        try:
            error_row = connection.execute(
                "SELECT error_code, retryable, parser_name FROM parse_errors"
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(error_row["error_code"], "PARSE_TIMEOUT")
        self.assertEqual(error_row["retryable"], 1)
        self.assertEqual(error_row["parser_name"], "parse-worker")

    def test_run_once_returns_none_when_no_parse_task_is_ready(self) -> None:
        worker = ParseWorker(data_dir=self.data_dir)

        self.assertIsNone(worker.run_once())

    def _insert_file(
        self,
        file_id: str,
        path: Path,
        *,
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
                  file_status,
                  parse_status,
                  deleted_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, 'discovered', 'pending', 0)
                """,
                (
                    file_id,
                    str(path),
                    str(path).casefold(),
                    path.name,
                    extension,
                    source_type,
                ),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
