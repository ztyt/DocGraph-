"""Parser contracts and registry for DocGraph document parsers."""

from docgraph_sidecar.parser.base import (
    BaseParser,
    ParsedChunk,
    ParsedDocumentElement,
    ParseContext,
    ParseResult,
)
from docgraph_sidecar.parser.registry import ParserRegistry, ParserRegistryError, default_parser_registry
from docgraph_sidecar.parser.text import TextMarkdownParser

__all__ = [
    "BaseParser",
    "ParsedChunk",
    "ParsedDocumentElement",
    "ParseContext",
    "ParseResult",
    "ParserRegistry",
    "ParserRegistryError",
    "TextMarkdownParser",
    "default_parser_registry",
]
