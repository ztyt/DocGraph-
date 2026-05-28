import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.core.db import (
    MIGRATION_PREFIX,
    connect,
    initialize_database,
    read_schema_meta,
)


class DatabaseMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initialize_database_applies_migrations_once(self) -> None:
        first = initialize_database(data_dir=self.data_dir)
        second = initialize_database(data_dir=self.data_dir)

        self.assertEqual(first.applied, ("001_init",))
        self.assertEqual(first.skipped, ())
        self.assertEqual(second.applied, ())
        self.assertEqual(second.skipped, ("001_init",))
        self.assertEqual(second.schema_version, "001_init")
        self.assertTrue(first.db_path.exists())

    def test_connection_pragmas_are_configured(self) -> None:
        initialize_database(data_dir=self.data_dir)

        connection = connect(data_dir=self.data_dir)
        try:
            journal_mode = connection.execute("PRAGMA journal_mode;").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout;").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_keys;").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(journal_mode, "wal")
        self.assertEqual(busy_timeout, 5000)
        self.assertEqual(foreign_keys, 1)

    def test_schema_meta_records_migration_checksum(self) -> None:
        initialize_database(data_dir=self.data_dir)

        connection = connect(data_dir=self.data_dir)
        try:
            meta = read_schema_meta(connection)
        finally:
            connection.close()

        self.assertEqual(meta["schema_version"], "001_init")
        self.assertTrue(meta[f"{MIGRATION_PREFIX}001_init"])

    def test_cli_init_db_outputs_result_json(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        result = subprocess.run(
            [sys.executable, str(app_path), "init-db", "--data-dir", str(self.data_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn('"schema_version": "001_init"', result.stdout)
        self.assertTrue((self.data_dir / "docgraph.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
