import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.parser import (
    BaseParser,
    ParsedChunk,
    ParsedDocumentElement,
    ParseContext,
    ParseResult,
    ParserRegistry,
    ParserRegistryError,
    default_parser_registry,
)
from docgraph_sidecar.parser.base import normalize_extension


class DummyTextParser(BaseParser):
    name = "dummy-text"
    supported_extensions = ("txt", ".md")
    supported_source_types = ("text",)

    def parse(self, context: ParseContext) -> ParseResult:
        element = ParsedDocumentElement(
            element_id=f"{context.file_id}-element-0",
            file_id=context.file_id,
            element_index=0,
            element_type="paragraph",
            text="hello world",
        )
        chunk = ParsedChunk(
            chunk_id=f"{context.file_id}-chunk-0",
            file_id=context.file_id,
            element_id=element.element_id,
            chunk_index=0,
            chunk_type="paragraph",
            text="hello world",
            token_count=2,
        )
        return ParseResult(
            parser_name=self.name,
            file_id=context.file_id,
            elements=(element,),
            chunks=(chunk,),
        )


class DummyPdfParser(BaseParser):
    name = "dummy-pdf"
    supported_extensions = (".pdf",)

    def parse(self, context: ParseContext) -> ParseResult:
        return ParseResult(parser_name=self.name, file_id=context.file_id)


class ParserRegistryTest(unittest.TestCase):
    def test_register_and_select_by_normalized_extension(self) -> None:
        registry = ParserRegistry([DummyTextParser()])

        parser = registry.get_for_extension("MD")

        self.assertIsInstance(parser, DummyTextParser)
        self.assertEqual(parser.normalized_extensions, (".txt", ".md"))

    def test_select_falls_back_to_source_type(self) -> None:
        registry = ParserRegistry([DummyTextParser()])
        context = ParseContext.from_path("notes.unknown", file_id="file-1", source_type="text")

        parser = registry.select(context)

        self.assertIsInstance(parser, DummyTextParser)

    def test_parse_returns_elements_and_chunks_without_database_write_contract(self) -> None:
        registry = ParserRegistry([DummyTextParser()])
        result = registry.parse_path("notes.txt", file_id="file-1", source_type="text")

        self.assertEqual(result.parser_name, "dummy-text")
        self.assertEqual(result.file_id, "file-1")
        self.assertEqual(result.elements[0].to_dict()["element_type"], "paragraph")
        self.assertEqual(result.chunks[0].to_dict()["text"], "hello world")

    def test_duplicate_extensions_are_rejected(self) -> None:
        registry = ParserRegistry([DummyTextParser()])

        with self.assertRaises(ParserRegistryError):
            registry.register(DummyTextParser())

    def test_require_errors_when_no_parser_matches(self) -> None:
        registry = ParserRegistry([DummyPdfParser()])
        context = ParseContext.from_path("notes.txt", file_id="file-1")

        with self.assertRaises(ParserRegistryError):
            registry.require(context)

    def test_list_returns_stable_registration_metadata(self) -> None:
        registry = ParserRegistry([DummyPdfParser(), DummyTextParser()])

        registrations = [item.to_dict() for item in registry.list()]

        self.assertEqual([item["name"] for item in registrations], ["dummy-pdf", "dummy-text"])
        self.assertEqual(registrations[1]["extensions"], [".txt", ".md"])
        self.assertEqual(registrations[1]["source_types"], ["text"])

    def test_normalize_extension_accepts_bare_or_dotted_values(self) -> None:
        self.assertEqual(normalize_extension("TXT"), ".txt")
        self.assertEqual(normalize_extension(".md"), ".md")
        self.assertEqual(normalize_extension(""), "")

    def test_default_registry_includes_text_markdown_parser(self) -> None:
        registry = default_parser_registry()

        self.assertEqual(registry.get_for_extension(".txt").name, "text-markdown")
        self.assertEqual(registry.get_for_extension("md").name, "text-markdown")
        self.assertEqual(registry.get_for_extension("docx").name, "docx")
        self.assertEqual(registry.get_for_extension("xlsx").name, "xlsx")
        self.assertEqual(registry.get_for_extension("pptx").name, "pptx")


if __name__ == "__main__":
    unittest.main()
