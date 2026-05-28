import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.parser import ChunkingOptions, ParsedDocumentElement, build_chunks
from docgraph_sidecar.parser.structure_chunker import split_text


class StructureChunkerTest(unittest.TestCase):
    def test_build_chunks_preserves_structural_fields_and_evidence(self) -> None:
        element = ParsedDocumentElement(
            element_id="element-1",
            file_id="file-1",
            element_index=3,
            element_type="pdf_block",
            page_no=2,
            sheet_name="Budget",
            slide_no=4,
            section_path="Alpha > Budget",
            bbox={"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0},
            text="Budget paragraph text.",
            metadata={"parser": "test"},
        )

        chunks = build_chunks([element])

        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertTrue(chunk.chunk_id.startswith("chunk-"))
        self.assertEqual(chunk.file_id, "file-1")
        self.assertEqual(chunk.element_id, "element-1")
        self.assertEqual(chunk.chunk_index, 0)
        self.assertEqual(chunk.chunk_type, "pdf_block")
        self.assertEqual(chunk.page_no, 2)
        self.assertEqual(chunk.sheet_name, "Budget")
        self.assertEqual(chunk.slide_no, 4)
        self.assertEqual(chunk.section_path, "Alpha > Budget")
        self.assertEqual(chunk.heading, "Budget")
        self.assertEqual(chunk.text, "Budget paragraph text.")
        self.assertEqual(chunk.token_count, 3)
        self.assertEqual(chunk.evidence["source"], "structure_chunker")
        self.assertEqual(chunk.evidence["element_index"], 3)
        self.assertEqual(chunk.evidence["bbox"], {"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0})
        self.assertEqual(chunk.evidence["metadata"], {"parser": "test"})

    def test_heading_element_uses_text_as_heading(self) -> None:
        element = ParsedDocumentElement(
            element_id="element-heading",
            file_id="file-1",
            element_index=0,
            element_type="heading",
            text="Alpha Project",
        )

        chunks = build_chunks([element])

        self.assertEqual(chunks[0].heading, "Alpha Project")
        self.assertEqual(chunks[0].chunk_type, "heading")

    def test_empty_text_is_skipped(self) -> None:
        element = ParsedDocumentElement(
            element_id="element-empty",
            file_id="file-1",
            element_index=0,
            element_type="paragraph",
            text="   ",
        )

        self.assertEqual(build_chunks([element]), ())

    def test_long_text_splits_into_multiple_chunks_with_segment_evidence(self) -> None:
        text = "Alpha sentence. " * 50
        element = ParsedDocumentElement(
            element_id="element-long",
            file_id="file-1",
            element_index=0,
            element_type="paragraph",
            text=text,
        )

        chunks = build_chunks([element], options=ChunkingOptions(max_chars=160))

        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))
        self.assertEqual(chunks[0].evidence["segment_index"], 0)
        self.assertEqual(chunks[-1].evidence["segment_count"], len(chunks))
        self.assertTrue(all(len(chunk.text) <= 160 for chunk in chunks))

    def test_chunk_ids_are_stable_for_same_input(self) -> None:
        element = ParsedDocumentElement(
            element_id="element-1",
            file_id="file-1",
            element_index=0,
            element_type="paragraph",
            text="Stable text.",
        )

        first = build_chunks([element])
        second = build_chunks([element])

        self.assertEqual(first[0].chunk_id, second[0].chunk_id)

    def test_split_text_prefers_sentence_boundaries(self) -> None:
        segments = split_text("One sentence. Two sentence. Three sentence.", max_chars=28)

        self.assertEqual(segments[0], "One sentence. Two sentence.")
        self.assertEqual(segments[1], "Three sentence.")

    def test_invalid_max_chars_errors(self) -> None:
        with self.assertRaises(ValueError):
            build_chunks([], options=ChunkingOptions(max_chars=20))


if __name__ == "__main__":
    unittest.main()
