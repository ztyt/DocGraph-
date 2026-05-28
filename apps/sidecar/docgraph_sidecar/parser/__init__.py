"""Parser contracts and registry for DocGraph document parsers."""

from docgraph_sidecar.parser.base import (
    BaseParser,
    ParsedChunk,
    ParsedDocumentElement,
    ParseContext,
    ParseResult,
    ParserError,
)
from docgraph_sidecar.parser.docx import DocxParser
from docgraph_sidecar.parser.errors import parse_with_error_recording, record_parse_error
from docgraph_sidecar.parser.pptx import PptxParser
from docgraph_sidecar.parser.registry import ParserRegistry, ParserRegistryError, default_parser_registry
from docgraph_sidecar.parser.text import TextMarkdownParser
from docgraph_sidecar.parser.xlsx import XlsxParser

__all__ = [
    "BaseParser",
    "ParsedChunk",
    "ParsedDocumentElement",
    "ParseContext",
    "ParseResult",
    "ParserError",
    "DocxParser",
    "PptxParser",
    "ParserRegistry",
    "ParserRegistryError",
    "TextMarkdownParser",
    "XlsxParser",
    "default_parser_registry",
    "parse_with_error_recording",
    "record_parse_error",
]
