from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import fitz

from docgraph_sidecar.parser.base import (
    BaseParser,
    ParsedChunk,
    ParsedDocumentElement,
    ParseContext,
    ParseResult,
    ParserError,
)


@dataclass(frozen=True)
class PdfBlock:
    page_no: int
    block_index: int
    text: str
    bbox: dict[str, float]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "page_no": self.page_no,
            "block_index": self.block_index,
            "bbox": self.bbox,
        }


class PdfParser(BaseParser):
    name = "pdf"
    supported_extensions = (".pdf",)

    def parse(self, context: ParseContext) -> ParseResult:
        try:
            document = fitz.open(context.path)
        except Exception as exc:
            raise ParserError(
                "PDF file could not be parsed.",
                error_code="PDF_PARSE_ERROR",
                parser_name=self.name,
                retryable=False,
                details={"path": str(context.path), "error_type": type(exc).__name__},
            ) from exc

        elements: list[ParsedDocumentElement] = []
        chunks: list[ParsedChunk] = []
        blocks: list[PdfBlock] = []
        try:
            for page_index, page in enumerate(document, start=1):
                for block_index, raw_block in enumerate(page.get_text("blocks")):
                    block = pdf_block_from_raw(raw_block, page_no=page_index, block_index=block_index)
                    if block is None:
                        continue
                    blocks.append(block)
                    add_pdf_block(elements, chunks, context=context, block=block)
        finally:
            document.close()

        ocr_needed = len(blocks) == 0
        warnings = ("No text blocks found; OCR is needed.",) if ocr_needed else ()
        return ParseResult(
            parser_name=self.name,
            file_id=context.file_id,
            elements=tuple(elements),
            chunks=tuple(chunks),
            warnings=warnings,
            metadata={
                "pdf_profile": {
                    "page_count": len({block.page_no for block in blocks}),
                    "text_block_count": len(blocks),
                    "ocr_needed": ocr_needed,
                    "ocr_performed": False,
                }
            },
        )


def pdf_block_from_raw(raw_block: tuple[Any, ...], *, page_no: int, block_index: int) -> PdfBlock | None:
    if len(raw_block) < 5:
        return None
    text = normalize_text(str(raw_block[4]))
    if not text:
        return None
    return PdfBlock(
        page_no=page_no,
        block_index=block_index,
        text=text,
        bbox={
            "x0": float(raw_block[0]),
            "y0": float(raw_block[1]),
            "x1": float(raw_block[2]),
            "y1": float(raw_block[3]),
        },
    )


def add_pdf_block(
    elements: list[ParsedDocumentElement],
    chunks: list[ParsedChunk],
    *,
    context: ParseContext,
    block: PdfBlock,
) -> None:
    index = len(elements)
    element_id = stable_parse_id(context.file_id, "element", index, block.text)
    chunk_id = stable_parse_id(context.file_id, "chunk", index, block.text)
    elements.append(
        ParsedDocumentElement(
            element_id=element_id,
            file_id=context.file_id,
            element_index=index,
            element_type="pdf_block",
            page_no=block.page_no,
            bbox=block.bbox,
            text=block.text,
            metadata=block.to_metadata(),
            confidence=1.0,
        )
    )
    chunks.append(
        ParsedChunk(
            chunk_id=chunk_id,
            file_id=context.file_id,
            element_id=element_id,
            chunk_index=index,
            chunk_type="pdf_block",
            page_no=block.page_no,
            text=block.text,
            token_count=estimate_token_count(block.text),
            evidence={"parser": PdfParser.name, "bbox": block.bbox, "ocr_performed": False},
        )
    )


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def stable_parse_id(file_id: str, kind: str, index: int, text: str) -> str:
    digest = hashlib.sha256(f"{file_id}:{kind}:{index}:{text}".encode("utf-8")).hexdigest()
    return f"{kind}-{digest[:24]}"


def estimate_token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))
