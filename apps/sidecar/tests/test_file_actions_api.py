import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.api import create_app
from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.settings_store import SettingsStore
from fastapi.testclient import TestClient


class FakeFileActionLauncher:
    def __init__(self) -> None:
        self.opened: list[Path] = []
        self.revealed: list[Path] = []

    def open_file(self, path: Path) -> None:
        self.opened.append(path)

    def reveal_in_folder(self, path: Path) -> None:
        self.revealed.append(path)


class FileActionsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "data"
        self.docs_dir = self.root / "docs"
        self.docs_dir.mkdir()
        self.file_path = self.docs_dir / "alpha.txt"
        self.file_path.write_text("alpha", encoding="utf-8")
        initialize_database(data_dir=self.data_dir)
        self._insert_file("file-alpha", self.file_path)
        self._insert_file("file-missing-path", self.docs_dir / "missing.txt")
        self.launcher = FakeFileActionLauncher()
        self.client = TestClient(
            create_app(
                settings_store=SettingsStore(self.data_dir),
                file_action_launcher=self.launcher,
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_open_file_returns_envelope_and_launches_file(self) -> None:
        response = self.client.post("/api/files/file-alpha/open")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["file_id"], "file-alpha")
        self.assertEqual(payload["data"]["path"], str(self.file_path))
        self.assertEqual(payload["data"]["action"], "open")
        self.assertEqual(payload["data"]["status"], "started")
        self.assertEqual(self.launcher.opened, [self.file_path])
        self.assertEqual(self.launcher.revealed, [])

    def test_reveal_file_returns_envelope_and_launches_folder_selection(self) -> None:
        response = self.client.post("/api/files/file-alpha/reveal-in-folder")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["action"], "reveal_in_folder")
        self.assertEqual(self.launcher.opened, [])
        self.assertEqual(self.launcher.revealed, [self.file_path])

    def test_reveal_underscore_route_is_supported(self) -> None:
        response = self.client.post("/api/files/file-alpha/reveal_in_folder")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["action"], "reveal_in_folder")

    def test_missing_file_id_returns_file_not_found(self) -> None:
        response = self.client.post("/api/files/missing/open")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "FILE_NOT_FOUND")
        self.assertEqual(payload["error"]["details"]["file_id"], "missing")
        self.assertEqual(self.launcher.opened, [])

    def test_missing_path_returns_file_not_found(self) -> None:
        response = self.client.post("/api/files/file-missing-path/open")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "FILE_NOT_FOUND")
        self.assertEqual(payload["error"]["details"]["file_id"], "file-missing-path")
        self.assertIn("missing.txt", payload["error"]["details"]["path"])
        self.assertEqual(self.launcher.opened, [])

    def _insert_file(self, file_id: str, path: Path) -> None:
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
                  file_status,
                  parse_status,
                  deleted_flag
                )
                VALUES (?, ?, ?, ?, ?, 'text', 'indexed', 'parsed', 0)
                """,
                (
                    file_id,
                    str(path),
                    str(path).casefold(),
                    path.name,
                    path.suffix.casefold(),
                ),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
