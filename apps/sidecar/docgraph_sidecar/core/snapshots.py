from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from docgraph_sidecar.core.db import (
    DB_FILENAME,
    connect,
    get_schema_value,
    initialize_database,
    resolve_db_path,
)
from docgraph_sidecar.settings_store import SettingsStore, default_data_dir


SETTINGS_FILENAME = "settings.json"


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseStatus:
    db_path: Path
    exists: bool
    schema_version: str | None
    size_bytes: int
    snapshot_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "db_path": str(self.db_path),
            "exists": self.exists,
            "schema_version": self.schema_version,
            "size_bytes": self.size_bytes,
            "snapshot_count": self.snapshot_count,
        }


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_id: str
    snapshot_dir: Path
    db_path: Path
    settings_path: Path | None
    size_bytes: int
    schema_version: str | None
    status: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_dir": str(self.snapshot_dir),
            "db_path": str(self.db_path),
            "settings_path": str(self.settings_path) if self.settings_path else None,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
        }


def create_snapshot(
    *,
    data_dir: Path | None = None,
    settings_store: SettingsStore | None = None,
    snapshot_type: str = "manual",
) -> SnapshotResult:
    resolved_data_dir = data_dir or default_data_dir()
    store = settings_store or SettingsStore(resolved_data_dir)
    initialize_database(data_dir=resolved_data_dir)

    snapshot_id = _new_snapshot_id()
    snapshot_dir = _snapshot_root(resolved_data_dir) / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    source_db_path = resolve_db_path(data_dir=resolved_data_dir)
    snapshot_db_path = snapshot_dir / DB_FILENAME
    created_at = _now()
    schema_version = _schema_version(resolved_data_dir)

    _backup_sqlite(source_db_path, snapshot_db_path)

    snapshot_settings_path: Path | None = None
    if store.path.exists():
        snapshot_settings_path = snapshot_dir / SETTINGS_FILENAME
        shutil.copy2(store.path, snapshot_settings_path)

    size_bytes = snapshot_db_path.stat().st_size
    result = SnapshotResult(
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        db_path=snapshot_db_path,
        settings_path=snapshot_settings_path,
        size_bytes=size_bytes,
        schema_version=schema_version,
        status="created",
        created_at=created_at,
    )
    _record_snapshot(resolved_data_dir, result, snapshot_type=snapshot_type)
    return result


def restore_snapshot(
    snapshot_id: str,
    *,
    data_dir: Path | None = None,
    settings_store: SettingsStore | None = None,
) -> SnapshotResult:
    if not snapshot_id or any(part in snapshot_id for part in ("..", "/", "\\")):
        raise SnapshotError("Invalid snapshot id.")

    resolved_data_dir = data_dir or default_data_dir()
    store = settings_store or SettingsStore(resolved_data_dir)
    snapshot_dir = _snapshot_root(resolved_data_dir) / snapshot_id
    snapshot_db_path = snapshot_dir / DB_FILENAME

    if not snapshot_db_path.exists():
        raise SnapshotError("Snapshot database was not found.")

    target_db_path = resolve_db_path(data_dir=resolved_data_dir)
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    _remove_sqlite_sidecars(target_db_path)
    shutil.copy2(snapshot_db_path, target_db_path)
    _remove_sqlite_sidecars(target_db_path)

    snapshot_settings_path = snapshot_dir / SETTINGS_FILENAME
    restored_settings_path: Path | None = None
    if snapshot_settings_path.exists():
        store.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_settings_path, store.path)
        restored_settings_path = store.path

    initialize_database(data_dir=resolved_data_dir)
    return SnapshotResult(
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        db_path=target_db_path,
        settings_path=restored_settings_path,
        size_bytes=target_db_path.stat().st_size,
        schema_version=_schema_version(resolved_data_dir),
        status="restored",
        created_at=_now(),
    )


def database_status(*, data_dir: Path | None = None) -> DatabaseStatus:
    resolved_data_dir = data_dir or default_data_dir()
    result = initialize_database(data_dir=resolved_data_dir)
    db_path = result.db_path
    connection = connect(data_dir=resolved_data_dir)
    try:
        snapshot_count = connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        schema_version = get_schema_value(connection, "schema_version")
    finally:
        connection.close()

    return DatabaseStatus(
        db_path=db_path,
        exists=db_path.exists(),
        schema_version=schema_version,
        size_bytes=db_path.stat().st_size if db_path.exists() else 0,
        snapshot_count=int(snapshot_count),
    )


def _backup_sqlite(source_db_path: Path, snapshot_db_path: Path) -> None:
    source = sqlite3.connect(source_db_path)
    destination = sqlite3.connect(snapshot_db_path)
    try:
        source.execute("PRAGMA wal_checkpoint(FULL);")
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()


def _record_snapshot(data_dir: Path, result: SnapshotResult, *, snapshot_type: str) -> None:
    connection = connect(data_dir=data_dir)
    try:
        connection.execute(
            """
            INSERT INTO snapshots (
              snapshot_id,
              snapshot_type,
              db_path,
              settings_path,
              size_bytes,
              schema_version,
              status,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.snapshot_id,
                snapshot_type,
                str(result.db_path),
                str(result.settings_path) if result.settings_path else None,
                result.size_bytes,
                result.schema_version,
                result.status,
                result.created_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _schema_version(data_dir: Path) -> str | None:
    connection = connect(data_dir=data_dir)
    try:
        return get_schema_value(connection, "schema_version")
    finally:
        connection.close()


def _snapshot_root(data_dir: Path) -> Path:
    return data_dir / "snapshots"


def _new_snapshot_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"snap-{stamp}-{uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _remove_sqlite_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()

