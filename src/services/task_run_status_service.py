"""
任务运行状态结构化服务。

当前只记录进程边界状态，后续可以从 scraper 内部补充更细阶段。
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now().isoformat()


def build_idle_status() -> dict[str, Any]:
    now = _now_iso()
    return {
        "state": "idle",
        "stage": "idle",
        "error_category": None,
        "message": "任务尚未运行。",
        "pid": None,
        "returncode": None,
        "log_path": None,
        "started_at": None,
        "stopped_at": None,
        "updated_at": now,
    }


class TaskRunStatusService:
    """内存中的任务运行状态索引。"""

    def __init__(self) -> None:
        self._statuses: dict[int, dict[str, Any]] = {}

    def get_status(self, task_id: int | None) -> dict[str, Any]:
        if task_id is None:
            return build_idle_status()
        status = self._statuses.get(task_id)
        return deepcopy(status) if status else build_idle_status()

    def mark_starting(self, task_id: int, *, log_path: str | None = None) -> dict[str, Any]:
        now = _now_iso()
        status = self.get_status(task_id)
        status.update(
            {
                "state": "starting",
                "stage": "process_starting",
                "error_category": None,
                "message": "任务进程正在启动。",
                "pid": None,
                "returncode": None,
                "log_path": log_path,
                "started_at": now,
                "stopped_at": None,
                "updated_at": now,
            }
        )
        self._statuses[task_id] = status
        return deepcopy(status)

    def mark_running(
        self,
        task_id: int,
        *,
        pid: int | None,
        log_path: str | None,
    ) -> dict[str, Any]:
        now = _now_iso()
        status = self.get_status(task_id)
        status.update(
            {
                "state": "running",
                "stage": "process_running",
                "error_category": None,
                "message": "任务进程正在运行。",
                "pid": pid,
                "returncode": None,
                "log_path": log_path,
                "started_at": status.get("started_at") or now,
                "stopped_at": None,
                "updated_at": now,
            }
        )
        self._statuses[task_id] = status
        return deepcopy(status)

    def mark_stopping(self, task_id: int) -> dict[str, Any]:
        now = _now_iso()
        status = self.get_status(task_id)
        status.update(
            {
                "state": "stopping",
                "stage": "process_stopping",
                "message": "任务进程正在停止。",
                "updated_at": now,
            }
        )
        self._statuses[task_id] = status
        return deepcopy(status)

    def mark_stopped(self, task_id: int, *, returncode: int | None = None) -> dict[str, Any]:
        now = _now_iso()
        status = self.get_status(task_id)
        status.update(
            {
                "state": "stopped",
                "stage": "process_stopped",
                "error_category": None,
                "message": "任务进程已停止。",
                "pid": None,
                "returncode": returncode,
                "stopped_at": now,
                "updated_at": now,
            }
        )
        self._statuses[task_id] = status
        return deepcopy(status)

    def mark_failed(
        self,
        task_id: int,
        *,
        error_category: str = "unknown",
        message: str,
        returncode: int | None = None,
        log_path: str | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        status = self.get_status(task_id)
        status.update(
            {
                "state": "failed",
                "stage": "process_failed",
                "error_category": error_category,
                "message": message,
                "pid": None,
                "returncode": returncode,
                "log_path": log_path if log_path is not None else status.get("log_path"),
                "stopped_at": now,
                "updated_at": now,
            }
        )
        self._statuses[task_id] = status
        return deepcopy(status)

    def mark_skipped(
        self,
        task_id: int,
        *,
        error_category: str = "failure_guard",
        message: str,
    ) -> dict[str, Any]:
        now = _now_iso()
        status = self.get_status(task_id)
        status.update(
            {
                "state": "skipped",
                "stage": "failure_guard_skipped",
                "error_category": error_category,
                "message": message,
                "pid": None,
                "returncode": None,
                "stopped_at": now,
                "updated_at": now,
            }
        )
        self._statuses[task_id] = status
        return deepcopy(status)

    def reindex_after_delete(self, deleted_task_id: int) -> None:
        reindexed: dict[int, dict[str, Any]] = {}
        for task_id, status in self._statuses.items():
            if task_id == deleted_task_id:
                continue
            next_task_id = task_id - 1 if task_id > deleted_task_id else task_id
            reindexed[next_task_id] = status
        self._statuses = reindexed
