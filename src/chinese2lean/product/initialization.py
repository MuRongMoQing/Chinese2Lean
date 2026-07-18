from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import tomllib
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chinese2lean.product.logging import redact_sensitive_values


class InitializationStep(StrEnum):
    CHECK_SYSTEM = "CHECK_SYSTEM"
    PREPARE_RUNTIME = "PREPARE_RUNTIME"
    CONFIGURE_LEAN = "CONFIGURE_LEAN"
    CONFIGURE_MATHLIB = "CONFIGURE_MATHLIB"
    VERIFY_ENVIRONMENT = "VERIFY_ENVIRONMENT"
    COMPLETE = "COMPLETE"


STEP_LABELS: dict[InitializationStep, str] = {
    InitializationStep.CHECK_SYSTEM: "检查系统环境",
    InitializationStep.PREPARE_RUNTIME: "准备运行环境",
    InitializationStep.CONFIGURE_LEAN: "配置 Lean",
    InitializationStep.CONFIGURE_MATHLIB: "配置 Mathlib",
    InitializationStep.VERIFY_ENVIRONMENT: "验证编译环境",
    InitializationStep.COMPLETE: "初始化完成",
}


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InitializationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EnvironmentSpec(_FrozenModel):
    toolchain: str
    lean_version: str
    mathlib_url: str
    mathlib_input_revision: str
    mathlib_revision: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_project(cls, project_root: Path) -> EnvironmentSpec:
        root = project_root.resolve()
        toolchain_path = root / "lean-toolchain"
        lakefile_path = root / "lakefile.toml"
        manifest_path = root / "lake-manifest.json"
        try:
            toolchain_bytes = toolchain_path.read_bytes()
            lakefile_bytes = lakefile_path.read_bytes()
            manifest_bytes = manifest_path.read_bytes()
        except OSError as error:
            raise ValueError(f"无法读取环境锁定文件：{error}") from error

        try:
            toolchain = toolchain_bytes.decode("utf-8").strip()
            lakefile = tomllib.loads(lakefile_bytes.decode("utf-8"))
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"环境锁定文件格式无效：{error}") from error

        toolchain_match = re.fullmatch(r"leanprover/lean4:v(\d+\.\d+\.\d+)", toolchain)
        if toolchain_match is None:
            raise ValueError("lean-toolchain 不是受支持的 Lean 锁定格式")
        lean_version = toolchain_match.group(1)

        requirements = lakefile.get("require")
        if not isinstance(requirements, list):
            raise ValueError("lakefile.toml 缺少 Mathlib 锁定要求")
        mathlib_requirements = [
            item
            for item in requirements
            if isinstance(item, dict) and item.get("name") == "mathlib"
        ]
        if len(mathlib_requirements) != 1:
            raise ValueError("lakefile.toml 必须包含唯一的 Mathlib 锁定要求")
        lake_mathlib = mathlib_requirements[0]
        mathlib_url = lake_mathlib.get("git")
        mathlib_input_revision = lake_mathlib.get("rev")
        if not isinstance(mathlib_url, str) or not mathlib_url:
            raise ValueError("lakefile.toml 的 Mathlib 锁定地址无效")
        if not isinstance(mathlib_input_revision, str) or not mathlib_input_revision:
            raise ValueError("lakefile.toml 的 Mathlib 锁定修订无效")
        if mathlib_input_revision != f"v{lean_version}":
            raise ValueError("Lean 与 Mathlib 的锁定版本不一致")

        packages = manifest.get("packages") if isinstance(manifest, dict) else None
        if not isinstance(packages, list):
            raise ValueError("lake-manifest.json 缺少锁定包列表")
        manifest_mathlib = [
            item for item in packages if isinstance(item, dict) and item.get("name") == "mathlib"
        ]
        if len(manifest_mathlib) != 1:
            raise ValueError("lake-manifest.json 必须包含唯一的 Mathlib 锁定包")
        locked_mathlib = manifest_mathlib[0]
        if locked_mathlib.get("url") != mathlib_url:
            raise ValueError("lakefile.toml 与 lake-manifest.json 的 Mathlib 锁定地址不一致")
        if locked_mathlib.get("inputRev") != mathlib_input_revision:
            raise ValueError("lakefile.toml 与 lake-manifest.json 的 Mathlib 锁定修订不一致")
        mathlib_revision = locked_mathlib.get("rev")
        if (
            not isinstance(mathlib_revision, str)
            or re.fullmatch(r"[0-9a-fA-F]{40}", mathlib_revision) is None
        ):
            raise ValueError("lake-manifest.json 的 Mathlib 解析修订不是完整提交哈希")

        digest = hashlib.sha256()
        for name, content in (
            ("lean-toolchain", toolchain_bytes),
            ("lakefile.toml", lakefile_bytes),
            ("lake-manifest.json", manifest_bytes),
        ):
            digest.update(name.encode("ascii"))
            digest.update(b"\0")
            digest.update(content)
            digest.update(b"\0")
        return cls(
            toolchain=toolchain,
            lean_version=lean_version,
            mathlib_url=mathlib_url,
            mathlib_input_revision=mathlib_input_revision,
            mathlib_revision=mathlib_revision.lower(),
            fingerprint=digest.hexdigest(),
        )


class StepResult(_FrozenModel):
    success: bool
    cancelled: bool = False
    recoverable: bool = False
    error_code: str | None = None
    error_message: str | None = None


class InitializationEvent(_FrozenModel):
    sequence: int = Field(ge=1)
    kind: Literal["progress", "log", "error"]
    step: InitializationStep | None = None
    step_status: StepStatus | None = None
    overall_status: InitializationStatus
    progress_percent: int = Field(ge=0, le=100)
    message: str
    recoverable: bool = False


class InitializationSnapshot(_FrozenModel):
    schema_version: Literal[1] = 1
    spec_fingerprint: str
    status: InitializationStatus
    steps: dict[InitializationStep, StepStatus]
    attempts: dict[InitializationStep, int]
    current_step: InitializationStep | None = None
    progress_percent: int = Field(ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None
    error_recoverable: bool = False
    logs: list[str] = Field(default_factory=list)
    sequence: int = Field(default=0, ge=0)

    @classmethod
    def fresh(cls, spec_fingerprint: str) -> InitializationSnapshot:
        return cls(
            spec_fingerprint=spec_fingerprint,
            status=InitializationStatus.NOT_STARTED,
            steps={step: StepStatus.PENDING for step in InitializationStep},
            attempts={step: 0 for step in InitializationStep},
            progress_percent=0,
        )


class InitializationBackend(Protocol):
    @property
    def workspace_root(self) -> Path: ...

    def is_ready(self, spec: EnvironmentSpec) -> bool: ...

    def run_step(
        self,
        step: InitializationStep,
        spec: EnvironmentSpec,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult: ...


class EnvironmentStateStore:
    def __init__(self, state_root: Path) -> None:
        self.root = state_root.resolve()
        self.path = self.root / "initialization-state.json"

    def load(self) -> InitializationSnapshot | None:
        try:
            return InitializationSnapshot.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            return None

    def save(self, snapshot: InitializationSnapshot) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / f".{self.path.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(snapshot.model_dump_json(indent=2))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


EventCallback = Callable[[InitializationEvent], None]


class EnvironmentInitializer:
    def __init__(
        self,
        project_root: Path,
        state_root: Path,
        backend: InitializationBackend,
        logger: logging.Logger,
    ) -> None:
        self._project_root = project_root.resolve()
        self._backend = backend
        self._logger = logger
        self._store = EnvironmentStateStore(state_root)
        self._spec = EnvironmentSpec.from_project(self._project_root)
        loaded = self._store.load()
        self._snapshot = (
            loaded
            if loaded is not None and loaded.spec_fingerprint == self._spec.fingerprint
            else InitializationSnapshot.fresh(self._spec.fingerprint)
        )
        self._events: list[InitializationEvent] = []
        self._event_lock = threading.RLock()
        self._run_lock = threading.Lock()
        self._cancel_lock = threading.Lock()
        self._active_cancel_event: threading.Event | None = None

    @property
    def workspace_root(self) -> Path:
        return self._backend.workspace_root.resolve()

    @property
    def snapshot(self) -> InitializationSnapshot:
        return self._snapshot

    @property
    def events(self) -> tuple[InitializationEvent, ...]:
        return tuple(self._events)

    def needs_initialization(self) -> bool:
        self._refresh_spec()
        if self._snapshot.status is not InitializationStatus.COMPLETED:
            return True
        try:
            return not self._backend.is_ready(self._spec)
        except Exception as error:
            self._logger.warning("环境就绪检查失败：%s", error)
            return True

    def cancel(self) -> None:
        with self._cancel_lock:
            if self._active_cancel_event is not None:
                self._active_cancel_event.set()

    def run(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: EventCallback | None = None,
    ) -> InitializationSnapshot:
        return self._execute("run", cancel_event=cancel_event, on_event=on_event)

    def retry(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: EventCallback | None = None,
    ) -> InitializationSnapshot:
        return self._execute("retry", cancel_event=cancel_event, on_event=on_event)

    def resume(
        self,
        *,
        cancel_event: threading.Event | None = None,
        on_event: EventCallback | None = None,
    ) -> InitializationSnapshot:
        return self._execute("resume", cancel_event=cancel_event, on_event=on_event)

    def _execute(
        self,
        mode: Literal["run", "retry", "resume"],
        *,
        cancel_event: threading.Event | None,
        on_event: EventCallback | None,
    ) -> InitializationSnapshot:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("环境初始化已经在运行")
        token = cancel_event or threading.Event()
        with self._cancel_lock:
            self._active_cancel_event = token
        try:
            self._refresh_spec()
            completed = self._snapshot.status is InitializationStatus.COMPLETED
            if completed and self._is_ready():
                return self._mark_ready(on_event)
            if mode == "run" or self._snapshot.status is InitializationStatus.COMPLETED:
                self._snapshot = InitializationSnapshot.fresh(self._spec.fingerprint)
            else:
                self._prepare_recovery()
            return self._run_steps(token, on_event)
        finally:
            with self._cancel_lock:
                self._active_cancel_event = None
            self._run_lock.release()

    def _refresh_spec(self) -> None:
        current = EnvironmentSpec.from_project(self._project_root)
        if current.fingerprint != self._spec.fingerprint:
            self._spec = current
            self._snapshot = InitializationSnapshot.fresh(current.fingerprint)

    def _is_ready(self) -> bool:
        try:
            return self._backend.is_ready(self._spec)
        except Exception as error:
            self._logger.warning("环境就绪检查失败，将重新初始化：%s", error)
            return False

    def _mark_ready(self, on_event: EventCallback | None) -> InitializationSnapshot:
        attempts = dict(self._snapshot.attempts)
        self._snapshot = self._snapshot.model_copy(
            update={
                "status": InitializationStatus.COMPLETED,
                "steps": {step: StepStatus.SUCCEEDED for step in InitializationStep},
                "attempts": attempts,
                "current_step": InitializationStep.COMPLETE,
                "progress_percent": 100,
                "error_code": None,
                "error_message": None,
                "error_recoverable": False,
            }
        )
        self._publish(
            kind="progress",
            step=InitializationStep.COMPLETE,
            step_status=StepStatus.SUCCEEDED,
            message=STEP_LABELS[InitializationStep.COMPLETE],
            on_event=on_event,
        )
        return self._snapshot

    def _prepare_recovery(self) -> None:
        steps = dict(self._snapshot.steps)
        for step, status in tuple(steps.items()):
            if status in {StepStatus.RUNNING, StepStatus.FAILED, StepStatus.CANCELLED}:
                steps[step] = StepStatus.PENDING
        self._snapshot = self._snapshot.model_copy(
            update={
                "status": InitializationStatus.NOT_STARTED,
                "steps": steps,
                "current_step": None,
                "error_code": None,
                "error_message": None,
                "error_recoverable": False,
            }
        )

    def _run_steps(
        self,
        cancel_event: threading.Event,
        on_event: EventCallback | None,
    ) -> InitializationSnapshot:
        action_steps = tuple(
            step for step in InitializationStep if step is not InitializationStep.COMPLETE
        )
        for index, step in enumerate(action_steps):
            if self._snapshot.steps[step] is StepStatus.SUCCEEDED:
                continue
            if cancel_event.is_set():
                return self._mark_cancelled(step, index, on_event)
            self._start_step(step, index, on_event)

            try:
                result = self._backend.run_step(
                    step,
                    self._spec,
                    cancel_event,
                    self._log_emitter(step, on_event),
                )
            except Exception as error:
                result = StepResult(
                    success=False,
                    error_code="INITIALIZATION_BACKEND_ERROR",
                    error_message=str(error),
                )
            if result.cancelled or cancel_event.is_set():
                return self._mark_cancelled(step, index, on_event, result)
            if not result.success:
                return self._mark_failed(step, index, result, on_event)
            self._finish_step(step, index, on_event)
        return self._mark_ready(on_event)

    def _start_step(
        self,
        step: InitializationStep,
        index: int,
        on_event: EventCallback | None,
    ) -> None:
        steps = dict(self._snapshot.steps)
        attempts = dict(self._snapshot.attempts)
        steps[step] = StepStatus.RUNNING
        attempts[step] += 1
        self._snapshot = self._snapshot.model_copy(
            update={
                "status": InitializationStatus.RUNNING,
                "steps": steps,
                "attempts": attempts,
                "current_step": step,
                "progress_percent": index * 100 // len(InitializationStep),
                "error_code": None,
                "error_message": None,
                "error_recoverable": False,
            }
        )
        self._publish(
            kind="progress",
            step=step,
            step_status=StepStatus.RUNNING,
            message=STEP_LABELS[step],
            on_event=on_event,
        )

    def _finish_step(
        self,
        step: InitializationStep,
        index: int,
        on_event: EventCallback | None,
    ) -> None:
        steps = dict(self._snapshot.steps)
        steps[step] = StepStatus.SUCCEEDED
        self._snapshot = self._snapshot.model_copy(
            update={
                "steps": steps,
                "progress_percent": (index + 1) * 100 // len(InitializationStep),
            }
        )
        self._publish(
            kind="progress",
            step=step,
            step_status=StepStatus.SUCCEEDED,
            message=f"{STEP_LABELS[step]}完成",
            on_event=on_event,
        )

    def _mark_failed(
        self,
        step: InitializationStep,
        index: int,
        result: StepResult,
        on_event: EventCallback | None,
    ) -> InitializationSnapshot:
        steps = dict(self._snapshot.steps)
        steps[step] = StepStatus.FAILED
        message = result.error_message or f"{STEP_LABELS[step]}失败"
        self._snapshot = self._snapshot.model_copy(
            update={
                "status": InitializationStatus.FAILED,
                "steps": steps,
                "current_step": step,
                "progress_percent": index * 100 // len(InitializationStep),
                "error_code": result.error_code or "INITIALIZATION_STEP_FAILED",
                "error_message": message,
                "error_recoverable": result.recoverable,
            }
        )
        self._publish(
            kind="error",
            step=step,
            step_status=StepStatus.FAILED,
            message=message,
            recoverable=result.recoverable,
            on_event=on_event,
        )
        return self._snapshot

    def _mark_cancelled(
        self,
        step: InitializationStep,
        index: int,
        on_event: EventCallback | None,
        result: StepResult | None = None,
    ) -> InitializationSnapshot:
        steps = dict(self._snapshot.steps)
        steps[step] = StepStatus.CANCELLED
        message = (result.error_message if result is not None else None) or "初始化已取消"
        self._snapshot = self._snapshot.model_copy(
            update={
                "status": InitializationStatus.CANCELLED,
                "steps": steps,
                "current_step": step,
                "progress_percent": index * 100 // len(InitializationStep),
                "error_code": (result.error_code if result is not None else None) or "CANCELLED",
                "error_message": message,
                "error_recoverable": True,
            }
        )
        self._publish(
            kind="error",
            step=step,
            step_status=StepStatus.CANCELLED,
            message=message,
            recoverable=True,
            on_event=on_event,
        )
        return self._snapshot

    def _publish(
        self,
        *,
        kind: Literal["progress", "log", "error"],
        step: InitializationStep | None,
        step_status: StepStatus | None,
        message: str,
        on_event: EventCallback | None,
        recoverable: bool = False,
    ) -> None:
        message = redact_sensitive_values(message)
        if self._snapshot.error_message is not None:
            self._snapshot = self._snapshot.model_copy(
                update={
                    "error_message": redact_sensitive_values(self._snapshot.error_message)
                }
            )
        sequence = self._snapshot.sequence + 1
        self._snapshot = self._snapshot.model_copy(update={"sequence": sequence})
        event = InitializationEvent(
            sequence=sequence,
            kind=kind,
            step=step,
            step_status=step_status,
            overall_status=self._snapshot.status,
            progress_percent=self._snapshot.progress_percent,
            message=message,
            recoverable=recoverable,
        )
        self._events.append(event)
        self._store.save(self._snapshot)
        if kind == "error":
            self._logger.error(message)
        else:
            self._logger.info(message)
        if on_event is not None:
            try:
                on_event(event)
            except Exception as error:
                self._logger.error(
                    "初始化事件回调失败：%s",
                    type(error).__name__,
                )

    def _log_emitter(
        self,
        step: InitializationStep,
        on_event: EventCallback | None,
    ) -> Callable[[str], None]:
        def emit(message: str) -> None:
            with self._event_lock:
                text = redact_sensitive_values(str(message))
                self._snapshot = self._snapshot.model_copy(
                    update={"logs": [*self._snapshot.logs, text]}
                )
                self._publish(
                    kind="log",
                    step=step,
                    step_status=StepStatus.RUNNING,
                    message=text,
                    on_event=on_event,
                )

        return emit
