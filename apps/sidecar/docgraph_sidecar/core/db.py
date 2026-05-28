from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from docgraph_sidecar.settings_store import default_data_dir


DB_FILENAME = "docgraph.sqlite"
MIGRATION_PREFIX = "migration:"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    migration_id: str
    checksum: str
    sql: str


@dataclass(frozen=True)
class MigrationResult:
    db_path: Path
    applied: tuple[str, ...]
    skipped: tuple[str, ...]
    schema_version: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "db_path": str(self.db_path),
            "applied": list(self.applied),
            "skipped": list(self.skipped),
            "schema_version": self.schema_version,
        }


def resolve_db_path(
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
) -> Path:
    if db_path is not None:
        return db_path
    return (data_dir or default_data_dir()) / DB_FILENAME


def connect(
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
) -> sqlite3.Connection:
    resolved = resolve_db_path(data_dir=data_dir, db_path=db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved)
    connection.row_factory = sqlite3.Row
    configure_connection(connection)
    return connection


def configure_connection(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA busy_timeout=5000;")
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.execute("PRAGMA journal_mode=WAL;")


def initialize_database(
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
) -> MigrationResult:
    resolved = resolve_db_path(data_dir=data_dir, db_path=db_path)
    applied: list[str] = []
    skipped: list[str] = []

    connection = connect(db_path=resolved)
    try:
        _ensure_schema_meta(connection)

        for migration in load_migrations():
            key = f"{MIGRATION_PREFIX}{migration.migration_id}"
            stored = get_schema_value(connection, key)
            if stored is not None:
                if stored != migration.checksum:
                    raise MigrationError(
                        f"Migration checksum mismatch for {migration.migration_id}."
                    )
                skipped.append(migration.migration_id)
                continue

            connection.executescript(migration.sql)
            set_schema_value(connection, key, migration.checksum)
            set_schema_value(connection, "schema_version", migration.migration_id)
            applied.append(migration.migration_id)

        schema_version = get_schema_value(connection, "schema_version")
        connection.commit()
    finally:
        connection.close()

    return MigrationResult(
        db_path=resolved,
        applied=tuple(applied),
        skipped=tuple(skipped),
        schema_version=schema_version,
    )


def load_migrations() -> list[Migration]:
    migration_files = sorted(
        resource
        for resource in files("docgraph_sidecar.migrations").iterdir()
        if resource.name.endswith(".sql")
    )
    migrations: list[Migration] = []

    for resource in migration_files:
        sql = resource.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                migration_id=resource.name.removesuffix(".sql"),
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )

    return migrations


def get_schema_value(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM schema_meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


def set_schema_value(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO schema_meta (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
          value = excluded.value,
          updated_at = excluded.updated_at;
        """,
        (key, value, datetime.now(UTC).isoformat()),
    )


def read_schema_meta(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM schema_meta ORDER BY key").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def migration_result_json(result: MigrationResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)


def _ensure_schema_meta(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT
        );
        """
    )
