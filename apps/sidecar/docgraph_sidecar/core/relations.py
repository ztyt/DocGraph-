from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from docgraph_sidecar.core.db import connect, initialize_database


CANDIDATE_SOURCES = (
    "same_folder",
    "fts_overlap",
    "same_entity",
    "time_window",
    "filename_similarity",
)
DEFAULT_PER_SOURCE_LIMIT = 20
MAX_PER_SOURCE_LIMIT = 50
TIME_WINDOW_DAYS = 14


class RelationCandidateError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "RELATION_CANDIDATE_ERROR",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class RelationCandidateItem:
    source_file_id: str
    target_file_id: str
    target_filename: str
    candidate_source: str
    raw_score: float
    payload: dict[str, Any]
    created_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file_id": self.source_file_id,
            "target_file_id": self.target_file_id,
            "target_filename": self.target_filename,
            "candidate_source": self.candidate_source,
            "raw_score": self.raw_score,
            "payload": self.payload,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RelationCandidateResult:
    source_file_id: str
    items: tuple[RelationCandidateItem, ...]
    candidate_sources: tuple[str, ...] = CANDIDATE_SOURCES

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file_id": self.source_file_id,
            "items": [item.to_dict() for item in self.items],
            "total": len(self.items),
            "candidate_sources": list(self.candidate_sources),
        }


@dataclass(frozen=True)
class _CandidateDraft:
    target_file_id: str
    candidate_source: str
    raw_score: float
    payload: dict[str, Any]


class RelationCandidateStore:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        initialize_database(data_dir=data_dir)

    def build_for_file(
        self,
        file_id: str,
        *,
        per_source_limit: int = DEFAULT_PER_SOURCE_LIMIT,
    ) -> RelationCandidateResult:
        if per_source_limit < 1 or per_source_limit > MAX_PER_SOURCE_LIMIT:
            raise RelationCandidateError(
                "per_source_limit must be between 1 and 50.",
                details={"per_source_limit": "Expected an integer from 1 to 50."},
            )

        connection = connect(data_dir=self.data_dir)
        try:
            source = _get_source_file(connection, file_id)
            drafts = [
                *self._same_folder(connection, source, per_source_limit),
                *self._same_entity(connection, source, per_source_limit),
                *self._time_window(connection, source, per_source_limit),
                *self._filename_similarity(connection, source, per_source_limit),
                *self._fts_overlap(connection, source, per_source_limit),
            ]
            now = datetime.now(UTC).isoformat()
            placeholders = ",".join("?" for _ in CANDIDATE_SOURCES)
            connection.execute(
                f"""
                DELETE FROM relation_candidates
                WHERE source_file_id = ?
                  AND candidate_source IN ({placeholders})
                """,
                (file_id, *CANDIDATE_SOURCES),
            )
            for draft in drafts:
                connection.execute(
                    """
                    INSERT INTO relation_candidates (
                      source_file_id,
                      target_file_id,
                      candidate_source,
                      raw_score,
                      payload_json,
                      created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_file_id, target_file_id, candidate_source) DO UPDATE SET
                      raw_score = excluded.raw_score,
                      payload_json = excluded.payload_json,
                      created_at = excluded.created_at
                    """,
                    (
                        file_id,
                        draft.target_file_id,
                        draft.candidate_source,
                        draft.raw_score,
                        json.dumps(draft.payload, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
            connection.commit()
            items = _list_candidates(connection, file_id)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return RelationCandidateResult(source_file_id=file_id, items=tuple(items))

    def _same_folder(
        self,
        connection: Any,
        source: Any,
        limit: int,
    ) -> list[_CandidateDraft]:
        parent = _parent_path(str(source["path"]))
        if not parent:
            return []
        rows = connection.execute(
            """
            SELECT file_id, path, filename
            FROM files
            WHERE deleted_flag = 0
              AND file_id != ?
              AND normalized_path LIKE ? ESCAPE '\\'
            ORDER BY modified_time DESC, filename ASC
            LIMIT ?
            """,
            (source["file_id"], f"{_escape_like(parent.casefold())}%", limit * 4),
        ).fetchall()
        drafts: list[_CandidateDraft] = []
        for row in rows:
            if _parent_path(str(row["path"])).casefold() != parent.casefold():
                continue
            drafts.append(
                _CandidateDraft(
                    target_file_id=str(row["file_id"]),
                    candidate_source="same_folder",
                    raw_score=0.72,
                    payload={"folder": parent, "target_filename": row["filename"]},
                )
            )
            if len(drafts) >= limit:
                break
        return drafts

    def _same_entity(
        self,
        connection: Any,
        source: Any,
        limit: int,
    ) -> list[_CandidateDraft]:
        rows = connection.execute(
            """
            SELECT
              target.file_id AS target_file_id,
              target.filename AS target_filename,
              COUNT(DISTINCT source_fe.entity_id) AS overlap_count,
              GROUP_CONCAT(DISTINCT e.entity_text) AS entity_texts,
              GROUP_CONCAT(DISTINCT e.entity_type) AS entity_types
            FROM file_entities source_fe
            JOIN file_entities target_fe ON target_fe.entity_id = source_fe.entity_id
            JOIN entities e ON e.entity_id = source_fe.entity_id
            JOIN files target ON target.file_id = target_fe.file_id
            WHERE source_fe.file_id = ?
              AND target_fe.file_id != ?
              AND target.deleted_flag = 0
            GROUP BY target.file_id, target.filename
            ORDER BY overlap_count DESC, target.modified_time DESC
            LIMIT ?
            """,
            (source["file_id"], source["file_id"], limit),
        ).fetchall()
        return [
            _CandidateDraft(
                target_file_id=str(row["target_file_id"]),
                candidate_source="same_entity",
                raw_score=round(min(1.0, 0.35 + float(row["overlap_count"]) * 0.18), 3),
                payload={
                    "overlap_count": row["overlap_count"],
                    "entities": _split_group_concat(row["entity_texts"]),
                    "entity_types": _split_group_concat(row["entity_types"]),
                    "target_filename": row["target_filename"],
                },
            )
            for row in rows
        ]

    def _time_window(
        self,
        connection: Any,
        source: Any,
        limit: int,
    ) -> list[_CandidateDraft]:
        source_time = _parse_datetime(source["modified_time"])
        if source_time is None:
            return []
        start = (source_time - timedelta(days=TIME_WINDOW_DAYS)).isoformat()
        end = (source_time + timedelta(days=TIME_WINDOW_DAYS)).isoformat()
        rows = connection.execute(
            """
            SELECT file_id, filename, modified_time
            FROM files
            WHERE deleted_flag = 0
              AND file_id != ?
              AND modified_time IS NOT NULL
              AND modified_time >= ?
              AND modified_time <= ?
            ORDER BY modified_time DESC, filename ASC
            LIMIT ?
            """,
            (source["file_id"], start, end, limit * 3),
        ).fetchall()
        drafts: list[_CandidateDraft] = []
        for row in rows:
            target_time = _parse_datetime(row["modified_time"])
            if target_time is None:
                continue
            delta_days = abs((target_time - source_time).total_seconds()) / 86400
            score = max(0.1, 1.0 - (delta_days / TIME_WINDOW_DAYS))
            drafts.append(
                _CandidateDraft(
                    target_file_id=str(row["file_id"]),
                    candidate_source="time_window",
                    raw_score=round(score, 3),
                    payload={
                        "source_modified_time": source["modified_time"],
                        "target_modified_time": row["modified_time"],
                        "delta_days": round(delta_days, 3),
                    },
                )
            )
            if len(drafts) >= limit:
                break
        return drafts

    def _filename_similarity(
        self,
        connection: Any,
        source: Any,
        limit: int,
    ) -> list[_CandidateDraft]:
        source_tokens = _filename_tokens(str(source["filename"]))
        if not source_tokens:
            return []
        clauses = " OR ".join("filename LIKE ? ESCAPE '\\'" for _ in source_tokens)
        rows = connection.execute(
            f"""
            SELECT file_id, filename
            FROM files
            WHERE deleted_flag = 0
              AND file_id != ?
              AND ({clauses})
            ORDER BY modified_time DESC, filename ASC
            LIMIT ?
            """,
            (source["file_id"], *(f"%{_escape_like(token)}%" for token in source_tokens), limit * 5),
        ).fetchall()
        drafts: list[_CandidateDraft] = []
        for row in rows:
            target_tokens = _filename_tokens(str(row["filename"]))
            overlap = source_tokens.intersection(target_tokens)
            union = source_tokens.union(target_tokens)
            if not overlap or not union:
                continue
            score = len(overlap) / len(union)
            drafts.append(
                _CandidateDraft(
                    target_file_id=str(row["file_id"]),
                    candidate_source="filename_similarity",
                    raw_score=round(score, 3),
                    payload={
                        "shared_tokens": sorted(overlap),
                        "source_filename": source["filename"],
                        "target_filename": row["filename"],
                    },
                )
            )
        drafts.sort(key=lambda item: (-item.raw_score, item.target_file_id))
        return drafts[:limit]

    def _fts_overlap(
        self,
        connection: Any,
        source: Any,
        limit: int,
    ) -> list[_CandidateDraft]:
        terms = _source_terms(connection, str(source["file_id"]), str(source["filename"]))[:6]
        if not terms:
            return []
        grouped: dict[str, dict[str, Any]] = {}
        for term in terms:
            rows = connection.execute(
                """
                SELECT
                  files.file_id,
                  files.filename,
                  fts_chunks.chunk_id,
                  bm25(fts_chunks) AS bm25_score
                FROM fts_chunks
                JOIN files ON files.file_id = fts_chunks.file_id
                WHERE fts_chunks MATCH ?
                  AND files.file_id != ?
                  AND files.deleted_flag = 0
                ORDER BY bm25_score ASC, files.modified_time DESC
                LIMIT ?
                """,
                (f'"{term}"', source["file_id"], limit * 4),
            ).fetchall()
            for row in rows:
                target_file_id = str(row["file_id"])
                entry = grouped.setdefault(
                    target_file_id,
                    {
                        "target_filename": row["filename"],
                        "terms": set(),
                        "chunk_ids": set(),
                        "best_bm25": float(row["bm25_score"]),
                    },
                )
                entry["terms"].add(term)
                entry["chunk_ids"].add(str(row["chunk_id"]))
                entry["best_bm25"] = min(float(entry["best_bm25"]), float(row["bm25_score"]))

        drafts = [
            _CandidateDraft(
                target_file_id=target_file_id,
                candidate_source="fts_overlap",
                raw_score=round(min(1.0, 0.24 + 0.14 * len(entry["terms"])), 3),
                payload={
                    "matched_terms": sorted(entry["terms"]),
                    "matched_chunk_ids": sorted(entry["chunk_ids"])[:5],
                    "best_bm25": entry["best_bm25"],
                    "target_filename": entry["target_filename"],
                },
            )
            for target_file_id, entry in grouped.items()
        ]
        drafts.sort(key=lambda item: (-item.raw_score, item.target_file_id))
        return drafts[:limit]


def _get_source_file(connection: Any, file_id: str) -> Any:
    row = connection.execute(
        """
        SELECT file_id, path, normalized_path, filename, modified_time
        FROM files
        WHERE file_id = ?
          AND deleted_flag = 0
        """,
        (file_id,),
    ).fetchone()
    if row is None:
        raise RelationCandidateError(
            "File not found.",
            error_code="FILE_NOT_FOUND",
            details={"file_id": file_id},
        )
    return row


def _list_candidates(connection: Any, source_file_id: str) -> list[RelationCandidateItem]:
    rows = connection.execute(
        """
        SELECT
          rc.source_file_id,
          rc.target_file_id,
          files.filename AS target_filename,
          rc.candidate_source,
          rc.raw_score,
          rc.payload_json,
          rc.created_at
        FROM relation_candidates rc
        JOIN files ON files.file_id = rc.target_file_id
        WHERE rc.source_file_id = ?
        ORDER BY rc.candidate_source ASC, rc.raw_score DESC, files.filename ASC
        """,
        (source_file_id,),
    ).fetchall()
    return [_row_to_candidate(row) for row in rows]


def _row_to_candidate(row: Any) -> RelationCandidateItem:
    return RelationCandidateItem(
        source_file_id=str(row["source_file_id"]),
        target_file_id=str(row["target_file_id"]),
        target_filename=str(row["target_filename"]),
        candidate_source=str(row["candidate_source"]),
        raw_score=float(row["raw_score"] or 0.0),
        payload=_json_object(row["payload_json"]),
        created_at=row["created_at"],
    )


def _source_terms(connection: Any, file_id: str, filename: str) -> list[str]:
    text_parts = [filename]
    rows = connection.execute(
        """
        SELECT heading, text
        FROM chunks
        WHERE file_id = ?
        ORDER BY chunk_index
        LIMIT 5
        """,
        (file_id,),
    ).fetchall()
    for row in rows:
        if row["heading"]:
            text_parts.append(str(row["heading"]))
        text_parts.append(str(row["text"])[:400])
    terms = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", " ".join(text_parts)):
        normalized = token.casefold()
        if normalized in _STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(token)
    return terms


def _filename_tokens(filename: str) -> set[str]:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", stem)
        if token.casefold() not in _STOPWORDS
    }


def _parent_path(value: str) -> str:
    normalized = value.replace("\\", "/").rstrip("/")
    if "/" not in normalized:
        return ""
    return normalized.rsplit("/", 1)[0]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _split_group_concat(value: str | None) -> list[str]:
    if not value:
        return []
    return sorted({item for item in value.split(",") if item})


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


_STOPWORDS = {
    "and",
    "for",
    "from",
    "into",
    "notes",
    "project",
    "the",
    "with",
}
