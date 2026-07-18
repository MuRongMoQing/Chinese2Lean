from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from chinese2lean.product.initialization import (
    STEP_LABELS,
    EnvironmentInitializer,
    EnvironmentSpec,
    EnvironmentStateStore,
    InitializationEvent,
    InitializationSnapshot,
    InitializationStatus,
    InitializationStep,
    StepResult,
    StepStatus,
)

ROOT = Path(__file__).parents[1]
ACTION_STEPS = tuple(step for step in InitializationStep if step is not InitializationStep.COMPLETE)


class FakeBackend:
    def __init__(self, workspace_root: Path, *, ready: bool = False) -> None:
        self._workspace_root = workspace_root
        self.ready = ready
        self.calls: list[InitializationStep] = []
        self.results: dict[InitializationStep, list[StepResult]] = {}
        self.ready_checks = 0

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def is_ready(self, spec: EnvironmentSpec) -> bool:
        self.ready_checks += 1
        return self.ready

    def run_step(
        self,
        step: InitializationStep,
        spec: EnvironmentSpec,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult:
        self.calls.append(step)
        emit_log(f"running {step.value}")
        queued = self.results.get(step, [])
        if queued:
            return queued.pop(0)
        return StepResult(success=True)


def _copy_locks(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("lean-toolchain", "lakefile.toml", "lake-manifest.json"):
        (destination / name).write_bytes((ROOT / name).read_bytes())


def test_public_initialization_contract_has_the_six_required_chinese_steps() -> None:
    assert list(InitializationStep) == [
        InitializationStep.CHECK_SYSTEM,
        InitializationStep.PREPARE_RUNTIME,
        InitializationStep.CONFIGURE_LEAN,
        InitializationStep.CONFIGURE_MATHLIB,
        InitializationStep.VERIFY_ENVIRONMENT,
        InitializationStep.COMPLETE,
    ]
    assert STEP_LABELS == {
        InitializationStep.CHECK_SYSTEM: "检查系统环境",
        InitializationStep.PREPARE_RUNTIME: "准备运行环境",
        InitializationStep.CONFIGURE_LEAN: "配置 Lean",
        InitializationStep.CONFIGURE_MATHLIB: "配置 Mathlib",
        InitializationStep.VERIFY_ENVIRONMENT: "验证编译环境",
        InitializationStep.COMPLETE: "初始化完成",
    }


def test_environment_spec_reads_and_cross_checks_the_three_lock_files() -> None:
    spec = EnvironmentSpec.from_project(ROOT)

    assert spec.toolchain == "leanprover/lean4:v4.19.0"
    assert spec.lean_version == "4.19.0"
    assert spec.mathlib_input_revision == "v4.19.0"
    assert spec.mathlib_revision == "c44e0c8ee63ca166450922a373c7409c5d26b00b"
    assert spec.mathlib_url == "https://github.com/leanprover-community/mathlib4.git"
    assert len(spec.fingerprint) == 64


@pytest.mark.parametrize("conflict", ["revision", "url", "lean"])
def test_environment_spec_rejects_lock_conflicts(tmp_path: Path, conflict: str) -> None:
    _copy_locks(tmp_path)
    if conflict == "lean":
        (tmp_path / "lean-toolchain").write_text(
            "leanprover/lean4:v4.18.0\n", encoding="utf-8"
        )
    elif conflict == "revision":
        manifest = json.loads((tmp_path / "lake-manifest.json").read_text(encoding="utf-8"))
        mathlib = next(item for item in manifest["packages"] if item["name"] == "mathlib")
        mathlib["inputRev"] = "v4.18.0"
        (tmp_path / "lake-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        manifest = json.loads((tmp_path / "lake-manifest.json").read_text(encoding="utf-8"))
        mathlib = next(item for item in manifest["packages"] if item["name"] == "mathlib")
        mathlib["url"] = "https://example.invalid/mathlib.git"
        (tmp_path / "lake-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="锁定"):
        EnvironmentSpec.from_project(tmp_path)


def test_ready_artifacts_without_completed_state_still_run_validation_steps(
    tmp_path: Path,
) -> None:
    backend = FakeBackend(tmp_path / "workspace", ready=True)
    events: list[InitializationEvent] = []
    initializer = EnvironmentInitializer(ROOT, tmp_path / "state", backend, logging.getLogger())

    snapshot = initializer.run(on_event=events.append)

    assert snapshot.status is InitializationStatus.COMPLETED
    assert snapshot.progress_percent == 100
    assert set(snapshot.steps.values()) == {StepStatus.SUCCEEDED}
    assert backend.calls == list(ACTION_STEPS)
    assert backend.ready_checks == 0
    assert initializer.needs_initialization() is False
    assert initializer.workspace_root == (tmp_path / "workspace").resolve()
    assert events[-1].step is InitializationStep.COMPLETE

    backend.calls.clear()
    assert initializer.resume().status is InitializationStatus.COMPLETED
    assert backend.calls == []


def test_run_persists_progress_logs_and_all_action_steps(tmp_path: Path) -> None:
    backend = FakeBackend(tmp_path / "workspace")
    state_root = tmp_path / "state"
    events: list[InitializationEvent] = []
    initializer = EnvironmentInitializer(ROOT, state_root, backend, logging.getLogger())

    snapshot = initializer.run(on_event=events.append)
    persisted = EnvironmentStateStore(state_root).load()

    assert backend.calls == list(ACTION_STEPS)
    assert snapshot.status is InitializationStatus.COMPLETED
    assert persisted == snapshot
    assert snapshot.logs == [f"running {step.value}" for step in ACTION_STEPS]
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert events[-1].progress_percent == 100


def test_failed_step_is_retried_without_repeating_successful_steps(tmp_path: Path) -> None:
    backend = FakeBackend(tmp_path / "workspace")
    backend.results[InitializationStep.CONFIGURE_LEAN] = [
        StepResult(
            success=False,
            recoverable=True,
            error_code="LEAN_INSTALL_FAILED",
            error_message="offline",
        ),
        StepResult(success=True),
    ]
    initializer = EnvironmentInitializer(ROOT, tmp_path / "state", backend, logging.getLogger())

    failed = initializer.run()
    recovered = initializer.retry()

    assert failed.status is InitializationStatus.FAILED
    assert failed.current_step is InitializationStep.CONFIGURE_LEAN
    assert failed.error_code == "LEAN_INSTALL_FAILED"
    assert failed.error_recoverable is True
    assert recovered.status is InitializationStatus.COMPLETED
    assert backend.calls == [
        InitializationStep.CHECK_SYSTEM,
        InitializationStep.PREPARE_RUNTIME,
        InitializationStep.CONFIGURE_LEAN,
        InitializationStep.CONFIGURE_LEAN,
        InitializationStep.CONFIGURE_MATHLIB,
        InitializationStep.VERIFY_ENVIRONMENT,
    ]
    assert recovered.attempts[InitializationStep.CONFIGURE_LEAN] == 2


def test_cancelled_run_can_resume_from_the_cancelled_step(tmp_path: Path) -> None:
    cancel_event = threading.Event()

    class CancellingBackend(FakeBackend):
        def run_step(
            self,
            step: InitializationStep,
            spec: EnvironmentSpec,
            step_cancel_event: threading.Event,
            emit_log: Callable[[str], None],
        ) -> StepResult:
            result = super().run_step(step, spec, step_cancel_event, emit_log)
            if step is InitializationStep.PREPARE_RUNTIME and len(self.calls) == 2:
                cancel_event.set()
                return StepResult(success=False, cancelled=True, error_code="CANCELLED")
            return result

    backend = CancellingBackend(tmp_path / "workspace")
    initializer = EnvironmentInitializer(ROOT, tmp_path / "state", backend, logging.getLogger())

    cancelled = initializer.run(cancel_event=cancel_event)
    cancel_event.clear()
    resumed = initializer.resume(cancel_event=cancel_event)

    assert cancelled.status is InitializationStatus.CANCELLED
    assert cancelled.steps[InitializationStep.PREPARE_RUNTIME] is StepStatus.CANCELLED
    assert resumed.status is InitializationStatus.COMPLETED
    assert backend.calls.count(InitializationStep.CHECK_SYSTEM) == 1
    assert backend.calls.count(InitializationStep.PREPARE_RUNTIME) == 2


def test_corrupt_state_and_changed_fingerprint_start_safely(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "initialization-state.json").write_text("{broken", encoding="utf-8")
    backend = FakeBackend(tmp_path / "workspace")
    initializer = EnvironmentInitializer(ROOT, state_root, backend, logging.getLogger())

    assert initializer.resume().status is InitializationStatus.COMPLETED

    project = tmp_path / "project"
    _copy_locks(project)
    changed_backend = FakeBackend(tmp_path / "changed-workspace")
    changed = EnvironmentInitializer(project, state_root, changed_backend, logging.getLogger())
    (project / "lean-toolchain").write_text(
        "leanprover/lean4:v4.19.0\n\n", encoding="utf-8"
    )

    assert changed.resume().status is InitializationStatus.COMPLETED
    assert changed_backend.calls == list(ACTION_STEPS)


def test_completed_state_is_revalidated_instead_of_blindly_trusted(tmp_path: Path) -> None:
    backend = FakeBackend(tmp_path / "workspace", ready=True)
    state_root = tmp_path / "state"
    initializer = EnvironmentInitializer(ROOT, state_root, backend, logging.getLogger())
    assert initializer.run().status is InitializationStatus.COMPLETED

    backend.calls.clear()
    backend.ready = False
    restarted = initializer.resume()

    assert backend.ready_checks >= 1
    assert restarted.status is InitializationStatus.COMPLETED
    assert backend.calls == list(ACTION_STEPS)


def test_state_store_replaces_json_atomically(tmp_path: Path) -> None:
    store = EnvironmentStateStore(tmp_path / "state")
    snapshot = InitializationSnapshot.fresh(EnvironmentSpec.from_project(ROOT).fingerprint)

    store.save(snapshot)

    assert store.load() == snapshot
    assert list((tmp_path / "state").glob("*.tmp")) == []


def test_persisted_logs_events_and_errors_redact_credentials(tmp_path: Path) -> None:
    backend = FakeBackend(tmp_path / "workspace")
    backend.results[InitializationStep.CHECK_SYSTEM] = [
        StepResult(
            success=False,
            error_code="CHECK_FAILED",
            error_message="password=hunter2 unavailable",
        )
    ]

    original_run_step = backend.run_step

    def run_step_with_secret(
        step: InitializationStep,
        spec: EnvironmentSpec,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult:
        emit_log("token=plain-text must not persist")
        return original_run_step(step, spec, cancel_event, lambda _message: None)

    backend.run_step = run_step_with_secret  # type: ignore[method-assign]
    events: list[InitializationEvent] = []
    initializer = EnvironmentInitializer(
        ROOT,
        tmp_path / "state",
        backend,
        logging.getLogger(),
    )

    snapshot = initializer.run(on_event=events.append)
    persisted = (tmp_path / "state" / "initialization-state.json").read_text(encoding="utf-8")

    assert snapshot.logs == ["token=[REDACTED] must not persist"]
    assert snapshot.error_message == "password=[REDACTED] unavailable"
    assert all(
        "plain-text" not in event.message and "hunter2" not in event.message
        for event in events
    )
    assert "plain-text" not in persisted
    assert "hunter2" not in persisted


def test_parallel_process_logs_are_serialized_without_losing_state(tmp_path: Path) -> None:
    class ParallelLoggingBackend(FakeBackend):
        def run_step(
            self,
            step: InitializationStep,
            spec: EnvironmentSpec,
            cancel_event: threading.Event,
            emit_log: Callable[[str], None],
        ) -> StepResult:
            if step is not InitializationStep.CHECK_SYSTEM:
                return StepResult(success=True)
            workers = [
                threading.Thread(
                    target=lambda prefix=prefix: [
                        emit_log(f"{prefix}-{index}") for index in range(20)
                    ]
                )
                for prefix in ("stdout", "stderr")
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            return StepResult(success=True)

    initializer = EnvironmentInitializer(
        ROOT,
        tmp_path / "state",
        ParallelLoggingBackend(tmp_path / "workspace"),
        logging.getLogger(),
    )

    snapshot = initializer.run()
    persisted = EnvironmentStateStore(tmp_path / "state").load()

    assert snapshot.status is InitializationStatus.COMPLETED
    assert len(snapshot.logs) == 40
    assert len(set(snapshot.logs)) == 40
    assert persisted == snapshot


def test_event_callback_failure_does_not_abort_initialization(tmp_path: Path) -> None:
    initializer = EnvironmentInitializer(
        ROOT,
        tmp_path / "state",
        FakeBackend(tmp_path / "workspace"),
        logging.getLogger(),
    )

    def broken_callback(_event: InitializationEvent) -> None:
        raise UnicodeEncodeError("gbk", "✔", 0, 1, "unsupported")

    snapshot = initializer.run(on_event=broken_callback)

    assert snapshot.status is InitializationStatus.COMPLETED
    assert EnvironmentStateStore(tmp_path / "state").load() == snapshot
