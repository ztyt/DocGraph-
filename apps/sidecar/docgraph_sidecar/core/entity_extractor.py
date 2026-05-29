from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class EntityExtractionChunk:
    chunk_id: str
    text: str


@dataclass(frozen=True)
class EntityCandidate:
    entity_id: str
    entity_text: str
    normalized_text: str
    entity_type: str
    entity_confidence: float
    evidence_chunk_id: str
    evidence_text: str
    evidence_confidence: float


def extract_rule_entities(chunks: tuple[EntityExtractionChunk, ...]) -> tuple[EntityCandidate, ...]:
    candidates: list[EntityCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        for entity_type, text, confidence, start, end in _extract_from_text(chunk.text):
            normalized = normalize_entity_text(text, entity_type)
            key = (entity_type, normalized, chunk.chunk_id)
            if not normalized or key in seen:
                continue
            seen.add(key)
            candidates.append(
                EntityCandidate(
                    entity_id=stable_entity_id(entity_type, normalized),
                    entity_text=_clean_entity_text(text),
                    normalized_text=normalized,
                    entity_type=entity_type,
                    entity_confidence=confidence,
                    evidence_chunk_id=chunk.chunk_id,
                    evidence_text=_evidence_excerpt(chunk.text, start, end),
                    evidence_confidence=max(0.5, min(0.99, confidence - 0.03)),
                )
            )
    return tuple(candidates)


def stable_entity_id(entity_type: str, normalized_text: str) -> str:
    digest = sha256(f"{entity_type}:{normalized_text}".encode("utf-8")).hexdigest()
    return f"entity-{entity_type.casefold()}-{digest[:20]}"


def normalize_entity_text(value: str, entity_type: str) -> str:
    cleaned = _clean_entity_text(value)
    if entity_type == "MONEY":
        return cleaned.replace(",", "").casefold()
    if entity_type == "DATE":
        return _normalize_date(cleaned)
    if entity_type == "ID_CODE":
        return cleaned.upper()
    return cleaned.casefold()


def _extract_from_text(text: str) -> list[tuple[str, str, float, int, int]]:
    matches: list[tuple[str, str, float, int, int]] = []
    for entity_type, pattern, confidence in _PATTERNS:
        for match in pattern.finditer(text):
            value = _select_match_text(match)
            if not _is_valid_candidate(entity_type, value):
                continue
            start, end = match.span()
            matches.append((entity_type, value, confidence, start, end))
    return matches


def _select_match_text(match: re.Match[str]) -> str:
    for value in match.groups():
        if value:
            return value
    return match.group(0)


def _is_valid_candidate(entity_type: str, value: str) -> bool:
    cleaned = _clean_entity_text(value)
    if len(cleaned) < 2:
        return False
    if entity_type == "ID_CODE" and not any(char.isdigit() for char in cleaned):
        return False
    if entity_type in {"PROJECT", "ORG", "LOCATION", "DEVICE"} and cleaned.casefold() in _STOPWORDS:
        return False
    return True


def _clean_entity_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip(" ,.;:()[]{}<>，。；：、")


def _normalize_date(value: str) -> str:
    cleaned = _clean_entity_text(value)
    ymd = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", cleaned)
    if ymd:
        return f"{ymd.group(1)}-{int(ymd.group(2)):02d}-{int(ymd.group(3)):02d}"
    chinese = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", cleaned)
    if chinese:
        return f"{chinese.group(1)}-{int(chinese.group(2)):02d}-{int(chinese.group(3)):02d}"
    return cleaned.casefold()


def _evidence_excerpt(text: str, start: int, end: int, *, radius: int = 70) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    excerpt = _clean_entity_text(text[left:right])
    if left > 0:
        excerpt = f"...{excerpt}"
    if right < len(text):
        excerpt = f"{excerpt}..."
    return excerpt


_PROJECT_WORD = r"(?:Project|Program|Initiative|工程|项目|专项|课题)"
_ORG_WORD = r"(?:Center|Centre|Department|Division|Team|Company|Corp|Inc|Ltd|LLC|Group|中心|部门|公司|集团|团队)"
_LOCATION_WORD = r"(?:City|County|District|Park|Plant|Site|Warehouse|Office|Room|Zone|市|县|区|园区|厂区|仓库|办公室|机房)"
_DEVICE_WORD = (
    r"(?:camera|switch|router|server|sensor|pump|valve|cable|gateway|controller|"
    r"相机|摄像头|交换机|路由器|服务器|传感器|泵|阀|线缆|网关|控制器|设备)"
)

_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    (
        "PROJECT",
        re.compile(rf"\b([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*){{0,4}}\s+{_PROJECT_WORD})\b"),
        0.88,
    ),
    ("PROJECT", re.compile(rf"([\u4e00-\u9fffA-Za-z0-9_-]{{2,24}}{_PROJECT_WORD})"), 0.86),
    (
        "ORG",
        re.compile(rf"\b([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*){{0,4}}\s+{_ORG_WORD})\b"),
        0.84,
    ),
    ("ORG", re.compile(rf"([\u4e00-\u9fffA-Za-z0-9_-]{{2,24}}{_ORG_WORD})"), 0.82),
    (
        "LOCATION",
        re.compile(rf"\b([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*){{0,4}}\s+{_LOCATION_WORD})\b"),
        0.78,
    ),
    ("LOCATION", re.compile(rf"([\u4e00-\u9fffA-Za-z0-9_-]{{2,24}}{_LOCATION_WORD})"), 0.78),
    ("DEVICE", re.compile(rf"\b({_DEVICE_WORD}(?:\s+[A-Za-z0-9_-]+)?)\b", re.IGNORECASE), 0.76),
    ("DEVICE", re.compile(rf"({_DEVICE_WORD})"), 0.76),
    ("MONEY", re.compile(r"((?:[$¥￥]|RMB\s*)\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:元|万元|USD|CNY))", re.IGNORECASE), 0.9),
    ("DATE", re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日?)"), 0.88),
    ("ID_CODE", re.compile(r"\b([A-Z]{2,}[A-Z0-9]*-\d{2,}(?:-\d{1,})?)\b"), 0.82),
)

_STOPWORDS = {
    "project",
    "program",
    "center",
    "company",
    "device",
}
