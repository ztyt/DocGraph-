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
from docgraph_sidecar.core.snapshots import (
    create_snapshot,
    database_status,
    restore_snapshot,
)
from docgraph_sidecar.settings_store import SettingsStore


class DatabaseMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initialize_database_applies_migrations_once(self) -> None:
        first = initialize_database(data_dir=self.data_dir)
        second = initialize_database(data_dir=self.data_dir)

        self.assertEqual(
            first.applied,
            (
                "001_init",
                "002_v4_schema",
                "003_task_queue_contract",
                "004_scan_jobs",
                "005_profile_strategy_data",
            ),
        )
        self.assertEqual(first.skipped, ())
        self.assertEqual(second.applied, ())
        self.assertEqual(
            second.skipped,
            (
                "001_init",
                "002_v4_schema",
                "003_task_queue_contract",
                "004_scan_jobs",
                "005_profile_strategy_data",
            ),
        )
        self.assertEqual(second.schema_version, "005_profile_strategy_data")
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

        self.assertEqual(meta["schema_version"], "005_profile_strategy_data")
        self.assertTrue(meta[f"{MIGRATION_PREFIX}001_init"])
        self.assertTrue(meta[f"{MIGRATION_PREFIX}002_v4_schema"])
        self.assertTrue(meta[f"{MIGRATION_PREFIX}003_task_queue_contract"])
        self.assertTrue(meta[f"{MIGRATION_PREFIX}004_scan_jobs"])
        self.assertTrue(meta[f"{MIGRATION_PREFIX}005_profile_strategy_data"])

    def test_v4_schema_creates_required_tables(self) -> None:
        initialize_database(data_dir=self.data_dir)

        required_tables = {
            "files",
            "document_elements",
            "chunks",
            "fts_chunks",
            "task_queue",
            "parse_errors",
            "document_profiles",
            "entities",
            "file_entities",
            "relation_candidates",
            "edges",
            "eval_queries",
            "eval_runs",
            "api_logs",
            "snapshots",
            "scan_jobs",
        }
        connection = connect(data_dir=self.data_dir)
        try:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type IN ('table', 'virtual table')
                UNION
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'fts_chunks%'
                """
            ).fetchall()
        finally:
            connection.close()

        table_names = {row[0] for row in rows}
        self.assertTrue(required_tables.issubset(table_names))

    def test_file_cascade_removes_dependent_records(self) -> None:
        initialize_database(data_dir=self.data_dir)

        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO files (file_id, path, filename)
                VALUES ('file-1', 'C:/docs/a.txt', 'a.txt')
                """
            )
            connection.execute(
                """
                INSERT INTO document_elements (element_id, file_id, element_index, text)
                VALUES ('element-1', 'file-1', 0, 'hello')
                """
            )
            connection.execute(
                """
                INSERT INTO chunks (chunk_id, file_id, element_id, chunk_index, text)
                VALUES ('chunk-1', 'file-1', 'element-1', 0, 'hello world')
                """
            )
            connection.execute(
                """
                INSERT INTO document_profiles (file_id, central_idea)
                VALUES ('file-1', 'Test profile')
                """
            )
            connection.execute("DELETE FROM files WHERE file_id = 'file-1'")
            connection.commit()

            chunks_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            elements_count = connection.execute(
                "SELECT COUNT(*) FROM document_elements"
            ).fetchone()[0]
            profiles_count = connection.execute(
                "SELECT COUNT(*) FROM document_profiles"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(chunks_count, 0)
        self.assertEqual(elements_count, 0)
        self.assertEqual(profiles_count, 0)

    def test_fts_chunks_can_index_and_match_text(self) -> None:
        initialize_database(data_dir=self.data_dir)

        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO fts_chunks (file_id, chunk_id, filename, heading, text)
                VALUES ('file-1', 'chunk-1', 'plan.txt', 'Plan', 'alpha beta project')
                """
            )
            rows = connection.execute(
                """
                SELECT file_id, chunk_id FROM fts_chunks
                WHERE fts_chunks MATCH 'alpha'
                """
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual([(row["file_id"], row["chunk_id"]) for row in rows], [("file-1", "chunk-1")])

    def test_cli_init_db_outputs_result_json(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        result = subprocess.run(
            [sys.executable, str(app_path), "init-db", "--data-dir", str(self.data_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn('"schema_version": "005_profile_strategy_data"', result.stdout)
        self.assertTrue((self.data_dir / "docgraph.sqlite").exists())

    def test_database_status_initializes_database(self) -> None:
        status = database_status(data_dir=self.data_dir)

        self.assertTrue(status.exists)
        self.assertEqual(status.schema_version, "005_profile_strategy_data")
        self.assertEqual(status.snapshot_count, 0)
        self.assertGreater(status.size_bytes, 0)

    def test_snapshot_and_restore_copy_db_and_settings(self) -> None:
        store = SettingsStore(self.data_dir)
        store.save({"privacy_mode": "half_cloud", "llm_enabled": True})
        initialize_database(data_dir=self.data_dir)

        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO files (file_id, path, filename)
                VALUES ('file-before', 'C:/docs/before.txt', 'before.txt')
                """
            )
            connection.commit()
        finally:
            connection.close()

        snapshot = create_snapshot(data_dir=self.data_dir, settings_store=store)
        self.assertEqual(snapshot.status, "created")
        self.assertTrue(snapshot.db_path.exists())
        self.assertTrue(snapshot.settings_path and snapshot.settings_path.exists())

        store.save({"privacy_mode": "cloud_enhanced", "llm_enabled": False})
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO files (file_id, path, filename)
                VALUES ('file-after', 'C:/docs/after.txt', 'after.txt')
                """
            )
            connection.commit()
        finally:
            connection.close()

        restored = restore_snapshot(snapshot.snapshot_id, data_dir=self.data_dir, settings_store=store)
        self.assertEqual(restored.status, "restored")
        self.assertEqual(store.load()["privacy_mode"], "half_cloud")
        self.assertTrue(store.load()["llm_enabled"])

        connection = connect(data_dir=self.data_dir)
        try:
            file_ids = {
                row["file_id"]
                for row in connection.execute("SELECT file_id FROM files").fetchall()
            }
        finally:
            connection.close()

        self.assertEqual(file_ids, {"file-before"})


if __name__ == "__main__":
    unittest.main()
