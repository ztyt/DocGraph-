import json
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "fixtures" / "basic_docs"
GENERATOR = ROOT / "scripts" / "generate-basic-fixtures.py"


class BasicFixtureGeneratorTest(unittest.TestCase):
    def test_generator_creates_expected_files(self) -> None:
        subprocess.run([sys.executable, str(GENERATOR)], check=True, cwd=ROOT)

        expected_files = {
            "README.md",
            "alpha_notes.txt",
            "alpha_contract.docx",
            "alpha_budget.xlsx",
            "alpha_status.pptx",
            "alpha_brief.pdf",
            "empty.txt",
            "bad_file.bin",
            "expected_search.json",
        }
        actual_files = {path.name for path in FIXTURE_DIR.iterdir()}

        self.assertEqual(actual_files, expected_files)
        self.assertEqual((FIXTURE_DIR / "empty.txt").read_text(encoding="utf-8"), "")
        self.assertTrue((FIXTURE_DIR / "alpha_brief.pdf").read_bytes().startswith(b"%PDF-1.4"))

    def test_office_fixtures_are_valid_zip_packages(self) -> None:
        subprocess.run([sys.executable, str(GENERATOR)], check=True, cwd=ROOT)

        office_files = {
            "alpha_contract.docx": "word/document.xml",
            "alpha_budget.xlsx": "xl/worksheets/sheet1.xml",
            "alpha_status.pptx": "ppt/slides/slide1.xml",
        }

        for filename, required_member in office_files.items():
            with self.subTest(filename=filename):
                with zipfile.ZipFile(FIXTURE_DIR / filename) as archive:
                    self.assertIn("[Content_Types].xml", archive.namelist())
                    self.assertIn(required_member, archive.namelist())

    def test_expected_search_manifest_matches_fixture_files(self) -> None:
        subprocess.run([sys.executable, str(GENERATOR)], check=True, cwd=ROOT)

        manifest = json.loads((FIXTURE_DIR / "expected_search.json").read_text(encoding="utf-8"))
        fixture_names = {path.name for path in FIXTURE_DIR.iterdir()}
        referenced = set(manifest["non_parseable_files"])
        for query in manifest["queries"]:
            referenced.update(query["expected_files"])

        self.assertTrue(referenced.issubset(fixture_names))
        self.assertEqual(manifest["fixture_group"], "basic_docs")


if __name__ == "__main__":
    unittest.main()

