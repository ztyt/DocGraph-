from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PRIVACY_MODES = {"local", "half_cloud", "cloud_enhanced"}
RETRIEVAL_BACKENDS = {"fts", "rrf", "vector"}

DEFAULT_SETTINGS: dict[str, Any] = {
    "privacy_mode": "local",
    "llm_enabled": False,
    "ocr_enabled": False,
    "vector_search_enabled": False,
    "watchdog_enabled": False,
    "retrieval_backend": "fts",
    "graph_node_cap": 50,
    "max_workers_parse": 2,
}

FEATURE_TO_SETTING = {
    "llm": "llm_enabled",
    "ocr": "ocr_enabled",
    "vector_search": "vector_search_enabled",
    "watchdog": "watchdog_enabled",
}


class SettingsValidationError(ValueError):
    def __init__(self, details: dict[str, str]) -> None:
        super().__init__("Invalid settings payload.")
        self.details = details


class SettingsStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.path = self.data_dir / "settings.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return DEFAULT_SETTINGS.copy()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return DEFAULT_SETTINGS.copy()

        if not isinstance(raw, dict):
            return DEFAULT_SETTINGS.copy()

        try:
            clean = _validate_partial(raw, allow_unknown=False)
        except SettingsValidationError:
            return DEFAULT_SETTINGS.copy()

        settings = DEFAULT_SETTINGS.copy()
        settings.update(clean)
        return settings

    def save(self, patch: dict[str, Any]) -> dict[str, Any]:
        settings = self.load()
        settings.update(_validate_partial(patch, allow_unknown=False))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.path)
        return settings

    def features(self) -> dict[str, bool]:
        settings = self.load()
        return {feature: bool(settings[key]) for feature, key in FEATURE_TO_SETTING.items()}

    def save_features(self, patch: dict[str, Any]) -> dict[str, bool]:
        settings_patch: dict[str, Any] = {}
        errors: dict[str, str] = {}

        for feature, value in patch.items():
            if feature not in FEATURE_TO_SETTING:
                errors[feature] = "Unknown feature flag."
                continue
            if not isinstance(value, bool):
                errors[feature] = "Feature flag must be a boolean."
                continue
            settings_patch[FEATURE_TO_SETTING[feature]] = value

        if errors:
            raise SettingsValidationError(errors)

        self.save(settings_patch)
        return self.features()


def default_data_dir() -> Path:
    configured = os.environ.get("DOCGRAPH_DATA_DIR")
    if configured:
        return Path(configured)
    return Path.home() / ".docgraph-v4"


def _validate_partial(raw: dict[str, Any], *, allow_unknown: bool) -> dict[str, Any]:
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    for key, value in raw.items():
        if key not in DEFAULT_SETTINGS:
            if not allow_unknown:
                errors[key] = "Unknown setting."
            continue

        if key == "privacy_mode":
            if value not in PRIVACY_MODES:
                errors[key] = "Must be local, half_cloud, or cloud_enhanced."
            else:
                clean[key] = value
            continue

        if key == "retrieval_backend":
            if value not in RETRIEVAL_BACKENDS:
                errors[key] = "Must be fts, rrf, or vector."
            else:
                clean[key] = value
            continue

        if key == "graph_node_cap":
            if isinstance(value, int) and 10 <= value <= 200:
                clean[key] = value
            else:
                errors[key] = "Must be an integer from 10 to 200."
            continue

        if key == "max_workers_parse":
            if isinstance(value, int) and 1 <= value <= 8:
                clean[key] = value
            else:
                errors[key] = "Must be an integer from 1 to 8."
            continue

        if isinstance(value, bool):
            clean[key] = value
        else:
            errors[key] = "Must be a boolean."

    if errors:
        raise SettingsValidationError(errors)

    return clean
