import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.core.db import connect
from docgraph_sidecar.scanner.metadata import (
    file_id_for_path,
    normalize_path,
    scan_directory_to_db,
    source_type_for_extension,
)


class MetadataScannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "docs"
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scan_directory_writes_file_metadata_and_skips_ignored_paths(self) -> None:
        (self.root / "alpha.txt").write_text("alpha project", encoding="utf-8")
        (self.root / "report.PDF").write_bytes(b"%PDF-1.4\n")
        (self.root / "Thumbs.db").write_text("skip", encoding="utf-8")
        (self.root / "notes.tmp").write_text("skip", encoding="utf-8")
        ignored_dir = self.root / "node_modules"
        ignored_dir.mkdir()
        (ignored_dir / "skip.js").write_text("skip", encoding="utf-8")

        result = scan_directory_to_db(self.root, data_dir=self.data_dir)

        self.assertEqual(result.discovered_count, 2)
        self.assertEqual(result.ignored_count, 3)
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.written_count, 2)

        connection = connect(data_dir=self.data_dir)
        try:
            rows = connection.execute(
                "SELECT filename, extension, source_type, sha256, parse_status FROM files ORDER BY filename"
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(
            [(row["filename"], row["extension"], row["source_type"], row["sha256"], row["parse_status"]) for row in rows],
            [
                ("alpha.txt", ".txt", "text", None, "pending"),
                ("report.PDF", ".pdf", "pdf", None, "pending"),
            ],
        )

    def test_optional_sha256_is_written_when_enabled(self) -> None:
        target = self.root / "alpha.txt"
        target.write_text("alpha project", encoding="utf-8")

        scan_directory_to_db(self.root, data_dir=self.data_dir, compute_hash=True)

        expected_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        connection = connect(data_dir=self.data_dir)
        try:
            row = connection.execute("SELECT sha256 FROM files WHERE filename = 'alpha.txt'").fetchone()
        finally:
            connection.close()

        self.assertEqual(row["sha256"], expected_hash)

    def test_rescan_updates_existing_row_instead_of_duplicating(self) -> None:
        target = self.root / "alpha.txt"
        target.write_text("old", encoding="utf-8")
        scan_directory_to_db(self.root, data_dir=self.data_dir, compute_hash=True)

        target.write_text("new content", encoding="utf-8")
        scan_directory_to_db(self.root, data_dir=self.data_dir, compute_hash=True)

        connection = connect(data_dir=self.data_dir)
        try:
            count = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            row = connection.execute("SELECT size_bytes, sha256 FROM files").fetchone()
        finally:
            connection.close()

        self.assertEqual(count, 1)
        self.assertEqual(row["size_bytes"], len("new content"))
        self.assertEqual(row["sha256"], hashlib.sha256(b"new content").hexdigest())

    def test_normalized_path_and_file_id_are_deterministic(self) -> None:
        path = self.root / "alpha.txt"
        path.write_text("alpha", encoding="utf-8")

        normalized = normalize_path(path)

        self.assertEqual(normalized, normalize_path(path))
        self.assertEqual(file_id_for_path(normalized), file_id_for_path(normalized))
        self.assertTrue(file_id_for_path(normalized).startswith("file-"))

    def test_source_type_mapping(self) -> None:
        self.assertEqual(source_type_for_extension(".docx"), "office")
        self.assertEqual(source_type_for_extension(".XLSX"), "office")
        self.assertEqual(source_type_for_extension(".md"), "text")
        self.assertEqual(source_type_for_extension(".png"), "image")
        self.assertEqual(source_type_for_extension(".zip"), "archive")
        self.assertEqual(source_type_for_extension(".cad"), "unknown")


if __name__ == "__main__":
    unittest.main()

