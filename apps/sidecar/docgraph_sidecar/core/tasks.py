from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from docgraph_sidecar.core.db import connect, initialize_database


TaskStatus = Literal["queued", "running", "done", "failed"]
VALID_STATUSES = {"queued", "running", "done", "failed"}


class TaskQueueError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    task_type: str
    task_status: TaskStatus
    priority: int
    payload: dict[str, Any]
    retry_count: int
    max_attempts: int
    last_error_code: str | None
    last_error_message: str | None
    scheduled_at: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str | None
    updated_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_status": self.task_status,
            "priority": self.priority,
            "payload": self.payload,
            "retry_count": self.retry_count,
            "max_attempts": self.max_attempts,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskQueue:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        initialize_database(data_dir=data_dir)

    def enqueue(
        self,
        task_type: str,
        *,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        scheduled_at: str | None = None,
        task_id: str | None = None,
    ) -> TaskRecord:
        if not task_type:
            raise TaskQueueError("Task type is required.")
        if max_attempts < 1:
            raise TaskQueueError("max_attempts must be at least 1.")

        now = _now()
        task_id = task_id or f"task-{uuid4().hex}"
        payload_json = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)

        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute(
                """
                INSERT INTO task_queue (
                  task_id,
                  task_type,
                  task_status,
                  priority,
                  payload_json,
                  attempts,
                  retry_count,
                  max_attempts,
                  scheduled_at,
                  created_at,
                  updated_at
                )
                VALUES (?, ?, 'queued', ?, ?, 0, 0, ?, ?, ?, ?)
                """,
                (task_id, task_type, priority, payload_json, max_attempts, scheduled_at, now, now),
            )
            connection.commit()
            return _get_required(connection, task_id)
        finally:
            connection.close()

    def get(self, task_id: str) -> TaskRecord | None:
        connection = connect(data_dir=self.data_dir)
        try:
            row = connection.execute(
                "SELECT * FROM task_queue WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            return _row_to_task(row) if row else None
        finally:
            connection.close()

    def list(self, *, status: TaskStatus | None = None, limit: int = 100) -> list[TaskRecord]:
        if status is not None:
            _validate_status(status)
        connection = connect(data_dir=self.data_dir)
        try:
            if status is None:
                rows = connection.execute(
                    """
                    SELECT * FROM task_queue
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM task_queue
                    WHERE task_status = ?
                    ORDER BY priority ASC, scheduled_at ASC, created_at ASC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            return [_row_to_task(row) for row in rows]
        finally:
            connection.close()

    def claim_next(
        self,
        *,
        task_type: str | None = None,
        now: str | None = None,
    ) -> TaskRecord | None:
        now = now or _now()
        connection = connect(data_dir=self.data_dir)
        try:
            connection.execute("BEGIN IMMEDIATE;")
            if task_type is None:
                row = connection.execute(
                    """
                    SELECT * FROM task_queue
                    WHERE task_status = 'queued'
                      AND (scheduled_at IS NULL OR scheduled_at <= ?)
                    ORDER BY priority ASC, scheduled_at ASC, created_at ASC
                    LIMIT 1
                    """,
                    (now,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT * FROM task_queue
                    WHERE task_status = 'queued'
                      AND task_type = ?
                      AND (scheduled_at IS NULL OR scheduled_at <= ?)
                    ORDER BY priority ASC, scheduled_at ASC, created_at ASC
                    LIMIT 1
                    """,
                    (task_type, now),
                ).fetchone()

            if row is None:
                connection.commit()
                return None

            started_at = _now()
            connection.execute(
                """
                UPDATE task_queue
                SET task_status = 'running',
                    started_at = ?,
                    finished_at = NULL,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (started_at, started_at, row["task_id"]),
            )
            connection.commit()
            return _get_required(connection, row["task_id"])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete(self, task_id: str) -> TaskRecord:
        now = _now()
        connection = connect(data_dir=self.data_dir)
        try:
            self._require_existing(connection, task_id)
            connection.execute(
                """
                UPDATE task_queue
                SET task_status = 'done',
                    finished_at = ?,
                    updated_at = ?,
                    last_error_code = NULL,
                    last_error_message = NULL
                WHERE task_id = ?
                """,
                (now, now, task_id),
            )
            connection.commit()
            return _get_required(connection, task_id)
        finally:
            connection.close()

    def fail(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        retryable: bool = True,
        next_scheduled_at: str | None = None,
    ) -> TaskRecord:
        now = _now()
        connection = connect(data_dir=self.data_dir)
        try:
            current = self._require_existing(connection, task_id)
            retry_count = current.retry_count + 1
            should_retry = retryable and retry_count < current.max_attempts
            next_status: TaskStatus = "queued" if should_retry else "failed"
            finished_at = None if should_retry else now

            connection.execute(
                """
                UPDATE task_queue
                SET task_status = ?,
                    retry_count = ?,
                    attempts = ?,
                    last_error_code = ?,
                    last_error_message = ?,
                    scheduled_at = ?,
                    finished_at = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    next_status,
                    retry_count,
                    retry_count,
                    error_code,
                    error_message,
                    next_scheduled_at,
                    finished_at,
                    now,
                    task_id,
                ),
            )
            connection.commit()
            return _get_required(connection, task_id)
        finally:
            connection.close()

    def _require_existing(self, connection: sqlite3.Connection, task_id: str) -> TaskRecord:
        task = _get_required(connection, task_id)
        return task


def _get_required(connection: sqlite3.Connection, task_id: str) -> TaskRecord:
    row = connection.execute("SELECT * FROM task_queue WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise TaskQueueError(f"Task not found: {task_id}")
    return _row_to_task(row)


def _row_to_task(row: sqlite3.Row) -> TaskRecord:
    payload_json = row["payload_json"] or "{}"
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        payload = {}

    status = str(row["task_status"])
    _validate_status(status)
    return TaskRecord(
        task_id=str(row["task_id"]),
        task_type=str(row["task_type"]),
        task_status=status,  # type: ignore[arg-type]
        priority=int(row["priority"]),
        payload=payload if isinstance(payload, dict) else {},
        retry_count=int(row["retry_count"]),
        max_attempts=int(row["max_attempts"]),
        last_error_code=row["last_error_code"],
        last_error_message=row["last_error_message"],
        scheduled_at=row["scheduled_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise TaskQueueError(f"Invalid task status: {status}")


def _now() -> str:
    return datetime.now(UTC).isoformat()

