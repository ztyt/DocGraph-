from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docgraph_sidecar.core.db import connect, initialize_database


MAX_FILE_LIST_LIMIT = 200
DEFAULT_FILE_LIST_LIMIT = 50


class FileCatalogError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class FileListFilters:
    type: str | None = None
    status: str | None = None
    source: str | None = None
    keyword: str | None = None
    limit: int = DEFAULT_FILE_LIST_LIMIT
    offset: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "status": self.status,
            "source": self.source,
            "keyword": self.keyword,
            "limit": self.limit,
            "offset": self.offset,
        }


@dataclass(frozen=True)
class FileListItem:
    file_id: str
    filename: str
    path: str
    extension: str | None
    source_type: str | None
    size_bytes: int | None
    modified_time: str | None
    file_status: str
    parse_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "path": self.path,
            "extension": self.extension,
            "source_type": self.source_type,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "file_status": self.file_status,
            "parse_status": self.parse_status,
        }


@dataclass(frozen=True)
class FileDetailChunk:
    chunk_id: str
    chunk_index: int
    chunk_type: str | None
    page_no: int | None
    sheet_name: str | None
    slide_no: int | None
    heading: str | None
    section_path: str | None
    text: str
    token_count: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "chunk_type": self.chunk_type,
            "page_no": self.page_no,
            "sheet_name": self.sheet_name,
            "slide_no": self.slide_no,
            "heading": self.heading,
            "section_path": self.section_path,
            "text": self.text,
            "token_count": self.token_count,
        }


@dataclass(frozen=True)
class FileDetail:
    file: FileListItem
    chunks: tuple[FileDetailChunk, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file.to_dict(),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "chunk_count": len(self.chunks),
        }


@dataclass(frozen=True)
class FileListResult:
    items: tuple[FileListItem, ...]
    total: int
    filters: FileListFilters

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "filters": self.filters.to_dict(),
        }


class FileCatalog:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        initialize_database(data_dir=data_dir)

    def list_files(self, filters: FileListFilters | None = None) -> FileListResult:
        filters = filters or FileListFilters()
        where = ["deleted_flag = 0"]
        values: list[Any] = []

        if filters.type:
            where.append("extension = ?")
            values.append(_normalize_extension(filters.type))
        if filters.status:
            where.append("file_status = ?")
            values.append(filters.status)
        if filters.source:
            where.append("source_type = ?")
            values.append(filters.source)
        if filters.keyword:
            where.append("(filename LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\')")
            keyword = f"%{_escape_like(filters.keyword)}%"
            values.extend([keyword, keyword])

        where_sql = " AND ".join(where)
        connection = connect(data_dir=self.data_dir)
        try:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM files WHERE {where_sql}",
                    values,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT
                  file_id,
                  filename,
                  path,
                  extension,
                  source_type,
                  size_bytes,
                  modified_time,
                  file_status,
                  parse_status
                FROM files
                WHERE {where_sql}
                ORDER BY modified_time DESC, filename ASC
                LIMIT ? OFFSET ?
                """,
                [*values, filters.limit, filters.offset],
            ).fetchall()
        finally:
            connection.close()

        return FileListResult(
            items=tuple(_row_to_file(row) for row in rows),
            total=total,
            filters=filters,
        )

    def get_file_detail(self, file_id: str) -> FileDetail:
        connection = connect(data_dir=self.data_dir)
        try:
            file_row = connection.execute(
                """
                SELECT
                  file_id,
                  filename,
                  path,
                  extension,
                  source_type,
                  size_bytes,
                  modified_time,
                  file_status,
                  parse_status
                FROM files
                WHERE file_id = ?
                  AND deleted_flag = 0
                """,
                (file_id,),
            ).fetchone()
            if file_row is None:
                raise FileCatalogError(
                    "File not found.",
                    details={"file_id": file_id},
                )

            chunk_rows = connection.execute(
                """
                SELECT
                  chunk_id,
                  chunk_index,
                  chunk_type,
                  page_no,
                  sheet_name,
                  slide_no,
                  heading,
                  section_path,
                  text,
                  token_count
                FROM chunks
                WHERE file_id = ?
                ORDER BY chunk_index
                """,
                (file_id,),
            ).fetchall()
        finally:
            connection.close()

        return FileDetail(
            file=_row_to_file(file_row),
            chunks=tuple(_row_to_chunk(row) for row in chunk_rows),
        )


def parse_file_list_filters(params: dict[str, str | None]) -> FileListFilters:
    limit = _parse_int(params.get("limit"), name="limit", default=DEFAULT_FILE_LIST_LIMIT)
    offset = _parse_int(params.get("offset"), name="offset", default=0)
    if limit < 1 or limit > MAX_FILE_LIST_LIMIT:
        raise FileCatalogError(
            "limit must be between 1 and 200.",
            details={"limit": "Expected an integer from 1 to 200."},
        )
    if offset < 0:
        raise FileCatalogError(
            "offset must be greater than or equal to 0.",
            details={"offset": "Expected a non-negative integer."},
        )

    return FileListFilters(
        type=_clean(params.get("type")),
        status=_clean(params.get("status")),
        source=_clean(params.get("source")),
        keyword=_clean(params.get("keyword")),
        limit=limit,
        offset=offset,
    )


def _row_to_file(row: Any) -> FileListItem:
    return FileListItem(
        file_id=str(row["file_id"]),
        filename=str(row["filename"]),
        path=str(row["path"]),
        extension=row["extension"],
        source_type=row["source_type"],
        size_bytes=row["size_bytes"],
        modified_time=row["modified_time"],
        file_status=str(row["file_status"]),
        parse_status=str(row["parse_status"]),
    )


def _row_to_chunk(row: Any) -> FileDetailChunk:
    return FileDetailChunk(
        chunk_id=str(row["chunk_id"]),
        chunk_index=int(row["chunk_index"]),
        chunk_type=row["chunk_type"],
        page_no=row["page_no"],
        sheet_name=row["sheet_name"],
        slide_no=row["slide_no"],
        heading=row["heading"],
        section_path=row["section_path"],
        text=str(row["text"]),
        token_count=row["token_count"],
    )


def _parse_int(value: str | None, *, name: str, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise FileCatalogError(
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


def _normalize_extension(value: str) -> str:
    extension = value.strip().casefold()
    if extension and not extension.startswith("."):
        return f".{extension}"
    return extension


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
