import asyncio
import sys
from types import SimpleNamespace

from src.services.process_service import ProcessService


class FakeProcess:
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None
        self._done = asyncio.Event()

    async def wait(self):
        await self._done.wait()
        return self.returncode

    def finish(self, returncode: int = 0):
        self.returncode = returncode
        self._done.set()

    def terminate(self):
        self.finish(-15)

    def kill(self):
        self.finish(-9)


def test_process_service_marks_task_stopped_when_process_exits(monkeypatch, tmp_path):
    fake_process = FakeProcess(pid=4321)
    events = []

    async def run_scenario():
        service = ProcessService()
        service.failure_guard.should_skip_start = lambda *args, **kwargs: SimpleNamespace(
            skip=False,
            should_notify=False,
            reason="",
            consecutive_failures=0,
            paused_until=None,
        )

        stopped = asyncio.Event()

        async def on_started(task_id: int):
            events.append(("started", task_id))

        async def on_stopped(task_id: int):
            events.append(("stopped", task_id))
            stopped.set()

        service.set_lifecycle_hooks(on_started=on_started, on_stopped=on_stopped)

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(
            "src.services.process_service.build_task_log_path",
            lambda task_id, _task_name: str(tmp_path / f"task-{task_id}.log"),
        )
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        started = await service.start_task(0, "task-a")
        assert started is True
        assert events == [("started", 0)]
        assert service.is_running(0) is True
        running_status = service.task_run_status_service.get_status(0)
        assert running_status["state"] == "running"
        assert running_status["stage"] == "process_running"
        assert running_status["pid"] == 4321

        fake_process.finish(0)
        await asyncio.wait_for(stopped.wait(), timeout=1)

        assert ("stopped", 0) in events
        assert service.is_running(0) is False
        stopped_status = service.task_run_status_service.get_status(0)
        assert stopped_status["state"] == "stopped"
        assert stopped_status["stage"] == "process_stopped"
        assert stopped_status["returncode"] == 0

    asyncio.run(run_scenario())


def test_process_service_marks_task_failed_when_process_exits_nonzero(monkeypatch, tmp_path):
    fake_process = FakeProcess(pid=4321)

    async def run_scenario():
        service = ProcessService()
        service.failure_guard.should_skip_start = lambda *args, **kwargs: SimpleNamespace(
            skip=False,
            should_notify=False,
            reason="",
            consecutive_failures=0,
            paused_until=None,
        )
        stopped = asyncio.Event()
        service.set_lifecycle_hooks(on_stopped=lambda _task_id: stopped.set())

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(
            "src.services.process_service.build_task_log_path",
            lambda task_id, _task_name: str(tmp_path / f"task-{task_id}.log"),
        )
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        assert await service.start_task(0, "task-a") is True
        fake_process.finish(2)
        await asyncio.wait_for(stopped.wait(), timeout=1)

        status = service.task_run_status_service.get_status(0)
        assert status["state"] == "failed"
        assert status["stage"] == "process_failed"
        assert status["error_category"] == "process_failed"
        assert status["returncode"] == 2

    asyncio.run(run_scenario())


def test_process_service_marks_skipped_when_failure_guard_blocks_start(monkeypatch):
    async def run_scenario():
        service = ProcessService()
        service.failure_guard.should_skip_start = lambda *args, **kwargs: SimpleNamespace(
            skip=True,
            should_notify=False,
            reason="登录态连续失败",
            consecutive_failures=3,
            paused_until=None,
        )

        started = await service.start_task(0, "task-a")

        assert started is False
        status = service.task_run_status_service.get_status(0)
        assert status["state"] == "skipped"
        assert status["stage"] == "failure_guard_skipped"
        assert status["error_category"] == "failure_guard"
        assert "登录态连续失败" in status["message"]

    asyncio.run(run_scenario())


def test_process_service_marks_failed_when_spawn_raises(monkeypatch, tmp_path):
    async def run_scenario():
        service = ProcessService()
        service.failure_guard.should_skip_start = lambda *args, **kwargs: SimpleNamespace(
            skip=False,
            should_notify=False,
            reason="",
            consecutive_failures=0,
            paused_until=None,
        )

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "src.services.process_service.build_task_log_path",
            lambda task_id, _task_name: str(tmp_path / f"task-{task_id}.log"),
        )
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        started = await service.start_task(0, "task-a")

        assert started is False
        status = service.task_run_status_service.get_status(0)
        assert status["state"] == "failed"
        assert status["stage"] == "process_failed"
        assert status["error_category"] == "spawn_failed"
        assert "boom" in status["message"]

    asyncio.run(run_scenario())


def test_process_service_reindexes_runtime_maps_after_delete():
    service = ProcessService()
    proc_a = object()
    proc_c = object()
    watcher_a = object()
    watcher_c = object()

    service.processes = {0: proc_a, 2: proc_c}
    service.log_paths = {0: "a.log", 2: "c.log"}
    service.task_names = {0: "A", 2: "C"}
    service.exit_watchers = {0: watcher_a, 2: watcher_c}
    service.task_run_status_service.mark_running(0, pid=111, log_path="a.log")
    service.task_run_status_service.mark_running(2, pid=333, log_path="c.log")

    service.reindex_after_delete(1)

    assert service.processes == {0: proc_a, 1: proc_c}
    assert service.log_paths == {0: "a.log", 1: "c.log"}
    assert service.task_names == {0: "A", 1: "C"}
    assert service.exit_watchers == {0: watcher_a, 1: watcher_c}
    assert service.task_run_status_service.get_status(1)["pid"] == 333


def test_process_service_adds_debug_limit_arg_when_env_enabled(monkeypatch):
    monkeypatch.setenv("SPIDER_DEBUG_LIMIT", "1")
    service = ProcessService()

    command = service._build_spawn_command("task-a")

    assert command == [
        sys.executable,
        "-u",
        "spider_v2.py",
        "--task-name",
        "task-a",
        "--debug-limit",
        "1",
    ]
