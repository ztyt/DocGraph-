from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParseContext:
    file_id: str
    path: Path
    filename: str
    extension: str
    source_type: str | None = None

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        file_id: str,
        source_type: str | None = None,
    ) -> ParseContext:
        resolved = Path(path)
        return cls(
            file_id=file_id,
            path=resolved,
            filename=resolved.name,
            extension=resolved.suffix.casefold(),
            source_type=source_type,
        )


@dataclass(frozen=True)
class ParsedDocumentElement:
    element_id: str
    file_id: str
    element_index: int
    text: str | None = None
    element_type: str | None = None
    page_no: int | None = None
    sheet_name: str | None = None
    slide_no: int | None = None
    section_path: str | None = None
    bbox: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "file_id": self.file_id,
            "element_index": self.element_index,
            "element_type": self.element_type,
            "page_no": self.page_no,
            "sheet_name": self.sheet_name,
            "slide_no": self.slide_no,
            "section_path": self.section_path,
            "bbox": self.bbox,
            "text": self.text,
            "metadata": self.metadata,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ParsedChunk:
    chunk_id: str
    file_id: str
    chunk_index: int
    text: str
    element_id: str | None = None
    chunk_type: str | None = None
    page_no: int | None = None
    sheet_name: str | None = None
    slide_no: int | None = None
    heading: str | None = None
    section_path: str | None = None
    token_count: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "file_id": self.file_id,
            "element_id": self.element_id,
            "chunk_index": self.chunk_index,
            "chunk_type": self.chunk_type,
            "page_no": self.page_no,
            "sheet_name": self.sheet_name,
            "slide_no": self.slide_no,
            "heading": self.heading,
            "section_path": self.section_path,
            "text": self.text,
            "token_count": self.token_count,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ParseResult:
    parser_name: str
    file_id: str
    elements: tuple[ParsedDocumentElement, ...] = ()
    chunks: tuple[ParsedChunk, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "parser_name": self.parser_name,
            "file_id": self.file_id,
            "elements": [element.to_dict() for element in self.elements],
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "warnings": list(self.warnings),
        }


class BaseParser(ABC):
    name: str
    supported_extensions: tuple[str, ...]
    supported_source_types: tuple[str, ...] = ()

    def can_parse(self, context: ParseContext) -> bool:
        extension = normalize_extension(context.extension)
        source_type = context.source_type or ""
        return extension in self.normalized_extensions or (
            bool(source_type) and source_type in self.supported_source_types
        )

    @property
    def normalized_extensions(self) -> tuple[str, ...]:
        return tuple(normalize_extension(extension) for extension in self.supported_extensions)

    @abstractmethod
    def parse(self, context: ParseContext) -> ParseResult:
        """Return document elements and chunks without writing to the database."""


def normalize_extension(extension: str) -> str:
    cleaned = extension.strip().casefold()
    if cleaned and not cleaned.startswith("."):
        return f".{cleaned}"
    return cleaned
