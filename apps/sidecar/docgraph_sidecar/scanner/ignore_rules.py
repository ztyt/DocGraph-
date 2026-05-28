from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "program files",
        "program files (x86)",
        "venv",
        "windows",
    }
)

DEFAULT_IGNORED_FILE_NAMES = frozenset({"thumbs.db"})
DEFAULT_IGNORED_FILE_PATTERNS = ("*.tmp", "~$*.docx")


@dataclass(frozen=True)
class IgnoreDecision:
    ignored: bool
    reason: str | None = None
    matched: str | None = None


@dataclass(frozen=True)
class IgnoreRules:
    ignored_dir_names: frozenset[str] = DEFAULT_IGNORED_DIR_NAMES
    ignored_file_names: frozenset[str] = DEFAULT_IGNORED_FILE_NAMES
    ignored_file_patterns: tuple[str, ...] = DEFAULT_IGNORED_FILE_PATTERNS


DEFAULT_IGNORE_RULES = IgnoreRules()


def should_ignore(
    path: str | Path,
    *,
    is_dir: bool | None = None,
    rules: IgnoreRules = DEFAULT_IGNORE_RULES,
) -> bool:
    return explain_ignore(path, is_dir=is_dir, rules=rules).ignored


def explain_ignore(
    path: str | Path,
    *,
    is_dir: bool | None = None,
    rules: IgnoreRules = DEFAULT_IGNORE_RULES,
) -> IgnoreDecision:
    raw_path = str(path)
    parts = _split_path(raw_path)
    if not parts:
        return IgnoreDecision(False)

    for part in parts:
        normalized = _normalize(part)
        if normalized in rules.ignored_dir_names:
            return IgnoreDecision(True, "ignored_directory", part)

    name = parts[-1]
    if is_dir is True:
        return IgnoreDecision(False)

    normalized_name = _normalize(name)
    if normalized_name in rules.ignored_file_names:
        return IgnoreDecision(True, "ignored_filename", name)

    for pattern in rules.ignored_file_patterns:
        if fnmatch.fnmatchcase(normalized_name, pattern.lower()):
            return IgnoreDecision(True, "ignored_file_pattern", pattern)

    return IgnoreDecision(False)


def _split_path(path: str) -> list[str]:
    path = path.strip()
    if not path:
        return []
    return [part for part in re.split(r"[\\/]+", path) if part and part != "."]


def _normalize(value: str) -> str:
    return value.strip().casefold()


def filter_ignored(
    paths: Iterable[str | Path],
    *,
    rules: IgnoreRules = DEFAULT_IGNORE_RULES,
) -> list[Path]:
    return [Path(path) for path in paths if not should_ignore(path, rules=rules)]

