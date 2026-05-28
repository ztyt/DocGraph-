from __future__ import annotations

import hashlib
import re
from typing import Iterable

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from docgraph_sidecar.parser.base import (
    BaseParser,
    ParsedChunk,
    ParsedDocumentElement,
    ParseContext,
    ParseResult,
    ParserError,
)


HEADING_STYLE_PATTERN = re.compile(r"^(?:heading|\u6807\u9898)\s*(\d+)$", re.IGNORECASE)


class DocxParser(BaseParser):
    name = "docx"
    supported_extensions = (".docx",)

    def parse(self, context: ParseContext) -> ParseResult:
        try:
            document = Document(context.path)
        except Exception as exc:
            raise ParserError(
                "DOCX file could not be parsed.",
                error_code="DOCX_PARSE_ERROR",
                parser_name=self.name,
                retryable=False,
                details={"path": str(context.path), "error_type": type(exc).__name__},
            ) from exc

        elements: list[ParsedDocumentElement] = []
        chunks: list[ParsedChunk] = []
        heading_stack: list[tuple[int, str]] = []

        for block in iter_document_blocks(document):
            if isinstance(block, Paragraph):
                text = normalize_text(block.text)
                if not text:
                    continue

                heading_level = heading_level_for_paragraph(block)
                if heading_level is not None:
                    heading_stack = [item for item in heading_stack if item[0] < heading_level]
                    heading_stack.append((heading_level, text))
                    element_type = "heading"
                    heading = text
                else:
                    element_type = "paragraph"
                    heading = heading_stack[-1][1] if heading_stack else None

                add_block(
                    elements,
                    chunks,
                    context=context,
                    block_type=element_type,
                    text=text,
                    heading=heading,
                    section_path=section_path(heading_stack),
                    metadata={"style": block.style.name if block.style else None},
                )
                continue

            if isinstance(block, Table):
                text, metadata = table_to_text(block)
                if not text:
                    continue
                add_block(
                    elements,
                    chunks,
                    context=context,
                    block_type="table",
                    text=text,
                    heading=heading_stack[-1][1] if heading_stack else None,
                    section_path=section_path(heading_stack),
                    metadata=metadata,
                )

        warnings = () if elements else ("No parseable DOCX blocks found.",)
        return ParseResult(
            parser_name=self.name,
            file_id=context.file_id,
            elements=tuple(elements),
            chunks=tuple(chunks),
            warnings=warnings,
        )


def iter_document_blocks(document: DocxDocument) -> Iterable[Paragraph | Table]:
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def add_block(
    elements: list[ParsedDocumentElement],
    chunks: list[ParsedChunk],
    *,
    context: ParseContext,
    block_type: str,
    text: str,
    heading: str | None,
    section_path: str | None,
    metadata: dict[str, object],
) -> None:
    index = len(elements)
    element_id = stable_parse_id(context.file_id, "element", index, text)
    chunk_id = stable_parse_id(context.file_id, "chunk", index, text)
    elements.append(
        ParsedDocumentElement(
            element_id=element_id,
            file_id=context.file_id,
            element_index=index,
            element_type=block_type,
            section_path=section_path,
            text=text,
            metadata=metadata,
            confidence=1.0,
        )
    )
    chunks.append(
        ParsedChunk(
            chunk_id=chunk_id,
            file_id=context.file_id,
            element_id=element_id,
            chunk_index=index,
            chunk_type=block_type,
            heading=heading,
            section_path=section_path,
            text=text,
            token_count=estimate_token_count(text),
            evidence={"parser": DocxParser.name},
        )
    )


def heading_level_for_paragraph(paragraph: Paragraph) -> int | None:
    style_name = paragraph.style.name if paragraph.style else ""
    match = HEADING_STYLE_PATTERN.match(style_name.strip())
    if match is None:
        return None
    return int(match.group(1))


def table_to_text(table: Table) -> tuple[str, dict[str, object]]:
    rows: list[str] = []
    max_columns = 0
    for row in table.rows:
        cells = [normalize_text(cell.text) for cell in row.cells]
        max_columns = max(max_columns, len(cells))
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows).strip(), {"rows": len(table.rows), "columns": max_columns}


def normalize_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\xa0", " ")).strip()


def section_path(stack: list[tuple[int, str]]) -> str | None:
    if not stack:
        return None
    return " > ".join(title for _, title in stack)


def stable_parse_id(file_id: str, kind: str, index: int, text: str) -> str:
    digest = hashlib.sha256(f"{file_id}:{kind}:{index}:{text}".encode("utf-8")).hexdigest()
    return f"{kind}-{digest[:24]}"


def estimate_token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))
