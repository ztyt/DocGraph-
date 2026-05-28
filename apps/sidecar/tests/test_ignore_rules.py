import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.scanner.ignore_rules import (
    IgnoreRules,
    explain_ignore,
    filter_ignored,
    should_ignore,
)


class IgnoreRulesTest(unittest.TestCase):
    def test_ignores_default_directory_names_anywhere_in_path(self) -> None:
        ignored_paths = [
            r"C:\work\project\node_modules\pkg\index.js",
            r"C:\work\project\venv\pyvenv.cfg",
            r"C:\work\project\.venv\pyvenv.cfg",
            r"C:\work\project\.git\config",
            r"C:\Windows\System32\kernel32.dll",
            r"C:\Program Files\App\readme.txt",
            r"C:\Program Files (x86)\App\readme.txt",
            "/home/user/project/node_modules/pkg/index.js",
        ]

        for path in ignored_paths:
            with self.subTest(path=path):
                decision = explain_ignore(path)
                self.assertTrue(decision.ignored)
                self.assertEqual(decision.reason, "ignored_directory")

    def test_ignores_default_file_patterns(self) -> None:
        cases = {
            r"C:\docs\~$draft.docx": "~$*.docx",
            r"C:\docs\notes.tmp": "*.tmp",
            r"C:\docs\Thumbs.db": "Thumbs.db",
            r"C:\docs\THUMBS.DB": "THUMBS.DB",
            "/tmp/report.TMP": "*.tmp",
        }

        for path, matched in cases.items():
            with self.subTest(path=path):
                decision = explain_ignore(path)
                self.assertTrue(decision.ignored)
                self.assertIn(decision.reason, {"ignored_file_pattern", "ignored_filename"})
                if matched.lower() == "thumbs.db":
                    self.assertEqual(decision.matched, matched)

    def test_allows_regular_documents_and_similar_names(self) -> None:
        allowed_paths = [
            r"C:\docs\project.docx",
            r"C:\docs\windows_notes.txt",
            r"C:\docs\program files inventory.xlsx",
            r"C:\docs\~$draft.xlsx",
            r"C:\docs\temporary.tmpx",
        ]

        for path in allowed_paths:
            with self.subTest(path=path):
                self.assertFalse(should_ignore(path))

    def test_is_dir_skips_file_pattern_checks_for_directory_name(self) -> None:
        self.assertTrue(should_ignore(r"C:\docs\scratch.tmp"))
        self.assertFalse(should_ignore(r"C:\docs\scratch.tmp", is_dir=True))
        self.assertFalse(should_ignore(r"C:\docs\scratch.tmp\file.txt"))

    def test_custom_rules_can_extend_defaults(self) -> None:
        rules = IgnoreRules(
            ignored_dir_names=frozenset({"cache"}),
            ignored_file_names=frozenset({"desktop.ini"}),
            ignored_file_patterns=("*.bak",),
        )

        self.assertTrue(should_ignore(r"C:\docs\cache\file.txt", rules=rules))
        self.assertTrue(should_ignore(r"C:\docs\desktop.ini", rules=rules))
        self.assertTrue(should_ignore(r"C:\docs\old.bak", rules=rules))
        self.assertFalse(should_ignore(r"C:\docs\node_modules\file.txt", rules=rules))

    def test_filter_ignored_returns_allowed_paths(self) -> None:
        paths = [
            r"C:\docs\keep.txt",
            r"C:\docs\Thumbs.db",
            r"C:\docs\nested\keep.docx",
            r"C:\docs\node_modules\skip.js",
        ]

        kept = [str(path) for path in filter_ignored(paths)]

        self.assertEqual(kept, [r"C:\docs\keep.txt", r"C:\docs\nested\keep.docx"])


if __name__ == "__main__":
    unittest.main()
