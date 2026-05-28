import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.core.files import (
    FileCatalog,
    FileCatalogError,
    FileListFilters,
    parse_file_list_filters,
)


class FileCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        initialize_database(data_dir=self.data_dir)
        self._insert_file(
            "file-alpha",
            "C:/docs/alpha.md",
            "alpha.md",
            ".md",
            "text",
            128,
            "2026-05-28T08:00:00+00:00",
            "discovered",
        )
        self._insert_file(
            "file-budget",
            "C:/docs/budget.xlsx",
            "budget.xlsx",
            ".xlsx",
            "office",
            2048,
            "2026-05-27T08:00:00+00:00",
            "indexed",
        )
        self._insert_file(
            "file-deleted",
            "C:/docs/deleted.pdf",
            "deleted.pdf",
            ".pdf",
            "pdf",
            4096,
            "2026-05-26T08:00:00+00:00",
            "discovered",
            deleted=True,
        )
        self.catalog = FileCatalog(data_dir=self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_files_excludes_deleted_and_orders_by_modified_time(self) -> None:
        result = self.catalog.list_files()

        self.assertEqual(result.total, 2)
        self.assertEqual([item.file_id for item in result.items], ["file-alpha", "file-budget"])

    def test_filters_by_type_status_source_and_keyword(self) -> None:
        result = self.catalog.list_files(
            FileListFilters(type="xlsx", status="indexed", source="office", keyword="budget")
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].filename, "budget.xlsx")

    def test_keyword_matches_path(self) -> None:
        result = self.catalog.list_files(FileListFilters(keyword="docs/alpha"))

        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].file_id, "file-alpha")

    def test_parse_file_list_filters_validates_limit(self) -> None:
        with self.assertRaises(FileCatalogError):
            parse_file_list_filters({"limit": "500"})

    def test_parse_file_list_filters_normalizes_empty_values(self) -> None:
        filters = parse_file_list_filters(
            {
                "type": "all",
                "status": "",
                "source": "text",
                "keyword": " alpha ",
                "limit": "25",
                "offset": "2",
            }
        )

        self.assertIsNone(filters.type)
        self.assertIsNone(filters.status)
        self.assertEqual(filters.source, "text")
        self.assertEqual(filters.keyword, "alpha")
        self.assertEqual(filters.limit, 25)
        self.assertEqual(filters.offset, 2)

    def _insert_file(
        self,
        file_id: str,
        path: str,
        filename: str,
        extension: str,
        source_type: str,
        size_bytes: int,
        modified_time: str,
        file_status: str,
        *,
        deleted: bool = False,
    ) -> None:
        connection = connect(data_dir=self.data_dir)
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
                  size_bytes,
                  modified_time,
                  file_status,
                  parse_status,
                  deleted_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    file_id,
                    path,
                    path.casefold(),
                    filename,
                    extension,
                    source_type,
                    size_bytes,
                    modified_time,
                    file_status,
                    1 if deleted else 0,
                ),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
