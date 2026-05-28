from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docgraph_sidecar.core.db import connect, initialize_database


class FtsIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class FtsIndexResult:
    file_id: str | None
    indexed_chunk_count: int
    indexed_file_count: int
    rebuilt_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "indexed_chunk_count": self.indexed_chunk_count,
            "indexed_file_count": self.indexed_file_count,
            "rebuilt_at": self.rebuilt_at,
        }


def reindex_file_chunks(*, data_dir: Path | None = None, file_id: str) -> FtsIndexResult:
    if not file_id.strip():
        raise FtsIndexError("file_id is required.")
    initialize_database(data_dir=data_dir)
    rebuilt_at = _now()
    connection = connect(data_dir=data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE;")
        chunk_count = replace_file_fts_rows(connection, file_id=file_id)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return FtsIndexResult(
        file_id=file_id,
        indexed_chunk_count=chunk_count,
        indexed_file_count=1 if chunk_count > 0 else 0,
        rebuilt_at=rebuilt_at,
    )


def rebuild_fts(*, data_dir: Path | None = None) -> FtsIndexResult:
    initialize_database(data_dir=data_dir)
    rebuilt_at = _now()
    connection = connect(data_dir=data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE;")
        chunk_count = _count_indexable_chunks(connection)
        file_count = _count_indexable_files(connection)
        connection.execute("DELETE FROM fts_chunks;")
        connection.execute(
            """
            INSERT INTO fts_chunks (file_id, chunk_id, filename, heading, text)
            SELECT
              chunks.file_id,
              chunks.chunk_id,
              files.filename,
              COALESCE(chunks.heading, ''),
              chunks.text
            FROM chunks
            JOIN files ON files.file_id = chunks.file_id
            WHERE files.deleted_flag = 0
            ORDER BY chunks.file_id, chunks.chunk_index
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return FtsIndexResult(
        file_id=None,
        indexed_chunk_count=chunk_count,
        indexed_file_count=file_count,
        rebuilt_at=rebuilt_at,
    )


def replace_file_fts_rows(connection: sqlite3.Connection, *, file_id: str) -> int:
    chunk_count = _count_file_chunks(connection, file_id=file_id)
    connection.execute("DELETE FROM fts_chunks WHERE file_id = ?", (file_id,))
    connection.execute(
        """
        INSERT INTO fts_chunks (file_id, chunk_id, filename, heading, text)
        SELECT
          chunks.file_id,
          chunks.chunk_id,
          files.filename,
          COALESCE(chunks.heading, ''),
          chunks.text
        FROM chunks
        JOIN files ON files.file_id = chunks.file_id
        WHERE chunks.file_id = ?
          AND files.deleted_flag = 0
        ORDER BY chunks.chunk_index
        """,
        (file_id,),
    )
    return chunk_count


def rebuild_fts_json(result: FtsIndexResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)


def _count_file_chunks(connection: sqlite3.Connection, *, file_id: str) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM chunks
            JOIN files ON files.file_id = chunks.file_id
            WHERE chunks.file_id = ?
              AND files.deleted_flag = 0
            """,
            (file_id,),
        ).fetchone()[0]
    )


def _count_indexable_chunks(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM chunks
            JOIN files ON files.file_id = chunks.file_id
            WHERE files.deleted_flag = 0
            """
        ).fetchone()[0]
    )


def _count_indexable_files(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(DISTINCT chunks.file_id)
            FROM chunks
            JOIN files ON files.file_id = chunks.file_id
            WHERE files.deleted_flag = 0
            """
        ).fetchone()[0]
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
