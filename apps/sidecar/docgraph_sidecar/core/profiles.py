from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docgraph_sidecar.core.db import connect, initialize_database


MAX_KEYWORDS = 12
MAX_EVIDENCE_CHUNKS = 3


class DocumentProfileError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "PROFILE_ERROR",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class ProfileEvidenceChunk:
    chunk_id: str
    chunk_index: int
    heading: str | None
    section_path: str | None
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "heading": self.heading,
            "section_path": self.section_path,
            "excerpt": self.excerpt,
        }


@dataclass(frozen=True)
class DocumentProfile:
    file_id: str
    central_idea: str | None
    document_role: str | None
    role_confidence: float | None
    project_entities: tuple[str, ...]
    business_objects: tuple[str, ...]
    time_scope: str | None
    keywords: tuple[str, ...]
    summary_short: str | None
    summary_long: str | None
    evidence_chunks: tuple[ProfileEvidenceChunk, ...]
    profile_confidence: float | None
    generated_by: str | None
    updated_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "central_idea": self.central_idea,
            "document_role": self.document_role,
            "role_confidence": self.role_confidence,
            "project_entities": list(self.project_entities),
            "business_objects": list(self.business_objects),
            "time_scope": self.time_scope,
            "keywords": list(self.keywords),
            "summary_short": self.summary_short,
            "summary_long": self.summary_long,
            "evidence_chunks": [chunk.to_dict() for chunk in self.evidence_chunks],
            "profile_confidence": self.profile_confidence,
            "generated_by": self.generated_by,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class DocumentProfileResult:
    file_id: str
    profile: DocumentProfile | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "profile": self.profile.to_dict() if self.profile else None,
            "status": self.status,
        }


class DocumentProfileStore:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        initialize_database(data_dir=data_dir)

    def get_profile(self, file_id: str) -> DocumentProfileResult:
        connection = connect(data_dir=self.data_dir)
        try:
            self._ensure_file_exists(connection, file_id)
            row = connection.execute(
                """
                SELECT
                  file_id,
                  central_idea,
                  document_role,
                  role_confidence,
                  project_entities_json,
                  business_objects_json,
                  time_scope,
                  keywords_json,
                  summary_short,
                  summary_long,
                  evidence_chunks_json,
                  profile_confidence,
                  generated_by,
                  updated_at
                FROM document_profiles
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return DocumentProfileResult(file_id=file_id, profile=None, status="missing")
        return DocumentProfileResult(file_id=file_id, profile=_row_to_profile(row), status="ready")

    def build_profile(self, file_id: str) -> DocumentProfileResult:
        connection = connect(data_dir=self.data_dir)
        try:
            file_row = self._get_file(connection, file_id)
            chunk_rows = connection.execute(
                """
                SELECT
                  chunk_id,
                  chunk_index,
                  heading,
                  section_path,
                  text
                FROM chunks
                WHERE file_id = ?
                ORDER BY chunk_index
                """,
                (file_id,),
            ).fetchall()
            profile = _build_rule_profile(file_row, chunk_rows)
            connection.execute(
                """
                INSERT INTO document_profiles (
                  file_id,
                  central_idea,
                  document_role,
                  role_confidence,
                  project_entities_json,
                  business_objects_json,
                  time_scope,
                  keywords_json,
                  summary_short,
                  summary_long,
                  evidence_chunks_json,
                  profile_confidence,
                  generated_by,
                  updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                  central_idea = excluded.central_idea,
                  document_role = excluded.document_role,
                  role_confidence = excluded.role_confidence,
                  project_entities_json = excluded.project_entities_json,
                  business_objects_json = excluded.business_objects_json,
                  time_scope = excluded.time_scope,
                  keywords_json = excluded.keywords_json,
                  summary_short = excluded.summary_short,
                  summary_long = excluded.summary_long,
                  evidence_chunks_json = excluded.evidence_chunks_json,
                  profile_confidence = excluded.profile_confidence,
                  generated_by = excluded.generated_by,
                  updated_at = excluded.updated_at
                """,
                _profile_to_row(profile),
            )
            connection.commit()
        finally:
            connection.close()

        return DocumentProfileResult(file_id=file_id, profile=profile, status="ready")

    def _ensure_file_exists(self, connection: Any, file_id: str) -> None:
        self._get_file(connection, file_id)

    def _get_file(self, connection: Any, file_id: str) -> Any:
        row = connection.execute(
            """
            SELECT file_id, filename, extension, source_type
            FROM files
            WHERE file_id = ?
              AND deleted_flag = 0
            """,
            (file_id,),
        ).fetchone()
        if row is None:
            raise DocumentProfileError(
                "File not found.",
                error_code="FILE_NOT_FOUND",
                details={"file_id": file_id},
            )
        return row


def _build_rule_profile(file_row: Any, chunk_rows: list[Any]) -> DocumentProfile:
    chunks = tuple(chunk_rows)
    first_text = _first_text(chunks)
    central_idea = _truncate(_first_heading(chunks) or _first_sentence(first_text), 180)
    if not central_idea:
        central_idea = str(file_row["filename"])

    summary_short = _truncate(first_text, 240) if first_text else None
    summary_long_source = "\n\n".join(str(row["text"]).strip() for row in chunks[:5] if row["text"])
    summary_long = _truncate(summary_long_source, 900) if summary_long_source else summary_short
    evidence_chunks = tuple(
        ProfileEvidenceChunk(
            chunk_id=str(row["chunk_id"]),
            chunk_index=int(row["chunk_index"]),
            heading=row["heading"],
            section_path=row["section_path"],
            excerpt=_truncate(str(row["text"]).strip(), 220),
        )
        for row in chunks[:MAX_EVIDENCE_CHUNKS]
    )
    keywords = _extract_keywords(str(file_row["filename"]), chunks)
    confidence = 0.62 if chunks else 0.25

    return DocumentProfile(
        file_id=str(file_row["file_id"]),
        central_idea=central_idea,
        document_role=_document_role(file_row["extension"], file_row["source_type"]),
        role_confidence=0.55,
        project_entities=(),
        business_objects=keywords[:5],
        time_scope=None,
        keywords=keywords,
        summary_short=summary_short,
        summary_long=summary_long,
        evidence_chunks=evidence_chunks,
        profile_confidence=confidence,
        generated_by="rules:vc028",
        updated_at=datetime.now(UTC).isoformat(),
    )


def _profile_to_row(profile: DocumentProfile) -> tuple[Any, ...]:
    return (
        profile.file_id,
        profile.central_idea,
        profile.document_role,
        profile.role_confidence,
        _json_list(profile.project_entities),
        _json_list(profile.business_objects),
        profile.time_scope,
        _json_list(profile.keywords),
        profile.summary_short,
        profile.summary_long,
        json.dumps(
            [chunk.to_dict() for chunk in profile.evidence_chunks],
            ensure_ascii=False,
            sort_keys=True,
        ),
        profile.profile_confidence,
        profile.generated_by,
        profile.updated_at,
    )


def _row_to_profile(row: Any) -> DocumentProfile:
    evidence = tuple(
        ProfileEvidenceChunk(
            chunk_id=str(item.get("chunk_id", "")),
            chunk_index=int(item.get("chunk_index", 0)),
            heading=item.get("heading"),
            section_path=item.get("section_path"),
            excerpt=str(item.get("excerpt", "")),
        )
        for item in _json_array(row["evidence_chunks_json"])
        if isinstance(item, dict)
    )
    return DocumentProfile(
        file_id=str(row["file_id"]),
        central_idea=row["central_idea"],
        document_role=row["document_role"],
        role_confidence=row["role_confidence"],
        project_entities=tuple(str(item) for item in _json_array(row["project_entities_json"])),
        business_objects=tuple(str(item) for item in _json_array(row["business_objects_json"])),
        time_scope=row["time_scope"],
        keywords=tuple(str(item) for item in _json_array(row["keywords_json"])),
        summary_short=row["summary_short"],
        summary_long=row["summary_long"],
        evidence_chunks=evidence,
        profile_confidence=row["profile_confidence"],
        generated_by=row["generated_by"],
        updated_at=row["updated_at"],
    )


def _json_list(items: tuple[str, ...]) -> str:
    return json.dumps(list(items), ensure_ascii=False, sort_keys=True)


def _json_array(value: str | None) -> list[Any]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def _document_role(extension: str | None, source_type: str | None) -> str:
    ext = (extension or "").casefold()
    if ext in {".xlsx", ".xls", ".csv"}:
        return "spreadsheet"
    if ext in {".pptx", ".ppt"}:
        return "presentation"
    if ext == ".pdf":
        return "reference_document"
    if source_type:
        return f"{source_type}_document"
    return "local_document"


def _first_heading(chunks: tuple[Any, ...]) -> str | None:
    for row in chunks:
        heading = row["heading"]
        if isinstance(heading, str) and heading.strip():
            return heading.strip()
    return None


def _first_text(chunks: tuple[Any, ...]) -> str:
    for row in chunks:
        text = str(row["text"]).strip()
        if text:
            return text
    return ""


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    match = re.search(r"[.!?\n。！？]", cleaned)
    if match:
        return cleaned[: match.start()].strip()
    return cleaned


def _extract_keywords(filename: str, chunks: tuple[Any, ...]) -> tuple[str, ...]:
    source_parts = [filename]
    for row in chunks[:8]:
        if row["heading"]:
            source_parts.append(str(row["heading"]))
        if row["section_path"]:
            source_parts.append(str(row["section_path"]))
        source_parts.append(str(row["text"])[:500])
    source = " ".join(source_parts)
    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", source)
    seen: set[str] = set()
    keywords: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip("_-").casefold()
        if not normalized or normalized in _STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(candidate.strip("_-"))
        if len(keywords) >= MAX_KEYWORDS:
            break
    return tuple(keywords)


def _truncate(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 1)].rstrip()}..."


_STOPWORDS = {
    "and",
    "for",
    "from",
    "into",
    "notes",
    "the",
    "with",
}
