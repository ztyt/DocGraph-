from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from docgraph_sidecar.core.db import connect, initialize_database


FileAction = Literal["open", "reveal_in_folder"]


class FileActionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


class FileActionLauncher(Protocol):
    def open_file(self, path: Path) -> None:
        pass

    def reveal_in_folder(self, path: Path) -> None:
        pass


@dataclass(frozen=True)
class FileActionTarget:
    file_id: str
    path: Path


@dataclass(frozen=True)
class FileActionResult:
    file_id: str
    path: str
    action: FileAction
    status: str = "started"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "path": self.path,
            "action": self.action,
            "status": self.status,
        }


class SystemFileActionLauncher:
    def open_file(self, path: Path) -> None:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)])

    def reveal_in_folder(self, path: Path) -> None:
        if os.name == "nt":
            subprocess.Popen(["explorer", f"/select,{path}"])
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
            return
        subprocess.Popen(["xdg-open", str(path.parent)])


class FileActionService:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        launcher: FileActionLauncher | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.launcher = launcher or SystemFileActionLauncher()
        initialize_database(data_dir=data_dir)

    def open_file(self, file_id: str) -> FileActionResult:
        target = self._resolve_target(file_id)
        self._run_action("open", target.path)
        return FileActionResult(
            file_id=target.file_id,
            path=str(target.path),
            action="open",
        )

    def reveal_in_folder(self, file_id: str) -> FileActionResult:
        target = self._resolve_target(file_id)
        self._run_action("reveal_in_folder", target.path)
        return FileActionResult(
            file_id=target.file_id,
            path=str(target.path),
            action="reveal_in_folder",
        )

    def _resolve_target(self, file_id: str) -> FileActionTarget:
        connection = connect(data_dir=self.data_dir)
        try:
            row = connection.execute(
                """
                SELECT file_id, path
                FROM files
                WHERE file_id = ?
                  AND deleted_flag = 0
                """,
                (file_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            raise FileActionError(
                "File not found.",
                error_code="FILE_NOT_FOUND",
                retryable=False,
                details={"file_id": file_id},
            )

        path = Path(str(row["path"]))
        if not path.exists():
            raise FileActionError(
                "File path does not exist.",
                error_code="FILE_NOT_FOUND",
                retryable=False,
                details={"file_id": file_id, "path": str(path)},
            )

        return FileActionTarget(file_id=str(row["file_id"]), path=path)

    def _run_action(self, action: FileAction, path: Path) -> None:
        try:
            if action == "open":
                self.launcher.open_file(path)
            else:
                self.launcher.reveal_in_folder(path)
        except OSError as exc:
            raise FileActionError(
                "File action could not be started.",
                error_code="FILE_ACTION_ERROR",
                retryable=True,
                details={"action": action, "path": str(path), "error": str(exc)},
            ) from exc
