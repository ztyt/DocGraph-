from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from docgraph_sidecar.parser.base import (
    BaseParser,
    ParsedChunk,
    ParsedDocumentElement,
    ParseContext,
    ParseResult,
)


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str
    had_replacement: bool = False


@dataclass(frozen=True)
class TextBlock:
    block_type: str
    text: str
    heading: str | None
    section_path: str | None
    start_offset: int
    end_offset: int


class TextMarkdownParser(BaseParser):
    name = "text-markdown"
    supported_extensions = (".txt", ".md", ".markdown")
    supported_source_types = ("text",)

    def parse(self, context: ParseContext) -> ParseResult:
        decoded = decode_text(context.path.read_bytes())
        blocks = split_text_blocks(decoded.text, markdown=context.extension in {".md", ".markdown"})
        warnings: list[str] = []
        if decoded.had_replacement:
            warnings.append(f"Decoded with replacement characters using {decoded.encoding}.")
        if not blocks:
            warnings.append("No parseable text blocks found.")

        elements: list[ParsedDocumentElement] = []
        chunks: list[ParsedChunk] = []
        for index, block in enumerate(blocks):
            element_id = stable_parse_id(context.file_id, "element", index, block.text)
            chunk_id = stable_parse_id(context.file_id, "chunk", index, block.text)
            elements.append(
                ParsedDocumentElement(
                    element_id=element_id,
                    file_id=context.file_id,
                    element_index=index,
                    element_type=block.block_type,
                    section_path=block.section_path,
                    text=block.text,
                    metadata={
                        "encoding": decoded.encoding,
                        "start_offset": block.start_offset,
                        "end_offset": block.end_offset,
                    },
                    confidence=1.0,
                )
            )
            chunks.append(
                ParsedChunk(
                    chunk_id=chunk_id,
                    file_id=context.file_id,
                    element_id=element_id,
                    chunk_index=index,
                    chunk_type=block.block_type,
                    heading=block.heading,
                    section_path=block.section_path,
                    text=block.text,
                    token_count=estimate_token_count(block.text),
                    start_offset=block.start_offset,
                    end_offset=block.end_offset,
                    evidence={"parser": self.name, "encoding": decoded.encoding},
                )
            )

        return ParseResult(
            parser_name=self.name,
            file_id=context.file_id,
            elements=tuple(elements),
            chunks=tuple(chunks),
            warnings=tuple(warnings),
        )


def decode_text(raw: bytes) -> DecodedText:
    if raw.startswith(b"\xef\xbb\xbf"):
        return DecodedText(raw.decode("utf-8-sig"), "utf-8-sig")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return DecodedText(raw.decode("utf-16"), "utf-16")

    for encoding in ("utf-8", "gb18030", "cp1252"):
        try:
            return DecodedText(raw.decode(encoding), encoding)
        except UnicodeDecodeError:
            continue

    return DecodedText(raw.decode("utf-8", errors="replace"), "utf-8", had_replacement=True)


def split_text_blocks(text: str, *, markdown: bool) -> tuple[TextBlock, ...]:
    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []
    paragraph_lines: list[str] = []
    paragraph_start: int | None = None
    offset = 0

    def flush_paragraph(end_offset: int) -> None:
        nonlocal paragraph_lines, paragraph_start
        paragraph = "\n".join(line.strip() for line in paragraph_lines).strip()
        if paragraph and paragraph_start is not None:
            blocks.append(
                TextBlock(
                    block_type="paragraph",
                    text=paragraph,
                    heading=heading_stack[-1][1] if heading_stack else None,
                    section_path=_section_path(heading_stack),
                    start_offset=paragraph_start,
                    end_offset=end_offset,
                )
            )
        paragraph_lines = []
        paragraph_start = None

    for line in text.splitlines(keepends=True):
        raw_line = line.rstrip("\r\n")
        line_start = offset
        line_end = offset + len(line)
        offset = line_end

        match = HEADING_PATTERN.match(raw_line) if markdown else None
        if match:
            flush_paragraph(line_start)
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack = [item for item in heading_stack if item[0] < level]
            heading_stack.append((level, title))
            blocks.append(
                TextBlock(
                    block_type="heading",
                    text=title,
                    heading=title,
                    section_path=_section_path(heading_stack),
                    start_offset=line_start,
                    end_offset=line_end,
                )
            )
            continue

        if raw_line.strip() == "":
            flush_paragraph(line_start)
            continue

        if paragraph_start is None:
            paragraph_start = line_start
        paragraph_lines.append(raw_line)

    flush_paragraph(len(text))
    return tuple(blocks)


def stable_parse_id(file_id: str, kind: str, index: int, text: str) -> str:
    digest = hashlib.sha256(f"{file_id}:{kind}:{index}:{text}".encode("utf-8")).hexdigest()
    return f"{kind}-{digest[:24]}"


def estimate_token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _section_path(stack: list[tuple[int, str]]) -> str | None:
    if not stack:
        return None
    return " > ".join(title for _, title in stack)
