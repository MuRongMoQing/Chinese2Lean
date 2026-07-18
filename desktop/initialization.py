from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Protocol

from chinese2lean.product.initialization import (
    STEP_LABELS,
    EnvironmentInitializer,
    InitializationEvent,
    InitializationSnapshot,
    InitializationStatus,
    InitializationStep,
    StepStatus,
)


class Initializer(Protocol):
    def needs_initialization(self) -> bool: ...

    def run(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[InitializationEvent], None] | None = None,
    ) -> InitializationSnapshot: ...

    def retry(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[InitializationEvent], None] | None = None,
    ) -> InitializationSnapshot: ...

    def resume(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[InitializationEvent], None] | None = None,
    ) -> InitializationSnapshot: ...

    def cancel(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _WorkerResult:
    snapshot: InitializationSnapshot


@dataclass(frozen=True, slots=True)
class _WorkerFailure:
    message: str


_QueueItem = InitializationEvent | _WorkerResult | _WorkerFailure


class InitializationWindow:
    """Tk adapter for a first-run initializer executed outside the UI thread."""

    def __init__(
        self,
        root: tk.Tk,
        initializer: Initializer,
        on_completed: Callable[[], None],
        *,
        poll_interval_ms: int = 25,
    ) -> None:
        self.root = root
        self.initializer = initializer
        self.on_completed = on_completed
        self.poll_interval_ms = poll_interval_ms
        self.step_labels = [STEP_LABELS[step] for step in InitializationStep]
        self.buttons: dict[str, ttk.Button] = {}
        self.cancel_event = threading.Event()
        self._events: queue.Queue[_QueueItem] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._poll_id: str | None = None
        self._completion_notified = False
        self._destroyed = False
        self._shutdown_callback: Callable[[], None] | None = None
        self._step_status = {step: StepStatus.PENDING for step in InitializationStep}

        root.title("Chinese2Lean 初始化")
        root.geometry("760x600")
        self._build()

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _build(self) -> None:
        self.container = ttk.Frame(self.root, padding=16)
        self.container.pack(fill="both", expand=True)

        ttk.Label(
            self.container,
            text="Chinese2Lean 初始化",
            font=("TkDefaultFont", 18, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        steps_frame = ttk.LabelFrame(self.container, text="初始化步骤", padding=10)
        steps_frame.pack(fill="x")
        self.step_variables: dict[InitializationStep, tk.StringVar] = {}
        for step in InitializationStep:
            variable = tk.StringVar(value=self._format_step(step, StepStatus.PENDING))
            self.step_variables[step] = variable
            ttk.Label(steps_frame, textvariable=variable, anchor="w").pack(fill="x", pady=2)

        self.progress = ttk.Progressbar(
            self.container,
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress.pack(fill="x", pady=(12, 4))
        self.progress_text = tk.StringVar(value="0%")
        ttk.Label(self.container, textvariable=self.progress_text, anchor="e").pack(fill="x")

        log_frame = ttk.LabelFrame(self.container, text="初始化日志", padding=6)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")

        self.error = tk.StringVar(value="")
        ttk.Label(
            self.container,
            textvariable=self.error,
            foreground="#A40000",
            wraplength=700,
            anchor="w",
        ).pack(fill="x", pady=(8, 0))

        actions = ttk.Frame(self.container)
        actions.pack(fill="x", pady=(10, 0))
        for label, command in (
            ("重试", self.retry),
            ("取消", self.cancel),
            ("恢复", self.resume),
        ):
            button = ttk.Button(actions, text=label, command=command, state="disabled")
            button.pack(side="left", padx=(0, 8))
            self.buttons[label] = button

    @staticmethod
    def _format_step(step: InitializationStep, status: StepStatus) -> str:
        marker = {
            StepStatus.PENDING: "[ ]",
            StepStatus.RUNNING: "[… ]",
            StepStatus.SUCCEEDED: "[✓]",
            StepStatus.FAILED: "[✗]",
            StepStatus.CANCELLED: "[-]",
        }[status]
        return f"{marker} {STEP_LABELS[step]}"

    def start(self) -> None:
        self._start_action("run")

    def retry(self) -> None:
        self._start_action("retry")

    def resume(self) -> None:
        self._start_action("resume")

    def _start_action(self, action: str) -> None:
        if self._destroyed or self.is_running:
            return
        self.cancel_event = threading.Event()
        self.error.set("")
        self._set_buttons(retry=False, cancel=True, resume=False)
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(action, self.cancel_event),
            name="chinese2lean-environment-initializer",
            daemon=False,
        )
        self._worker.start()
        self._ensure_polling()

    def _run_worker(self, action: str, cancel_event: threading.Event) -> None:
        try:
            method = {
                "run": self.initializer.run,
                "retry": self.initializer.retry,
                "resume": self.initializer.resume,
            }[action]
            snapshot = method(cancel_event=cancel_event, on_event=self._events.put)
            self._events.put(_WorkerResult(snapshot))
        except Exception as error:
            self._events.put(_WorkerFailure(str(error)))

    def cancel(self) -> None:
        if not self.is_running:
            return
        self.cancel_event.set()
        self.initializer.cancel()
        self.buttons["取消"].configure(state="disabled")
        self._append_log("正在取消初始化，请稍候……")

    def _ensure_polling(self) -> None:
        if self._poll_id is None and not self._destroyed:
            self._poll_id = self.root.after(self.poll_interval_ms, self._drain_events)

    def _drain_events(self) -> None:
        self._poll_id = None
        while True:
            try:
                item = self._events.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, InitializationEvent):
                self._apply_event(item)
            elif isinstance(item, _WorkerResult):
                self._apply_result(item.snapshot)
            else:
                self.error.set(f"INITIALIZATION_WORKER_ERROR: {item.message}")
                self._append_log(self.error.get())
                self._set_buttons(retry=True, cancel=False, resume=False)
        if self.is_running or not self._events.empty():
            self._ensure_polling()
        elif self._shutdown_callback is not None:
            callback = self._shutdown_callback
            self._shutdown_callback = None
            callback()

    def _apply_event(self, event: InitializationEvent) -> None:
        self.progress.configure(value=event.progress_percent)
        self.progress_text.set(f"{event.progress_percent}%")
        if event.step is not None and event.step_status is not None:
            self._step_status[event.step] = event.step_status
            self.step_variables[event.step].set(self._format_step(event.step, event.step_status))
        self._append_log(event.message)
        if event.kind == "error":
            self.error.set(event.message)

    def _apply_result(self, snapshot: InitializationSnapshot) -> None:
        self.progress.configure(value=snapshot.progress_percent)
        self.progress_text.set(f"{snapshot.progress_percent}%")
        for step, status in snapshot.steps.items():
            self._step_status[step] = status
            self.step_variables[step].set(self._format_step(step, status))
        if snapshot.status is InitializationStatus.COMPLETED:
            self._set_buttons(retry=False, cancel=False, resume=False)
            if not self._completion_notified:
                self._completion_notified = True
                self.on_completed()
        elif snapshot.status is InitializationStatus.FAILED:
            details = ": ".join(
                value for value in (snapshot.error_code, snapshot.error_message) if value
            )
            self.error.set(details or "环境初始化失败")
            self._set_buttons(
                retry=snapshot.error_recoverable,
                cancel=False,
                resume=False,
            )
        elif snapshot.status is InitializationStatus.CANCELLED:
            self.error.set(snapshot.error_message or "初始化已取消")
            self._set_buttons(retry=False, cancel=False, resume=True)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_buttons(self, *, retry: bool, cancel: bool, resume: bool) -> None:
        states = {"重试": retry, "取消": cancel, "恢复": resume}
        for label, enabled in states.items():
            self.buttons[label].configure(state="normal" if enabled else "disabled")

    def request_shutdown(self, on_stopped: Callable[[], None]) -> None:
        if self._destroyed:
            on_stopped()
            return
        self._shutdown_callback = on_stopped
        if self.is_running:
            self.cancel()
            self._ensure_polling()
        else:
            callback = self._shutdown_callback
            self._shutdown_callback = None
            if callback is not None:
                callback()

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._poll_id is not None:
            try:
                self.root.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None
        self.container.destroy()


ProductLauncher = Callable[[tk.Tk], Callable[[], None] | None]


class DesktopApplication:
    """Own the initialization gate and product-window cleanup lifecycle."""

    def __init__(
        self,
        root: tk.Tk,
        initializer: Initializer,
        product_launcher: ProductLauncher,
    ) -> None:
        self.root = root
        self.initializer = initializer
        self.product_launcher = product_launcher
        self.initialization_window: InitializationWindow | None = None
        self._product_cleanup: Callable[[], None] | None = None
        self._product_started = False
        self._closing = False
        self._closed = False

    def start(self) -> None:
        if self._closed or self._product_started or self.initialization_window is not None:
            return
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        if self.initializer.needs_initialization():
            self.initialization_window = InitializationWindow(
                self.root,
                self.initializer,
                self._start_product,
            )
            self.initialization_window.start()
        else:
            self._start_product()

    def _start_product(self) -> None:
        if self._closing or self._product_started:
            return
        if self.initialization_window is not None:
            self.initialization_window.destroy()
            self.initialization_window = None
        self._product_cleanup = self.product_launcher(self.root)
        self._product_started = True

    def shutdown(self) -> None:
        if self._closed or self._closing:
            return
        self._closing = True
        if self.initialization_window is not None and self.initialization_window.is_running:
            self.initialization_window.request_shutdown(self._finish_shutdown)
        else:
            self._finish_shutdown()

    def _finish_shutdown(self) -> None:
        if self._closed:
            return
        if self.initialization_window is not None:
            self.initialization_window.destroy()
            self.initialization_window = None
        if self._product_cleanup is not None:
            self._product_cleanup()
            self._product_cleanup = None
        self._closed = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def launch_desktop(
    root: tk.Tk,
    initializer: Initializer | EnvironmentInitializer,
    product_launcher: ProductLauncher,
) -> DesktopApplication:
    """Create the testable desktop lifecycle without entering ``mainloop``."""

    return DesktopApplication(root, initializer, product_launcher)
