from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docgraph_sidecar.core.db import connect, initialize_database


SUPPORTED_ENTITY_TYPES = (
    "PROJECT",
    "ORG",
    "LOCATION",
    "DEVICE",
    "MONEY",
    "DATE",
    "ID_CODE",
)


class EntityStoreError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "ENTITY_ERROR",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class FileEntityItem:
    entity_id: str
    entity_text: str
    normalized_text: str | None
    entity_type: str | None
    entity_confidence: float | None
    evidence_chunk_id: str | None
    evidence_text: str | None
    evidence_confidence: float | None
    created_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_text": self.entity_text,
            "normalized_text": self.normalized_text,
            "entity_type": self.entity_type,
            "entity_confidence": self.entity_confidence,
            "evidence_chunk_id": self.evidence_chunk_id,
            "evidence_text": self.evidence_text,
            "evidence_confidence": self.evidence_confidence,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class FileEntityResult:
    file_id: str
    items: tuple[FileEntityItem, ...]
    supported_types: tuple[str, ...] = SUPPORTED_ENTITY_TYPES

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "items": [item.to_dict() for item in self.items],
            "total": len(self.items),
            "supported_types": list(self.supported_types),
        }


class EntityStore:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        initialize_database(data_dir=data_dir)

    def get_file_entities(self, file_id: str) -> FileEntityResult:
        connection = connect(data_dir=self.data_dir)
        try:
            self._ensure_file_exists(connection, file_id)
            rows = connection.execute(
                """
                SELECT
                  e.entity_id,
                  e.entity_text,
                  e.normalized_text,
                  e.entity_type,
                  e.confidence AS entity_confidence,
                  fe.evidence_chunk_id,
                  fe.evidence_text,
                  fe.confidence AS evidence_confidence,
                  fe.created_at
                FROM file_entities fe
                JOIN entities e ON e.entity_id = fe.entity_id
                WHERE fe.file_id = ?
                  AND (
                    e.entity_type IS NULL
                    OR e.entity_type IN ('PROJECT', 'ORG', 'LOCATION', 'DEVICE', 'MONEY', 'DATE', 'ID_CODE')
                  )
                ORDER BY
                  e.entity_type ASC,
                  e.normalized_text ASC,
                  fe.evidence_chunk_id ASC
                """,
                (file_id,),
            ).fetchall()
        finally:
            connection.close()

        return FileEntityResult(
            file_id=file_id,
            items=tuple(_row_to_file_entity(row) for row in rows),
        )

    def _ensure_file_exists(self, connection: Any, file_id: str) -> None:
        row = connection.execute(
            """
            SELECT file_id
            FROM files
            WHERE file_id = ?
              AND deleted_flag = 0
            """,
            (file_id,),
        ).fetchone()
        if row is None:
            raise EntityStoreError(
                "File not found.",
                error_code="FILE_NOT_FOUND",
                details={"file_id": file_id},
            )


def _row_to_file_entity(row: Any) -> FileEntityItem:
    return FileEntityItem(
        entity_id=str(row["entity_id"]),
        entity_text=str(row["entity_text"]),
        normalized_text=row["normalized_text"],
        entity_type=row["entity_type"],
        entity_confidence=row["entity_confidence"],
        evidence_chunk_id=row["evidence_chunk_id"],
        evidence_text=row["evidence_text"],
        evidence_confidence=row["evidence_confidence"],
        created_at=row["created_at"],
    )
