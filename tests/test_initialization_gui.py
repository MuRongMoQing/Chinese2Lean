from __future__ import annotations

import threading
import time
import tkinter as tk
from collections.abc import Callable

from chinese2lean.product.initialization import (
    STEP_LABELS,
    InitializationEvent,
    InitializationSnapshot,
    InitializationStatus,
    InitializationStep,
    StepStatus,
)
from desktop.initialization import InitializationWindow, launch_desktop


def _snapshot(
    status: InitializationStatus,
    *,
    progress: int,
    error_code: str | None = None,
    error_message: str | None = None,
    error_recoverable: bool = False,
) -> InitializationSnapshot:
    completed = status is InitializationStatus.COMPLETED
    step_status = StepStatus.SUCCEEDED if completed else StepStatus.PENDING
    return InitializationSnapshot(
        spec_fingerprint="test-fingerprint",
        status=status,
        steps={step: step_status for step in InitializationStep},
        attempts={step: 0 for step in InitializationStep},
        current_step=None,
        progress_percent=progress,
        error_code=error_code,
        error_message=error_message,
        error_recoverable=error_recoverable,
        logs=[],
        sequence=0,
    )


def _event(
    sequence: int,
    *,
    status: InitializationStatus,
    progress: int,
    message: str,
    kind: str = "progress",
    step: InitializationStep | None = None,
    step_status: StepStatus | None = None,
) -> InitializationEvent:
    return InitializationEvent(
        sequence=sequence,
        kind=kind,
        step=step,
        step_status=step_status,
        overall_status=status,
        progress_percent=progress,
        message=message,
    )


class ScriptedInitializer:
    def __init__(
        self,
        scripts: list[tuple[list[InitializationEvent], InitializationSnapshot]],
        *,
        required: bool = True,
    ) -> None:
        self.scripts = scripts
        self.required = required
        self.calls: list[str] = []
        self.cancelled = threading.Event()

    def needs_initialization(self) -> bool:
        return self.required

    def _execute(
        self,
        action: str,
        *,
        cancel_event: threading.Event | None,
        on_event: Callable[[InitializationEvent], None] | None,
    ) -> InitializationSnapshot:
        self.calls.append(action)
        events, snapshot = self.scripts.pop(0)
        for event in events:
            if on_event is not None:
                on_event(event)
        return snapshot

    def run(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[InitializationEvent], None] | None = None,
    ) -> InitializationSnapshot:
        return self._execute("run", cancel_event=cancel_event, on_event=on_event)

    def retry(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[InitializationEvent], None] | None = None,
    ) -> InitializationSnapshot:
        return self._execute("retry", cancel_event=cancel_event, on_event=on_event)

    def resume(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[InitializationEvent], None] | None = None,
    ) -> InitializationSnapshot:
        return self._execute("resume", cancel_event=cancel_event, on_event=on_event)

    def cancel(self) -> None:
        self.cancelled.set()


class BlockingInitializer(ScriptedInitializer):
    def __init__(self) -> None:
        super().__init__([])
        self.entered = threading.Event()

    def _execute(
        self,
        action: str,
        *,
        cancel_event: threading.Event | None,
        on_event: Callable[[InitializationEvent], None] | None,
    ) -> InitializationSnapshot:
        self.calls.append(action)
        self.entered.set()
        assert cancel_event is not None
        cancel_event.wait(timeout=2)
        return _snapshot(InitializationStatus.CANCELLED, progress=0)

    def cancel(self) -> None:
        super().cancel()


def _pump(root: tk.Tk, condition: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)
    assert condition()


def test_initialization_window_shows_exact_steps_progress_logs_and_completion() -> None:
    events = [
        _event(
            index,
            status=InitializationStatus.RUNNING,
            progress=index * 16,
            message=f"日志 {index}",
            kind="log",
            step=step,
            step_status=StepStatus.SUCCEEDED,
        )
        for index, step in enumerate(InitializationStep, start=1)
    ]
    events.append(
        _event(
            7,
            status=InitializationStatus.COMPLETED,
            progress=100,
            message="初始化完成",
            step=InitializationStep.COMPLETE,
            step_status=StepStatus.SUCCEEDED,
        )
    )
    initializer = ScriptedInitializer(
        [(events, _snapshot(InitializationStatus.COMPLETED, progress=100))]
    )
    completed: list[bool] = []
    root = tk.Tk()
    root.withdraw()
    try:
        window = InitializationWindow(root, initializer, lambda: completed.append(True))
        assert root.title() == "Chinese2Lean 初始化"
        assert window.step_labels == [STEP_LABELS[step] for step in InitializationStep]
        assert window.step_labels == [
            "检查系统环境",
            "准备运行环境",
            "配置 Lean",
            "配置 Mathlib",
            "验证编译环境",
            "初始化完成",
        ]
        assert set(window.buttons) == {"重试", "取消", "恢复"}
        assert str(window.log_text["state"]) == "disabled"

        window.start()
        _pump(root, lambda: completed == [True])

        assert int(float(window.progress["value"])) == 100
        assert "日志 1" in window.log_text.get("1.0", "end")
        assert window.error.get() == ""
        root.update()
        assert completed == [True]
    finally:
        root.destroy()


def test_failure_enables_retry_and_cancelled_run_can_resume() -> None:
    failure = _event(
        1,
        status=InitializationStatus.FAILED,
        progress=25,
        message="LEAN_INSTALL_FAILED: 配置 Lean 失败",
        kind="error",
        step=InitializationStep.CONFIGURE_LEAN,
        step_status=StepStatus.FAILED,
    )
    cancelled = _event(
        2,
        status=InitializationStatus.CANCELLED,
        progress=25,
        message="初始化已取消",
        step=InitializationStep.CONFIGURE_LEAN,
        step_status=StepStatus.CANCELLED,
    )
    success = _event(
        3,
        status=InitializationStatus.COMPLETED,
        progress=100,
        message="初始化完成",
        step=InitializationStep.COMPLETE,
        step_status=StepStatus.SUCCEEDED,
    )
    initializer = ScriptedInitializer(
        [
            (
                [failure],
                _snapshot(
                    InitializationStatus.FAILED,
                    progress=25,
                    error_code="LEAN_INSTALL_FAILED",
                    error_message="配置 Lean 失败",
                    error_recoverable=True,
                ),
            ),
            ([cancelled], _snapshot(InitializationStatus.CANCELLED, progress=25)),
            ([success], _snapshot(InitializationStatus.COMPLETED, progress=100)),
        ]
    )
    completed: list[bool] = []
    root = tk.Tk()
    root.withdraw()
    try:
        window = InitializationWindow(root, initializer, lambda: completed.append(True))
        window.start()
        _pump(root, lambda: str(window.buttons["重试"]["state"]) == "normal")
        assert "LEAN_INSTALL_FAILED" in window.error.get()
        assert completed == []

        window.retry()
        _pump(root, lambda: str(window.buttons["恢复"]["state"]) == "normal")
        assert completed == []

        window.resume()
        _pump(root, lambda: completed == [True])
        assert initializer.calls == ["run", "retry", "resume"]
    finally:
        root.destroy()


def test_worker_keeps_tk_responsive_and_cancel_requests_both_tokens() -> None:
    initializer = BlockingInitializer()
    root = tk.Tk()
    root.withdraw()
    try:
        window = InitializationWindow(root, initializer, lambda: None)
        ui_callback_ran = threading.Event()
        window.start()
        assert initializer.entered.wait(timeout=1)
        root.after(0, ui_callback_ran.set)
        _pump(root, ui_callback_ran.is_set)

        window.cancel()
        _pump(root, lambda: str(window.buttons["恢复"]["state"]) == "normal")
        assert initializer.cancelled.is_set()
        assert window.cancel_event.is_set()
    finally:
        root.destroy()


def test_launch_desktop_gates_product_start_and_skips_gate_when_ready() -> None:
    completed = _event(
        1,
        status=InitializationStatus.COMPLETED,
        progress=100,
        message="初始化完成",
        step=InitializationStep.COMPLETE,
        step_status=StepStatus.SUCCEEDED,
    )
    required = ScriptedInitializer(
        [([completed], _snapshot(InitializationStatus.COMPLETED, progress=100))]
    )
    product_starts: list[str] = []
    product_stops: list[str] = []
    root = tk.Tk()
    root.withdraw()
    try:
        application = launch_desktop(
            root,
            required,
            lambda _root: (
                product_starts.append("started"),
                lambda: product_stops.append("stopped"),
            )[1],
        )
        assert product_starts == []
        application.start()
        _pump(root, lambda: product_starts == ["started"])
        assert required.calls == ["run"]
        application.shutdown()
        assert product_stops == ["stopped"]
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    ready = ScriptedInitializer([], required=False)
    ready_starts: list[str] = []
    ready_root = tk.Tk()
    ready_root.withdraw()
    try:
        application = launch_desktop(
            ready_root,
            ready,
            lambda _root: (ready_starts.append("started"), None)[1],
        )
        application.start()
        assert ready_starts == ["started"]
        assert ready.calls == []
        application.shutdown()
    finally:
        try:
            ready_root.destroy()
        except tk.TclError:
            pass
