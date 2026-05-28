import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.parser import ParseContext, TextMarkdownParser, default_parser_registry
from docgraph_sidecar.parser.text import decode_text, estimate_token_count, split_text_blocks


class TextMarkdownParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.parser = TextMarkdownParser()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_markdown_headings_and_paragraphs_become_elements_and_chunks(self) -> None:
        path = self.root / "notes.md"
        path.write_text(
            "# Alpha Project\n\nKickoff notes for local search.\n\n## Budget\n\nOwner: North Center.\n",
            encoding="utf-8",
        )
        context = ParseContext.from_path(path, file_id="file-alpha", source_type="text")

        result = self.parser.parse(context)

        self.assertEqual(result.parser_name, "text-markdown")
        self.assertEqual([element.element_type for element in result.elements], [
            "heading",
            "paragraph",
            "heading",
            "paragraph",
        ])
        self.assertEqual(result.elements[0].text, "Alpha Project")
        self.assertEqual(result.elements[2].section_path, "Alpha Project > Budget")
        self.assertEqual(result.chunks[3].heading, "Budget")
        self.assertEqual(result.chunks[3].section_path, "Alpha Project > Budget")
        self.assertEqual(result.chunks[3].text, "Owner: North Center.")
        self.assertEqual(result.chunks[3].token_count, 3)

    def test_txt_parser_splits_blank_line_paragraphs(self) -> None:
        path = self.root / "plain.txt"
        path.write_text("First paragraph line one.\nline two.\n\nSecond paragraph.", encoding="utf-8")
        context = ParseContext.from_path(path, file_id="file-plain", source_type="text")

        result = self.parser.parse(context)

        self.assertEqual(len(result.elements), 2)
        self.assertEqual(result.elements[0].element_type, "paragraph")
        self.assertEqual(result.elements[0].text, "First paragraph line one.\nline two.")
        self.assertIsNone(result.elements[0].section_path)
        self.assertEqual(result.chunks[1].text, "Second paragraph.")

    def test_decode_text_handles_utf8_bom(self) -> None:
        decoded = decode_text(b"\xef\xbb\xbfhello")

        self.assertEqual(decoded.text, "hello")
        self.assertEqual(decoded.encoding, "utf-8-sig")

    def test_decode_text_handles_gb18030(self) -> None:
        raw = "北方中心预算".encode("gb18030")

        decoded = decode_text(raw)

        self.assertEqual(decoded.text, "北方中心预算")
        self.assertEqual(decoded.encoding, "gb18030")

    def test_empty_text_returns_warning_without_chunks(self) -> None:
        path = self.root / "empty.txt"
        path.write_text("", encoding="utf-8")
        context = ParseContext.from_path(path, file_id="file-empty", source_type="text")

        result = self.parser.parse(context)

        self.assertEqual(result.elements, ())
        self.assertEqual(result.chunks, ())
        self.assertEqual(result.warnings, ("No parseable text blocks found.",))

    def test_default_registry_selects_text_markdown_parser(self) -> None:
        registry = default_parser_registry()
        path = self.root / "notes.txt"
        path.write_text("hello", encoding="utf-8")

        result = registry.parse_path(path, file_id="file-default", source_type="text")

        self.assertEqual(result.parser_name, "text-markdown")
        self.assertEqual(result.chunks[0].text, "hello")

    def test_split_text_blocks_exposes_offsets(self) -> None:
        blocks = split_text_blocks("# Title\n\nBody text\n", markdown=True)

        self.assertEqual(blocks[0].start_offset, 0)
        self.assertEqual(blocks[0].end_offset, 8)
        self.assertEqual(blocks[1].start_offset, 9)
        self.assertEqual(blocks[1].end_offset, 19)

    def test_estimate_token_count_counts_non_empty_segments(self) -> None:
        self.assertEqual(estimate_token_count("alpha  beta\n\n gamma"), 3)


if __name__ == "__main__":
    unittest.main()
