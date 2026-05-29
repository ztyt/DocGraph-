from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


MAX_KEYWORDS = 12
MAX_EVIDENCE_CHUNKS = 5


@dataclass(frozen=True)
class ProfileFileInput:
    file_id: str
    filename: str
    extension: str | None
    source_type: str | None


@dataclass(frozen=True)
class ProfileChunkInput:
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


@dataclass(frozen=True)
class RuleEvidenceDraft:
    chunk_id: str
    chunk_index: int
    heading: str | None
    section_path: str | None
    excerpt: str
    score: float
    source: str


@dataclass(frozen=True)
class RuleProfileDraft:
    central_idea: str
    document_role: str
    role_confidence: float
    business_objects: tuple[str, ...]
    keywords: tuple[str, ...]
    summary_short: str | None
    summary_long: str | None
    evidence_chunks: tuple[RuleEvidenceDraft, ...]
    profile_confidence: float


def build_rule_profile(
    file: ProfileFileInput,
    chunks: tuple[ProfileChunkInput, ...],
) -> RuleProfileDraft:
    scored_chunks = _score_chunks(file, chunks)
    evidence_chunks = tuple(
        RuleEvidenceDraft(
            chunk_id=chunk.chunk_id,
            chunk_index=chunk.chunk_index,
            heading=chunk.heading,
            section_path=chunk.section_path,
            excerpt=_truncate(chunk.text, 220),
            score=round(score, 3),
            source=source,
        )
        for score, source, chunk in scored_chunks[:MAX_EVIDENCE_CHUNKS]
    )
    role, role_confidence = _document_role(file, chunks)
    central_idea = _central_idea(file, chunks, evidence_chunks)
    keywords = _extract_keywords(file, chunks, evidence_chunks)
    summary_short = _summary_short(central_idea, chunks, evidence_chunks)
    summary_long = _summary_long(chunks, evidence_chunks) or summary_short

    return RuleProfileDraft(
        central_idea=central_idea,
        document_role=role,
        role_confidence=role_confidence,
        business_objects=keywords[:5],
        keywords=keywords,
        summary_short=summary_short,
        summary_long=summary_long,
        evidence_chunks=evidence_chunks,
        profile_confidence=_profile_confidence(chunks, evidence_chunks, keywords),
    )


def _score_chunks(
    file: ProfileFileInput,
    chunks: tuple[ProfileChunkInput, ...],
) -> list[tuple[float, str, ProfileChunkInput]]:
    filename_terms = set(_keyword_candidates(_filename_stem(file.filename)))
    scored: list[tuple[float, str, ProfileChunkInput]] = []

    for chunk in chunks:
        score = 0.0
        sources: list[str] = []
        chunk_type = (chunk.chunk_type or "").casefold()
        text = chunk.text.strip()

        if chunk.heading:
            score += 4.0
            sources.append("heading")
        if chunk.sheet_name:
            score += 4.5
            sources.append("sheet")
        if chunk.slide_no is not None:
            score += 4.0
            sources.append("slide")
        if chunk.section_path:
            score += 2.0
            sources.append("section")
        if chunk_type in {"heading", "title"}:
            score += 3.0
            sources.append("title")
        elif chunk_type in {"sheet", "slide"}:
            score += 2.5
            sources.append(chunk_type)
        elif chunk_type in {"table", "list"}:
            score += 1.5
            sources.append(chunk_type)

        score += max(0.0, 3.0 - (chunk.chunk_index * 0.35))
        score += min(2.0, max(0, chunk.token_count or _rough_token_count(text)) / 120)
        if filename_terms.intersection(_keyword_candidates(text[:300])):
            score += 1.0
            sources.append("filename_match")

        if text:
            scored.append((score, "+".join(sources) or "early_chunk", chunk))

    return sorted(scored, key=lambda item: (-item[0], item[2].chunk_index))


def _document_role(
    file: ProfileFileInput,
    chunks: tuple[ProfileChunkInput, ...],
) -> tuple[str, float]:
    ext = (file.extension or "").casefold()
    chunk_types = {(chunk.chunk_type or "").casefold() for chunk in chunks}
    has_sheet = any(chunk.sheet_name for chunk in chunks)
    has_slide = any(chunk.slide_no is not None for chunk in chunks)

    if ext in {".xlsx", ".xls", ".csv"} or "sheet" in chunk_types or has_sheet:
        return "spreadsheet", 0.86
    if ext in {".pptx", ".ppt"} or "slide" in chunk_types or has_slide:
        return "presentation_deck", 0.86
    if ext == ".pdf":
        return "reference_document", 0.78
    if ext in {".docx", ".doc"}:
        return "structured_document", 0.76
    if file.source_type:
        return f"{file.source_type}_document", 0.62
    return "local_document", 0.5


def _central_idea(
    file: ProfileFileInput,
    chunks: tuple[ProfileChunkInput, ...],
    evidence_chunks: tuple[RuleEvidenceDraft, ...],
) -> str:
    filename_label = _title_case(_filename_stem(file.filename))
    for evidence in evidence_chunks:
        title = _clean_title(evidence.heading) or _clean_title(evidence.section_path)
        if title and not _is_generic_title(title):
            if "sheet" in (evidence.source or ""):
                return _truncate(f"{filename_label} - {title}", 180)
            return _truncate(title, 180)

    for chunk in chunks:
        title = _clean_title(chunk.sheet_name) or _clean_title(chunk.heading)
        if title and not _is_generic_title(title):
            return _truncate(f"{filename_label} - {title}", 180)

    first_sentence = _first_sentence(next((chunk.text for chunk in chunks if chunk.text.strip()), ""))
    return _truncate(first_sentence or filename_label, 180)


def _summary_short(
    central_idea: str,
    chunks: tuple[ProfileChunkInput, ...],
    evidence_chunks: tuple[RuleEvidenceDraft, ...],
) -> str | None:
    if evidence_chunks:
        return _truncate(f"{central_idea}: {evidence_chunks[0].excerpt}", 260)
    first_text = next((chunk.text for chunk in chunks if chunk.text.strip()), "")
    return _truncate(first_text, 260) if first_text else None


def _summary_long(
    chunks: tuple[ProfileChunkInput, ...],
    evidence_chunks: tuple[RuleEvidenceDraft, ...],
) -> str | None:
    selected_ids = {evidence.chunk_id for evidence in evidence_chunks}
    selected = [chunk.text.strip() for chunk in chunks if chunk.chunk_id in selected_ids and chunk.text.strip()]
    if not selected:
        selected = [chunk.text.strip() for chunk in chunks[:5] if chunk.text.strip()]
    return _truncate("\n\n".join(selected), 900) if selected else None


def _extract_keywords(
    file: ProfileFileInput,
    chunks: tuple[ProfileChunkInput, ...],
    evidence_chunks: tuple[RuleEvidenceDraft, ...],
) -> tuple[str, ...]:
    weights: dict[str, tuple[str, float]] = {}
    evidence_ids = {evidence.chunk_id for evidence in evidence_chunks}

    def add_terms(value: str | None, weight: float) -> None:
        if not value:
            return
        for candidate in _keyword_candidates(value):
            normalized = candidate.casefold()
            current = weights.get(normalized)
            if current is None:
                weights[normalized] = (candidate, weight)
            else:
                weights[normalized] = (current[0], current[1] + weight)

    add_terms(_title_case(_filename_stem(file.filename)), 6.0)
    for chunk in chunks:
        structural_weight = 5.0 if chunk.chunk_id in evidence_ids else 3.0
        add_terms(chunk.heading, structural_weight)
        add_terms(chunk.sheet_name, structural_weight)
        add_terms(chunk.section_path, structural_weight - 1.0)
        if chunk.slide_no is not None:
            add_terms(f"slide {chunk.slide_no}", 1.0)
        add_terms(chunk.text[:600], 1.5 if chunk.chunk_id in evidence_ids else 0.7)

    ranked = sorted(weights.values(), key=lambda item: (-item[1], item[0].casefold()))
    return tuple(term for term, _weight in ranked[:MAX_KEYWORDS])


def _profile_confidence(
    chunks: tuple[ProfileChunkInput, ...],
    evidence_chunks: tuple[RuleEvidenceDraft, ...],
    keywords: tuple[str, ...],
) -> float:
    confidence = 0.28
    if chunks:
        confidence += 0.24
    if evidence_chunks:
        confidence += min(0.18, len(evidence_chunks) * 0.04)
    if any(evidence.heading for evidence in evidence_chunks):
        confidence += 0.08
    if any("sheet" in evidence.source or "slide" in evidence.source for evidence in evidence_chunks):
        confidence += 0.08
    if len(keywords) >= 5:
        confidence += 0.06
    return round(min(confidence, 0.92), 3)


def _filename_stem(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip() or filename


def _clean_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.split()).strip(":-")
    return cleaned or None


def _is_generic_title(value: str) -> bool:
    return value.casefold() in {"sheet", "summary", "slide", "untitled"}


def _title_case(value: str) -> str:
    if not value:
        return value
    if any("\u4e00" <= char <= "\u9fff" for char in value):
        return value
    return " ".join(part.capitalize() if part.islower() else part for part in value.split())


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    match = re.search(r"[.!?\n。！？]", cleaned)
    if match:
        return cleaned[: match.start()].strip()
    return cleaned


def _keyword_candidates(value: str) -> tuple[str, ...]:
    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", value)
    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        term = candidate.strip("_-")
        normalized = term.casefold()
        if not term or normalized in _STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(term)
    return tuple(terms)


def _rough_token_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", text.strip()) if part])


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
    "sheet",
    "slide",
    "the",
    "with",
}
