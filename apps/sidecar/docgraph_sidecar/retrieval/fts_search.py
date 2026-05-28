from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docgraph_sidecar.core.db import connect, initialize_database


DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50
MAX_MATCHED_CHUNKS_PER_FILE = 5


class FtsSearchError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class FtsSearchFilters:
    query: str
    type: str | None = None
    source: str | None = None
    modified_from: str | None = None
    modified_to: str | None = None
    limit: int = DEFAULT_SEARCH_LIMIT
    offset: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "q": self.query,
            "type": self.type,
            "source": self.source,
            "modified_from": self.modified_from,
            "modified_to": self.modified_to,
            "limit": self.limit,
            "offset": self.offset,
        }


@dataclass(frozen=True)
class MatchedChunk:
    chunk_id: str
    heading: str | None
    snippet: str
    bm25_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "heading": self.heading,
            "snippet": self.snippet,
            "bm25_score": self.bm25_score,
        }


@dataclass(frozen=True)
class SearchResultItem:
    file_id: str
    filename: str
    path: str
    extension: str | None
    source_type: str | None
    modified_time: str | None
    snippet: str
    bm25_score: float
    matched_chunks: tuple[MatchedChunk, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "path": self.path,
            "extension": self.extension,
            "source_type": self.source_type,
            "modified_time": self.modified_time,
            "snippet": self.snippet,
            "bm25_score": self.bm25_score,
            "matched_chunks": [chunk.to_dict() for chunk in self.matched_chunks],
        }


@dataclass(frozen=True)
class FtsSearchResult:
    items: tuple[SearchResultItem, ...]
    total: int
    filters: FtsSearchFilters

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "filters": self.filters.to_dict(),
        }


def search_fts(
    *,
    data_dir: Path | None = None,
    filters: FtsSearchFilters,
) -> FtsSearchResult:
    initialize_database(data_dir=data_dir)
    match_query = build_match_query(filters.query)
    where_sql, values = build_filter_sql(filters)
    connection = connect(data_dir=data_dir)
    try:
        rows = connection.execute(
            f"""
            SELECT
              files.file_id,
              files.filename,
              files.path,
              files.extension,
              files.source_type,
              files.modified_time,
              fts_chunks.chunk_id,
              NULLIF(fts_chunks.heading, '') AS heading,
              snippet(fts_chunks, 4, '<mark>', '</mark>', '...', 18) AS snippet,
              bm25(fts_chunks) AS bm25_score
            FROM fts_chunks
            JOIN files ON files.file_id = fts_chunks.file_id
            WHERE fts_chunks MATCH ?
              AND {where_sql}
            ORDER BY bm25_score ASC, files.modified_time DESC, files.filename ASC
            """,
            [match_query, *values],
        ).fetchall()
    finally:
        connection.close()

    grouped: dict[str, SearchResultItemBuilder] = {}
    ordered_file_ids: list[str] = []
    for row in rows:
        file_id = str(row["file_id"])
        if file_id not in grouped:
            grouped[file_id] = SearchResultItemBuilder.from_row(row)
            ordered_file_ids.append(file_id)
        grouped[file_id].add_chunk(row)

    all_items = tuple(grouped[file_id].build() for file_id in ordered_file_ids)
    paged_items = all_items[filters.offset : filters.offset + filters.limit]
    return FtsSearchResult(
        items=paged_items,
        total=len(all_items),
        filters=filters,
    )


class SearchResultItemBuilder:
    def __init__(
        self,
        *,
        file_id: str,
        filename: str,
        path: str,
        extension: str | None,
        source_type: str | None,
        modified_time: str | None,
    ) -> None:
        self.file_id = file_id
        self.filename = filename
        self.path = path
        self.extension = extension
        self.source_type = source_type
        self.modified_time = modified_time
        self.best_score: float | None = None
        self.snippet = ""
        self.matched_chunks: list[MatchedChunk] = []

    @classmethod
    def from_row(cls, row: Any) -> SearchResultItemBuilder:
        return cls(
            file_id=str(row["file_id"]),
            filename=str(row["filename"]),
            path=str(row["path"]),
            extension=row["extension"],
            source_type=row["source_type"],
            modified_time=row["modified_time"],
        )

    def add_chunk(self, row: Any) -> None:
        score = float(row["bm25_score"])
        snippet = str(row["snippet"] or "")
        if self.best_score is None or score < self.best_score:
            self.best_score = score
            self.snippet = snippet
        if len(self.matched_chunks) >= MAX_MATCHED_CHUNKS_PER_FILE:
            return
        self.matched_chunks.append(
            MatchedChunk(
                chunk_id=str(row["chunk_id"]),
                heading=row["heading"],
                snippet=snippet,
                bm25_score=score,
            )
        )

    def build(self) -> SearchResultItem:
        return SearchResultItem(
            file_id=self.file_id,
            filename=self.filename,
            path=self.path,
            extension=self.extension,
            source_type=self.source_type,
            modified_time=self.modified_time,
            snippet=self.snippet,
            bm25_score=self.best_score if self.best_score is not None else 0.0,
            matched_chunks=tuple(self.matched_chunks),
        )


def parse_search_filters(params: dict[str, str | None]) -> FtsSearchFilters:
    query = _clean(params.get("q"))
    if query is None:
        raise FtsSearchError(
            "Search query is required.",
            details={"q": "Expected a non-empty search query."},
        )

    limit = _parse_int(params.get("limit"), name="limit", default=DEFAULT_SEARCH_LIMIT)
    offset = _parse_int(params.get("offset"), name="offset", default=0)
    if limit < 1 or limit > MAX_SEARCH_LIMIT:
        raise FtsSearchError(
            "limit must be between 1 and 50.",
            details={"limit": "Expected an integer from 1 to 50."},
        )
    if offset < 0:
        raise FtsSearchError(
            "offset must be greater than or equal to 0.",
            details={"offset": "Expected a non-negative integer."},
        )

    return FtsSearchFilters(
        query=query,
        type=_clean(params.get("type")),
        source=_clean(params.get("source")),
        modified_from=_clean(params.get("modified_from") or params.get("time_from")),
        modified_to=_clean(params.get("modified_to") or params.get("time_to")),
        limit=limit,
        offset=offset,
    )


def build_filter_sql(filters: FtsSearchFilters) -> tuple[str, list[Any]]:
    where = ["files.deleted_flag = 0"]
    values: list[Any] = []
    if filters.type:
        where.append("files.extension = ?")
        values.append(normalize_extension(filters.type))
    if filters.source:
        where.append("files.source_type = ?")
        values.append(filters.source)
    if filters.modified_from:
        where.append("files.modified_time >= ?")
        values.append(filters.modified_from)
    if filters.modified_to:
        where.append("files.modified_time <= ?")
        values.append(filters.modified_to)
    return " AND ".join(where), values


def build_match_query(query: str) -> str:
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not terms:
        raise FtsSearchError(
            "Search query must contain at least one searchable token.",
            details={"q": "Expected letters, numbers, or CJK text."},
        )
    return " ".join(f'"{term}"' for term in terms[:16])


def normalize_extension(value: str) -> str:
    extension = value.strip().casefold()
    if extension and not extension.startswith("."):
        return f".{extension}"
    return extension


def _parse_int(value: str | None, *, name: str, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise FtsSearchError(
            f"{name} must be an integer.",
            details={name: "Expected an integer."},
        ) from exc


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.casefold() == "all":
        return None
    return cleaned
