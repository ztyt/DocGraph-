from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from docgraph_sidecar.core.db import connect, initialize_database
from docgraph_sidecar.core.tasks import TaskQueue
from docgraph_sidecar.scanner.metadata import normalize_path


ScanJobStatus = Literal["queued", "running", "paused", "done", "failed"]
VALID_SCAN_JOB_STATUSES = {"queued", "running", "paused", "done", "failed"}


class ScanJobError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class ScanJobRecord:
    job_id: str
    task_id: str
    root_path: str
    normalized_root_path: str
    job_status: ScanJobStatus
    current_directory: str | None
    scanned_count: int
    failed_count: int
    ignored_count: int
    compute_hash: bool
    error_message: str | None
    created_at: str | None
    updated_at: str | None
    started_at: str | None
    finished_at: str | None
    paused_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "task_id": self.task_id,
            "root_path": self.root_path,
            "normalized_root_path": self.normalized_root_path,
            "job_status": self.job_status,
            "current_directory": self.current_directory,
            "scanned_count": self.scanned_count,
            "failed_count": self.failed_count,
            "ignored_count": self.ignored_count,
            "compute_hash": self.compute_hash,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "paused_at": self.paused_at,
        }


class ScanJobStore:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        initialize_database(data_dir=data_dir)
        self.task_queue = TaskQueue(data_dir=data_dir)

    def create(
        self,
        root_path: str | Path,
        *,
        compute_hash: bool = False,
        priority: int = 100,
    ) -> ScanJobRecord:
        root = _validate_root_path(root_path)
        now = _now()
        job_id = f"scan-{uuid4().hex}"
        task = self.task_queue.enqueue(
            "scan_directory",
            payload={
                "job_id": job_id,
                "root_path": str(root),
                "compute_hash": compute_hash,
            },
            priority=priority,
        )

        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO scan_jobs (
                  job_id,
                  task_id,
                  root_path,
                  normalized_root_path,
                  job_status,
                  current_directory,
                  scanned_count,
                  failed_count,
                  ignored_count,
                  compute_hash,
                  created_at,
                  updated_at
                )
                VALUES (?, ?, ?, ?, 'queued', ?, 0, 0, 0, ?, ?, ?)
                """,
                (
                    job_id,
                    task.task_id,
                    str(root),
                    normalize_path(root),
                    str(root),
                    1 if compute_hash else 0,
                    now,
                    now,
                ),
            )
            connection.commit()
            return _get_required(connection, job_id)
        finally:
            connection.close()

    def get(self, job_id: str) -> ScanJobRecord | None:
        connection = connect(data_dir=self.data_dir)
        try:
            row = connection.execute(
                "SELECT * FROM scan_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return _row_to_scan_job(row) if row else None
        finally:
            connection.close()

    def pause(self, job_id: str) -> ScanJobRecord:
        now = _now()
        connection = connect(data_dir=self.data_dir)
        try:
            current = _get_required(connection, job_id)
            if current.job_status in {"done", "failed"}:
                raise ScanJobError(
                    "Finished scan jobs cannot be paused.",
                    details={"job_id": job_id, "job_status": current.job_status},
                )

            connection.execute(
                """
                UPDATE scan_jobs
                SET job_status = 'paused',
                    paused_at = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (now, now, job_id),
            )
            connection.execute(
                """
                UPDATE task_queue
                SET scheduled_at = '9999-12-31T23:59:59+00:00',
                    updated_at = ?
                WHERE task_id = ?
                  AND task_status = 'queued'
                """,
                (now, current.task_id),
            )
            connection.commit()
            return _get_required(connection, job_id)
        finally:
            connection.close()

    def resume(self, job_id: str) -> ScanJobRecord:
        now = _now()
        connection = connect(data_dir=self.data_dir)
        try:
            current = _get_required(connection, job_id)
            if current.job_status != "paused":
                raise ScanJobError(
                    "Only paused scan jobs can be resumed.",
                    details={"job_id": job_id, "job_status": current.job_status},
                )

            connection.execute(
                """
                UPDATE scan_jobs
                SET job_status = 'queued',
                    paused_at = NULL,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (now, job_id),
            )
            connection.execute(
                """
                UPDATE task_queue
                SET scheduled_at = NULL,
                    updated_at = ?
                WHERE task_id = ?
                  AND task_status = 'queued'
                """,
                (now, current.task_id),
            )
            connection.commit()
            return _get_required(connection, job_id)
        finally:
            connection.close()


def _get_required(connection: sqlite3.Connection, job_id: str) -> ScanJobRecord:
    row = connection.execute("SELECT * FROM scan_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise ScanJobError("Scan job not found.", details={"job_id": job_id})
    return _row_to_scan_job(row)


def _row_to_scan_job(row: sqlite3.Row) -> ScanJobRecord:
    status = str(row["job_status"])
    if status not in VALID_SCAN_JOB_STATUSES:
        raise ScanJobError(
            "Invalid scan job status.",
            details={"job_id": row["job_id"], "job_status": status},
        )

    return ScanJobRecord(
        job_id=str(row["job_id"]),
        task_id=str(row["task_id"]),
        root_path=str(row["root_path"]),
        normalized_root_path=str(row["normalized_root_path"]),
        job_status=status,  # type: ignore[arg-type]
        current_directory=row["current_directory"],
        scanned_count=int(row["scanned_count"]),
        failed_count=int(row["failed_count"]),
        ignored_count=int(row["ignored_count"]),
        compute_hash=bool(row["compute_hash"]),
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        paused_at=row["paused_at"],
    )


def _validate_root_path(root_path: str | Path) -> Path:
    if str(root_path).strip() == "":
        raise ScanJobError(
            "Scan root path is required.",
            details={"root_path": "Path must not be empty."},
        )

    root = Path(root_path).resolve(strict=False)
    if not root.exists():
        raise ScanJobError(
            "Scan root path does not exist.",
            details={"root_path": str(root)},
        )
    if not root.is_dir():
        raise ScanJobError(
            "Scan root path must be a directory.",
            details={"root_path": str(root)},
        )
    return root


def _now() -> str:
    return datetime.now(UTC).isoformat()
