from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from docgraph_sidecar.parser.base import ParsedChunk, ParsedDocumentElement


DEFAULT_MAX_CHARS = 1200


@dataclass(frozen=True)
class ChunkingOptions:
    max_chars: int = DEFAULT_MAX_CHARS


def build_chunks(
    elements: tuple[ParsedDocumentElement, ...] | list[ParsedDocumentElement],
    *,
    options: ChunkingOptions | None = None,
) -> tuple[ParsedChunk, ...]:
    options = options or ChunkingOptions()
    if options.max_chars < 100:
        raise ValueError("max_chars must be at least 100.")

    chunks: list[ParsedChunk] = []
    for element in elements:
        text = normalize_text(element.text or "")
        if not text:
            continue

        segments = split_text(text, max_chars=options.max_chars)
        for segment_index, segment in enumerate(segments):
            chunk_index = len(chunks)
            chunks.append(
                ParsedChunk(
                    chunk_id=stable_chunk_id(element, chunk_index, segment),
                    file_id=element.file_id,
                    element_id=element.element_id,
                    chunk_index=chunk_index,
                    chunk_type=element.element_type,
                    page_no=element.page_no,
                    sheet_name=element.sheet_name,
                    slide_no=element.slide_no,
                    heading=infer_heading(element),
                    section_path=element.section_path,
                    text=segment,
                    token_count=estimate_token_count(segment),
                    start_offset=None,
                    end_offset=None,
                    evidence=build_evidence(
                        element,
                        segment_index=segment_index,
                        segment_count=len(segments),
                    ),
                )
            )
    return tuple(chunks)


def build_evidence(
    element: ParsedDocumentElement,
    *,
    segment_index: int,
    segment_count: int,
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "source": "structure_chunker",
        "element_id": element.element_id,
        "element_index": element.element_index,
        "element_type": element.element_type,
        "segment_index": segment_index,
        "segment_count": segment_count,
    }
    if element.page_no is not None:
        evidence["page_no"] = element.page_no
    if element.sheet_name is not None:
        evidence["sheet_name"] = element.sheet_name
    if element.slide_no is not None:
        evidence["slide_no"] = element.slide_no
    if element.section_path is not None:
        evidence["section_path"] = element.section_path
    if element.bbox is not None:
        evidence["bbox"] = element.bbox
    if element.metadata:
        evidence["metadata"] = element.metadata
    return evidence


def split_text(text: str, *, max_chars: int) -> tuple[str, ...]:
    if len(text) <= max_chars:
        return (text,)

    segments: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        split_at = best_split_index(remaining, max_chars=max_chars)
        segment = remaining[:split_at].strip()
        if segment:
            segments.append(segment)
        remaining = remaining[split_at:].strip()

    if remaining:
        segments.append(remaining)
    return tuple(segments)


def best_split_index(text: str, *, max_chars: int) -> int:
    window = text[:max_chars]
    candidates = [
        window.rfind("\n\n"),
        window.rfind("\n"),
        window.rfind(". "),
        window.rfind("; "),
        window.rfind(", "),
        window.rfind(" "),
    ]
    best = max(candidates)
    if best >= max_chars // 2:
        return best + 1
    return max_chars


def infer_heading(element: ParsedDocumentElement) -> str | None:
    if element.element_type == "heading":
        return normalize_text(element.text or "") or None
    if element.section_path:
        return element.section_path.split(">")[-1].strip() or element.section_path
    if element.sheet_name:
        return element.sheet_name
    if element.slide_no is not None:
        return f"Slide {element.slide_no}"
    if element.page_no is not None:
        return f"Page {element.page_no}"
    return None


def normalize_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\xa0", " ")).strip()


def estimate_token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def stable_chunk_id(element: ParsedDocumentElement, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(
        f"{element.file_id}:{element.element_id}:{chunk_index}:{text}".encode("utf-8")
    ).hexdigest()
    return f"chunk-{digest[:24]}"
