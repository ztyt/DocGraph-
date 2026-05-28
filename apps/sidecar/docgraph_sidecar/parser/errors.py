from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.parser.base import ParseContext, ParseResult, ParserError
from docgraph_sidecar.parser.registry import ParserRegistry


def parse_with_error_recording(
    registry: ParserRegistry,
    context: ParseContext,
    *,
    data_dir: Path | None = None,
    task_id: str | None = None,
) -> ParseResult:
    try:
        return registry.parse(context)
    except ParserError as exc:
        record_parse_error(
            data_dir=data_dir,
            file_id=context.file_id,
            task_id=task_id,
            error_code=exc.error_code,
            error_message=str(exc),
            retryable=exc.retryable,
            parser_name=exc.parser_name,
            details=exc.details,
        )
        raise


def record_parse_error(
    *,
    data_dir: Path | None,
    file_id: str | None,
    error_code: str,
    error_message: str,
    parser_name: str,
    task_id: str | None = None,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> str:
    initialize_database(data_dir=data_dir)
    error_id = f"parse-error-{uuid4().hex}"
    connection = connect(data_dir=data_dir)
    try:
        connection.execute(
            """
            INSERT INTO parse_errors (
              error_id,
              file_id,
              task_id,
              error_code,
              error_message,
              retryable,
              parser_name,
              details_json,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                error_id,
                file_id,
                task_id,
                error_code,
                error_message,
                1 if retryable else 0,
                parser_name,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return error_id
