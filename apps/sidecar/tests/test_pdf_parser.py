import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz

from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.parser import (
    ParseContext,
    ParserError,
    PdfParser,
    default_parser_registry,
    parse_with_error_recording,
)


class PdfParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.parser = PdfParser()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pdf_parser_extracts_page_blocks(self) -> None:
        path = self.root / "brief.pdf"
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Alpha Project PDF brief.")
        page.insert_text((72, 100), "Second block.")
        document.save(path)
        document.close()

        result = self.parser.parse(ParseContext.from_path(path, file_id="file-pdf"))

        self.assertEqual(result.parser_name, "pdf")
        self.assertGreaterEqual(len(result.elements), 1)
        self.assertEqual(result.elements[0].element_type, "pdf_block")
        self.assertEqual(result.elements[0].page_no, 1)
        self.assertIn("Alpha Project PDF brief", result.chunks[0].text)
        self.assertFalse(result.metadata["pdf_profile"]["ocr_needed"])
        self.assertFalse(result.chunks[0].evidence["ocr_performed"])
        self.assertIn("bbox", result.elements[0].metadata)

    def test_scanned_pdf_marks_ocr_needed_without_ocr(self) -> None:
        path = self.root / "blank.pdf"
        document = fitz.open()
        document.new_page()
        document.save(path)
        document.close()

        result = self.parser.parse(ParseContext.from_path(path, file_id="file-blank"))

        self.assertEqual(result.elements, ())
        self.assertEqual(result.chunks, ())
        self.assertEqual(result.warnings, ("No text blocks found; OCR is needed.",))
        self.assertTrue(result.metadata["pdf_profile"]["ocr_needed"])
        self.assertFalse(result.metadata["pdf_profile"]["ocr_performed"])

    def test_basic_fixture_pdf_can_be_parsed(self) -> None:
        path = Path("fixtures/basic_docs/alpha_brief.pdf")

        result = self.parser.parse(ParseContext.from_path(path, file_id="file-fixture"))

        self.assertEqual(result.elements[0].page_no, 1)
        self.assertIn("Alpha Project PDF brief", result.chunks[0].text)

    def test_default_registry_selects_pdf_parser(self) -> None:
        path = self.root / "simple.pdf"
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Simple PDF")
        document.save(path)
        document.close()

        result = default_parser_registry().parse_path(path, file_id="file-registry")

        self.assertEqual(result.parser_name, "pdf")
        self.assertIn("Simple PDF", result.chunks[0].text)

    def test_bad_pdf_records_parse_error(self) -> None:
        data_dir = self.root / "data"
        bad_path = self.root / "bad.pdf"
        bad_path.write_bytes(b"not a pdf")
        initialize_database(data_dir=data_dir)
        self._insert_file(data_dir, "file-bad", str(bad_path))
        context = ParseContext.from_path(bad_path, file_id="file-bad")

        with self.assertRaises(ParserError):
            parse_with_error_recording(default_parser_registry(), context, data_dir=data_dir)

        connection = connect(data_dir=data_dir)
        try:
            row = connection.execute(
                """
                SELECT error_code, error_message, parser_name, retryable, details_json
                FROM parse_errors
                WHERE file_id = 'file-bad'
                """
            ).fetchone()
        finally:
            connection.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["error_code"], "PDF_PARSE_ERROR")
        self.assertEqual(row["parser_name"], "pdf")
        self.assertEqual(row["retryable"], 0)
        self.assertEqual(row["error_message"], "PDF file could not be parsed.")
        self.assertEqual(json.loads(row["details_json"])["path"], str(bad_path))

    def _insert_file(self, data_dir: Path, file_id: str, path: str) -> None:
        connection = connect(data_dir=data_dir)
        try:
            connection.execute(
                """
                INSERT INTO files (
                  file_id,
                  path,
                  normalized_path,
                  filename,
                  extension,
                  source_type,
                  file_status,
                  parse_status,
                  deleted_flag
                )
                VALUES (?, ?, ?, ?, '.pdf', 'pdf', 'discovered', 'pending', 0)
                """,
                (file_id, path, path.casefold(), Path(path).name),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
