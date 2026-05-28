from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.scanner.ignore_rules import DEFAULT_IGNORE_RULES, IgnoreRules, explain_ignore


TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".log"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".gz"}


@dataclass(frozen=True)
class FileMetadata:
    file_id: str
    path: str
    normalized_path: str
    filename: str
    extension: str
    size_bytes: int
    sha256: str | None
    source_type: str
    created_time: str | None
    modified_time: str | None
    indexed_time: str


@dataclass(frozen=True)
class ScanError:
    path: str
    error: str


@dataclass(frozen=True)
class ScanResult:
    root: str
    discovered_count: int
    ignored_count: int
    error_count: int
    written_count: int
    errors: tuple[ScanError, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "discovered_count": self.discovered_count,
            "ignored_count": self.ignored_count,
            "error_count": self.error_count,
            "written_count": self.written_count,
            "errors": [error.__dict__ for error in self.errors],
        }


def scan_directory_to_db(
    root: str | Path,
    *,
    data_dir: Path | None = None,
    compute_hash: bool = False,
    rules: IgnoreRules = DEFAULT_IGNORE_RULES,
) -> ScanResult:
    initialize_database(data_dir=data_dir)
    files: list[FileMetadata] = []
    errors: list[ScanError] = []
    ignored_count = 0
    root_path = Path(root)

    for event in walk_file_metadata(root_path, compute_hash=compute_hash, rules=rules):
        if isinstance(event, FileMetadata):
            files.append(event)
        elif event == "ignored":
            ignored_count += 1
        else:
            errors.append(event)

    written_count = write_files(data_dir=data_dir, files=files)
    return ScanResult(
        root=str(root_path),
        discovered_count=len(files),
        ignored_count=ignored_count,
        error_count=len(errors),
        written_count=written_count,
        errors=tuple(errors),
    )


def walk_file_metadata(
    root: Path,
    *,
    compute_hash: bool = False,
    rules: IgnoreRules = DEFAULT_IGNORE_RULES,
) -> list[FileMetadata | ScanError | str]:
    results: list[FileMetadata | ScanError | str] = []
    _walk(root, results, compute_hash=compute_hash, rules=rules)
    return results


def write_files(*, data_dir: Path | None, files: list[FileMetadata]) -> int:
    if not files:
        return 0

    connection = connect(data_dir=data_dir)
    try:
        connection.executemany(
            """
            INSERT INTO files (
              file_id,
              path,
              normalized_path,
              filename,
              extension,
              size_bytes,
              sha256,
              source_type,
              created_time,
              modified_time,
              indexed_time,
              file_status,
              parse_status,
              deleted_flag,
              created_at,
              updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered', 'pending', 0, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
              path = excluded.path,
              normalized_path = excluded.normalized_path,
              filename = excluded.filename,
              extension = excluded.extension,
              size_bytes = excluded.size_bytes,
              sha256 = excluded.sha256,
              source_type = excluded.source_type,
              created_time = excluded.created_time,
              modified_time = excluded.modified_time,
              indexed_time = excluded.indexed_time,
              file_status = 'discovered',
              deleted_flag = 0,
              updated_at = excluded.updated_at;
            """,
            [
                (
                    item.file_id,
                    item.path,
                    item.normalized_path,
                    item.filename,
                    item.extension,
                    item.size_bytes,
                    item.sha256,
                    item.source_type,
                    item.created_time,
                    item.modified_time,
                    item.indexed_time,
                    item.indexed_time,
                    item.indexed_time,
                )
                for item in files
            ],
        )
        connection.commit()
        return len(files)
    finally:
        connection.close()


def build_file_metadata(path: Path, *, compute_hash: bool = False) -> FileMetadata:
    stat = path.stat()
    normalized_path = normalize_path(path)
    indexed_time = _now()
    extension = path.suffix.casefold()
    return FileMetadata(
        file_id=file_id_for_path(normalized_path),
        path=str(path),
        normalized_path=normalized_path,
        filename=path.name,
        extension=extension,
        size_bytes=stat.st_size,
        sha256=sha256_file(path) if compute_hash else None,
        source_type=source_type_for_extension(extension),
        created_time=_timestamp(stat.st_ctime),
        modified_time=_timestamp(stat.st_mtime),
        indexed_time=indexed_time,
    )


def normalize_path(path: str | Path) -> str:
    resolved = Path(path).resolve(strict=False)
    normalized = os.path.normpath(str(resolved)).replace("\\", "/")
    if os.name == "nt":
        return normalized.casefold()
    return normalized


def file_id_for_path(normalized_path: str) -> str:
    digest = hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()
    return f"file-{digest[:24]}"


def source_type_for_extension(extension: str) -> str:
    extension = extension.casefold()
    if extension in TEXT_EXTENSIONS:
        return "text"
    if extension in OFFICE_EXTENSIONS:
        return "office"
    if extension in PDF_EXTENSIONS:
        return "pdf"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in ARCHIVE_EXTENSIONS:
        return "archive"
    return "unknown"


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(
    directory: Path,
    results: list[FileMetadata | ScanError | str],
    *,
    compute_hash: bool,
    rules: IgnoreRules,
) -> None:
    decision = explain_ignore(directory, is_dir=True, rules=rules)
    if decision.ignored:
        results.append("ignored")
        return

    try:
        with os.scandir(directory) as entries:
            sorted_entries = sorted(entries, key=lambda entry: entry.name.casefold())
    except OSError as exc:
        results.append(ScanError(str(directory), str(exc)))
        return

    for entry in sorted_entries:
        entry_path = Path(entry.path)
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
        except OSError as exc:
            results.append(ScanError(str(entry_path), str(exc)))
            continue

        decision = explain_ignore(entry_path, is_dir=is_dir, rules=rules)
        if decision.ignored:
            results.append("ignored")
            continue

        if is_dir:
            _walk(entry_path, results, compute_hash=compute_hash, rules=rules)
            continue

        if not is_file:
            continue

        try:
            results.append(build_file_metadata(entry_path, compute_hash=compute_hash))
        except OSError as exc:
            results.append(ScanError(str(entry_path), str(exc)))


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()


def _now() -> str:
    return datetime.now(UTC).isoformat()

