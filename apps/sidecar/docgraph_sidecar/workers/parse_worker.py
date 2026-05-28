from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.core.tasks import TaskQueue, TaskRecord
from docgraph_sidecar.parser.base import (
    ParsedChunk,
    ParsedDocumentElement,
    ParseContext,
    ParseResult,
    ParserError,
)
from docgraph_sidecar.parser.errors import record_parse_error
from docgraph_sidecar.parser.registry import ParserRegistry, ParserRegistryError, default_parser_registry
from docgraph_sidecar.parser.structure_chunker import build_chunks


PARSE_TASK_TYPE = "parse_file"
DEFAULT_PARSE_TIMEOUT_SECONDS = 60.0


class ParseWorkerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


class ParseTimeoutError(ParseWorkerError):
    def __init__(self, *, timeout_seconds: float) -> None:
        super().__init__(
            f"Parse task exceeded {timeout_seconds:g} seconds.",
            error_code="PARSE_TIMEOUT",
            retryable=True,
            details={"timeout_seconds": timeout_seconds},
        )


@dataclass(frozen=True)
class ParseWorkerResult:
    task_id: str
    file_id: str | None
    task_status: str
    file_status: str | None
    parse_status: str | None
    parser_name: str | None = None
    element_count: int = 0
    chunk_count: int = 0
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "file_id": self.file_id,
            "task_status": self.task_status,
            "file_status": self.file_status,
            "parse_status": self.parse_status,
            "parser_name": self.parser_name,
            "element_count": self.element_count,
            "chunk_count": self.chunk_count,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class FileRecord:
    file_id: str
    path: str
    filename: str
    extension: str
    source_type: str | None


@dataclass(frozen=True)
class FailureClassification:
    error_code: str
    error_message: str
    retryable: bool
    parser_name: str
    details: dict[str, Any]


class ParseWorker:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        registry: ParserRegistry | None = None,
        timeout_seconds: float = DEFAULT_PARSE_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ParseWorkerError(
                "timeout_seconds must be greater than zero.",
                error_code="PARSE_WORKER_CONFIG_ERROR",
                details={"timeout_seconds": timeout_seconds},
            )
        self.data_dir = data_dir
        self.registry = registry or default_parser_registry()
        self.timeout_seconds = timeout_seconds
        initialize_database(data_dir=data_dir)
        self.task_queue = TaskQueue(data_dir=data_dir)

    def enqueue_file_parse(
        self,
        file_id: str,
        *,
        priority: int = 50,
        max_attempts: int = 3,
        timeout_seconds: float | None = None,
        task_id: str | None = None,
    ) -> TaskRecord:
        file = self._require_file(file_id)
        timeout = timeout_seconds or self.timeout_seconds
        if timeout <= 0:
            raise ParseWorkerError(
                "timeout_seconds must be greater than zero.",
                error_code="PARSE_WORKER_CONFIG_ERROR",
                details={"timeout_seconds": timeout},
            )

        task = self.task_queue.enqueue(
            PARSE_TASK_TYPE,
            payload={
                "file_id": file.file_id,
                "path": file.path,
                "timeout_seconds": timeout,
            },
            priority=priority,
            max_attempts=max_attempts,
            task_id=task_id,
        )
        self._set_file_status(
            file.file_id,
            file_status="queued_parse",
            parse_status="queued",
            last_error_code=None,
        )
        return task

    def run_once(self) -> ParseWorkerResult | None:
        task = self.task_queue.claim_next(task_type=PARSE_TASK_TYPE)
        if task is None:
            return None

        file_id = task.payload.get("file_id")
        if not isinstance(file_id, str) or not file_id.strip():
            failed_task = self.task_queue.fail(
                task.task_id,
                error_code="PARSE_TASK_PAYLOAD_ERROR",
                error_message="Parse task payload must include file_id.",
                retryable=False,
            )
            return ParseWorkerResult(
                task_id=failed_task.task_id,
                file_id=None,
                task_status=failed_task.task_status,
                file_status=None,
                parse_status=None,
                error_code="PARSE_TASK_PAYLOAD_ERROR",
                error_message="Parse task payload must include file_id.",
            )

        try:
            return self._run_task(task, file_id=file_id)
        except Exception as exc:
            classification = classify_parse_failure(exc)
            record_parse_error(
                data_dir=self.data_dir,
                file_id=file_id,
                task_id=task.task_id,
                error_code=classification.error_code,
                error_message=classification.error_message,
                retryable=classification.retryable,
                parser_name=classification.parser_name,
                details=classification.details,
            )
            failed_task = self.task_queue.fail(
                task.task_id,
                error_code=classification.error_code,
                error_message=classification.error_message,
                retryable=classification.retryable,
            )
            if failed_task.task_status == "queued":
                file_status = "queued_parse"
                parse_status = "queued"
            else:
                file_status = "parse_failed"
                parse_status = "failed"
            self._set_file_status(
                file_id,
                file_status=file_status,
                parse_status=parse_status,
                last_error_code=classification.error_code,
            )
            return ParseWorkerResult(
                task_id=failed_task.task_id,
                file_id=file_id,
                task_status=failed_task.task_status,
                file_status=file_status,
                parse_status=parse_status,
                parser_name=classification.parser_name,
                error_code=classification.error_code,
                error_message=classification.error_message,
            )

    def _run_task(self, task: TaskRecord, *, file_id: str) -> ParseWorkerResult:
        file = self._require_file(file_id)
        timeout = _timeout_from_payload(task.payload, default=self.timeout_seconds)
        self._set_file_status(file_id, file_status="parsing", parse_status="running")

        context = ParseContext(
            file_id=file.file_id,
            path=Path(file.path),
            filename=file.filename,
            extension=file.extension,
            source_type=file.source_type,
        )
        result = parse_with_timeout(self.registry, context, timeout_seconds=timeout)
        chunks = result.chunks or build_chunks(result.elements)
        self._write_parse_result(result, chunks=chunks)
        completed = self.task_queue.complete(task.task_id)
        return ParseWorkerResult(
            task_id=completed.task_id,
            file_id=file_id,
            task_status=completed.task_status,
            file_status="indexed",
            parse_status="parsed",
            parser_name=result.parser_name,
            element_count=len(result.elements),
            chunk_count=len(chunks),
        )

    def _require_file(self, file_id: str) -> FileRecord:
        connection = connect(data_dir=self.data_dir)
        try:
            row = connection.execute(
                """
                SELECT file_id, path, filename, extension, source_type
                FROM files
                WHERE file_id = ?
                  AND deleted_flag = 0
                """,
                (file_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            raise ParseWorkerError(
                "File not found.",
                error_code="FILE_NOT_FOUND",
                retryable=False,
                details={"file_id": file_id},
            )
        return FileRecord(
            file_id=str(row["file_id"]),
            path=str(row["path"]),
            filename=str(row["filename"]),
            extension=str(row["extension"] or ""),
            source_type=row["source_type"],
        )

    def _write_parse_result(
        self,
        result: ParseResult,
        *,
        chunks: tuple[ParsedChunk, ...],
    ) -> None:
        now = _now()
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute("DELETE FROM chunks WHERE file_id = ?", (result.file_id,))
            connection.execute("DELETE FROM document_elements WHERE file_id = ?", (result.file_id,))
            connection.executemany(
                """
                INSERT INTO document_elements (
                  element_id,
                  file_id,
                  element_index,
                  element_type,
                  page_no,
                  sheet_name,
                  slide_no,
                  section_path,
                  bbox_json,
                  text,
                  metadata_json,
                  confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_element_values(element) for element in result.elements],
            )
            connection.executemany(
                """
                INSERT INTO chunks (
                  chunk_id,
                  file_id,
                  element_id,
                  chunk_index,
                  chunk_type,
                  page_no,
                  sheet_name,
                  slide_no,
                  heading,
                  section_path,
                  text,
                  token_count,
                  start_offset,
                  end_offset,
                  evidence_json,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_chunk_values(chunk, created_at=now) for chunk in chunks],
            )
            connection.execute(
                """
                UPDATE files
                SET file_status = 'indexed',
                    parse_status = 'parsed',
                    last_error_code = NULL,
                    indexed_time = ?,
                    updated_at = ?
                WHERE file_id = ?
                """,
                (now, now, result.file_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _set_file_status(
        self,
        file_id: str,
        *,
        file_status: str,
        parse_status: str,
        last_error_code: str | None = None,
    ) -> None:
        now = _now()
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                UPDATE files
                SET file_status = ?,
                    parse_status = ?,
                    last_error_code = ?,
                    updated_at = ?
                WHERE file_id = ?
                """,
                (file_status, parse_status, last_error_code, now, file_id),
            )
            connection.commit()
        finally:
            connection.close()


def parse_with_timeout(
    registry: ParserRegistry,
    context: ParseContext,
    *,
    timeout_seconds: float,
) -> ParseResult:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(registry.parse, context)
    try:
        result = future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise ParseTimeoutError(timeout_seconds=timeout_seconds) from exc
    except Exception:
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True, cancel_futures=True)
        return result


def classify_parse_failure(exc: Exception) -> FailureClassification:
    if isinstance(exc, ParseWorkerError):
        return FailureClassification(
            error_code=exc.error_code,
            error_message=str(exc),
            retryable=exc.retryable,
            parser_name="parse-worker",
            details=exc.details,
        )
    if isinstance(exc, ParserError):
        return FailureClassification(
            error_code=exc.error_code,
            error_message=str(exc),
            retryable=exc.retryable,
            parser_name=exc.parser_name,
            details=exc.details,
        )
    if isinstance(exc, ParserRegistryError):
        return FailureClassification(
            error_code="PARSER_UNSUPPORTED",
            error_message=str(exc),
            retryable=False,
            parser_name="parser-registry",
            details={},
        )
    if isinstance(exc, FileNotFoundError):
        return FailureClassification(
            error_code="FILE_NOT_FOUND",
            error_message=str(exc),
            retryable=False,
            parser_name="filesystem",
            details={"errno": exc.errno, "filename": exc.filename},
        )
    if isinstance(exc, PermissionError):
        return FailureClassification(
            error_code="FILE_PERMISSION_DENIED",
            error_message=str(exc),
            retryable=False,
            parser_name="filesystem",
            details={"errno": exc.errno, "filename": exc.filename},
        )
    return FailureClassification(
        error_code="PARSE_ERROR",
        error_message=str(exc) or type(exc).__name__,
        retryable=True,
        parser_name="unknown",
        details={"error_type": type(exc).__name__},
    )


def _timeout_from_payload(payload: dict[str, Any], *, default: float) -> float:
    raw = payload.get("timeout_seconds")
    if isinstance(raw, bool) or raw is None:
        return default
    if isinstance(raw, int | float):
        value = float(raw)
        if value > 0:
            return value
    return default


def _element_values(element: ParsedDocumentElement) -> tuple[Any, ...]:
    return (
        element.element_id,
        element.file_id,
        element.element_index,
        element.element_type,
        element.page_no,
        element.sheet_name,
        element.slide_no,
        element.section_path,
        _json_or_none(element.bbox),
        element.text,
        _json_or_none(element.metadata),
        element.confidence,
    )


def _chunk_values(chunk: ParsedChunk, *, created_at: str) -> tuple[Any, ...]:
    return (
        chunk.chunk_id,
        chunk.file_id,
        chunk.element_id,
        chunk.chunk_index,
        chunk.chunk_type,
        chunk.page_no,
        chunk.sheet_name,
        chunk.slide_no,
        chunk.heading,
        chunk.section_path,
        chunk.text,
        chunk.token_count,
        chunk.start_offset,
        chunk.end_offset,
        _json_or_none(chunk.evidence),
        created_at,
    )


def _json_or_none(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()
