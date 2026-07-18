from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from chinese2lean.product.environment_backend import (
    LEAN_ROOT_FILE,
    SMOKE_FILE,
    AllowlistedProcessRunner,
    ElanBootstrapAsset,
    ProcessAction,
    ProcessExecutionResult,
    ProcessPolicyError,
    SystemEnvironmentBackend,
    load_bundled_elan_asset,
)
from chinese2lean.product.initialization import EnvironmentSpec, InitializationStep

ROOT = Path(__file__).parents[1]


def _python_action(tmp_path: Path, code: str, *, timeout: float = 5) -> ProcessAction:
    return ProcessAction(
        executable=Path(sys.executable),
        arguments=("-c", code),
        working_directory=tmp_path,
        timeout_seconds=timeout,
    )


def test_runner_executes_only_the_exact_allowlisted_argv(tmp_path: Path) -> None:
    action = _python_action(tmp_path, "print('fixed-output')")
    runner = AllowlistedProcessRunner(tmp_path, {"fixed": action})

    result = runner.execute("fixed")

    assert result.success
    assert result.command == [str(Path(sys.executable).resolve()), "-c", "print('fixed-output')"]
    assert result.stdout.strip() == "fixed-output"


def test_runner_does_not_inherit_credentials_when_action_environment_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-child")
    action = _python_action(
        tmp_path,
        "import os; print(os.environ.get('GITHUB_TOKEN', 'not-present'))",
    )

    result = AllowlistedProcessRunner(tmp_path, {"inspect": action}).execute("inspect")

    assert result.success
    assert result.stdout.strip() == "not-present"


def test_runner_rejects_unknown_actions_relative_executables_and_outside_cwd(
    tmp_path: Path,
) -> None:
    runner = AllowlistedProcessRunner(tmp_path, {"fixed": _python_action(tmp_path, "pass")})
    with pytest.raises(ProcessPolicyError, match="白名单"):
        runner.execute("unknown")
    with pytest.raises(ProcessPolicyError, match="绝对路径"):
        ProcessAction(Path("python"), (), tmp_path, 5)
    with pytest.raises(ProcessPolicyError, match="工作目录"):
        AllowlistedProcessRunner(
            tmp_path,
            {"outside": _python_action(tmp_path.parent, "pass")},
        )


def test_runner_reports_timeout_oserror_cancel_and_output_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeout_runner = AllowlistedProcessRunner(
        tmp_path,
        {"wait": _python_action(tmp_path, "import time; time.sleep(5)", timeout=0.1)},
    )
    timed_out = timeout_runner.execute("wait")
    assert timed_out.timed_out
    assert timed_out.error_code == "PROCESS_TIMEOUT"

    cancel_event = threading.Event()
    cancel_runner = AllowlistedProcessRunner(
        tmp_path,
        {"wait": _python_action(tmp_path, "import time; time.sleep(5)")},
    )
    timer = threading.Timer(0.1, cancel_event.set)
    timer.start()
    try:
        cancelled = cancel_runner.execute("wait", cancel_event=cancel_event)
    finally:
        timer.cancel()
    assert cancelled.cancelled
    assert cancelled.error_code == "PROCESS_CANCELLED"

    output_runner = AllowlistedProcessRunner(
        tmp_path,
        {"output": _python_action(tmp_path, "print('x' * 5000)")},
        output_limit_bytes=128,
    )
    limited = output_runner.execute("output")
    assert limited.success
    assert limited.output_truncated
    assert len(limited.stdout.encode("utf-8")) <= 128

    def fail_to_start(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        raise OSError("blocked")

    monkeypatch.setattr(subprocess, "Popen", fail_to_start)
    failed = AllowlistedProcessRunner(
        tmp_path,
        {"fixed": _python_action(tmp_path, "pass")},
    ).execute("fixed")
    assert failed.error_code == "PROCESS_ERROR"
    assert "blocked" in failed.stderr


def _copy_project_assets(project: Path) -> None:
    project.mkdir(parents=True)
    for name in ("lean-toolchain", "lakefile.toml", "lake-manifest.json"):
        (project / name).write_bytes((ROOT / name).read_bytes())
    lean_workspace = project / "lean_workspace"
    lean_workspace.mkdir()
    (lean_workspace / "Chinese2Lean.lean").write_text("def marker := 1\n", encoding="utf-8")
    smoke = project / "examples" / "generated"
    smoke.mkdir(parents=True)
    (smoke / "positive_add_one.lean").write_text(
        "import Mathlib\nexample : 1 + 1 = 2 := by norm_num\n",
        encoding="utf-8",
    )


def test_bootstrap_asset_requires_an_exact_sha256(tmp_path: Path) -> None:
    asset = tmp_path / "elan-init.exe"
    asset.write_bytes(b"known installer")
    valid = hashlib.sha256(asset.read_bytes()).hexdigest()

    assert ElanBootstrapAsset(asset, valid).verify()
    assert not ElanBootstrapAsset(asset, "0" * 64).verify()


def test_bundled_elan_asset_loader_uses_fixed_manifest_path_and_hash(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    asset = runtime_root / ("elan-init.exe" if sys.platform == "win32" else "elan-init")
    asset.write_bytes(b"bundled pinned installer")
    (runtime_root / "elan-bootstrap.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": sys.platform,
                "filename": asset.name,
                "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    loaded = load_bundled_elan_asset(runtime_root)

    assert loaded is not None
    assert loaded.path == asset.resolve()
    assert loaded.verify()

    manifest = json.loads((runtime_root / "elan-bootstrap.json").read_text(encoding="utf-8"))
    manifest["filename"] = "../unknown-script.exe"
    (runtime_root / "elan-bootstrap.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert load_bundled_elan_asset(runtime_root) is None


def test_backend_missing_elan_is_recoverable_and_never_uses_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        executable_search_paths=(),
    )
    spec = EnvironmentSpec.from_project(project)

    result = backend.run_step(
        InitializationStep.PREPARE_RUNTIME,
        spec,
        threading.Event(),
        lambda _line: None,
    )

    assert not result.success
    assert result.recoverable
    assert result.error_code == "ELAN_BOOTSTRAP_ASSET_MISSING"
    assert "latest" not in json.dumps(result.model_dump(), ensure_ascii=False).casefold()


def test_workspace_assets_and_lock_hashes_remain_exact(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        executable_search_paths=(),
    )
    spec = EnvironmentSpec.from_project(project)
    before = {
        name: hashlib.sha256((project / name).read_bytes()).hexdigest()
        for name in ("lean-toolchain", "lakefile.toml", "lake-manifest.json")
    }

    result = backend.run_step(
        InitializationStep.CHECK_SYSTEM,
        spec,
        threading.Event(),
        lambda _line: None,
    )

    assert result.success
    assert backend.workspace_root.joinpath("lean-toolchain").read_bytes() == (
        project / "lean-toolchain"
    ).read_bytes()
    assert backend.workspace_root.joinpath("lean_workspace/Chinese2Lean.lean").is_file()
    assert backend.workspace_root.joinpath(
        "examples/generated/positive_add_one.lean"
    ).is_file()
    assert before == {
        name: hashlib.sha256((project / name).read_bytes()).hexdigest()
        for name in before
    }


def _fake_tool(tool_directory: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    path = tool_directory / f"{name}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixed fake executable")
    return path


def test_backend_uses_exact_toolchain_argv_and_sanitized_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    tool_directory = tmp_path / "tools"
    _fake_tool(tool_directory, "elan")
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        executable_search_paths=(tool_directory,),
    )
    spec = EnvironmentSpec.from_project(project)
    observed: dict[str, object] = {}

    def execute(
        name: str,
        executable: Path,
        arguments: tuple[str, ...],
        cancel_event: threading.Event,
        emit_log: object,
        *,
        timeout: float,
    ) -> ProcessExecutionResult:
        observed.update(name=name, executable=executable, arguments=arguments, timeout=timeout)
        return ProcessExecutionResult(success=True, exit_code=0)

    monkeypatch.setattr(backend, "_execute", execute)
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-be-forwarded")

    result = backend.run_step(
        InitializationStep.CONFIGURE_LEAN,
        spec,
        threading.Event(),
        lambda _line: None,
    )

    assert result.success
    assert observed["arguments"] == (
        "toolchain",
        "install",
        "leanprover/lean4:v4.19.0",
    )
    assert "GITHUB_TOKEN" not in backend._safe_environment(tool_directory)

    floating = spec.model_copy(update={"toolchain": "stable"})
    observed.clear()
    rejected = backend.run_step(
        InitializationStep.CONFIGURE_LEAN,
        floating,
        threading.Event(),
        lambda _line: None,
    )
    assert not rejected.success
    assert observed == {}


def test_backend_rejects_bad_bootstrap_hash_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    asset_path = tmp_path / "elan-init.exe"
    asset_path.write_bytes(b"tampered")
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        bootstrap_asset=ElanBootstrapAsset(asset_path, "0" * 64),
        executable_search_paths=(),
    )
    called = False

    def unexpected(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(backend, "_execute", unexpected)
    result = backend.run_step(
        InitializationStep.PREPARE_RUNTIME,
        EnvironmentSpec.from_project(project),
        threading.Event(),
        lambda _line: None,
    )

    assert not result.success
    assert result.error_code == "ELAN_BOOTSTRAP_HASH_MISMATCH"
    assert not called


def test_ready_path_revalidates_assets_tools_mathlib_and_lean_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    tool_directory = tmp_path / "tools"
    _fake_tool(tool_directory, "elan")
    _fake_tool(tool_directory, "lake")
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        executable_search_paths=(tool_directory,),
    )
    spec = EnvironmentSpec.from_project(project)
    assert backend.run_step(
        InitializationStep.CHECK_SYSTEM,
        spec,
        threading.Event(),
        lambda _line: None,
    ).success
    git_directory = backend.workspace_root / ".lake/packages/mathlib/.git"
    git_directory.mkdir(parents=True)
    (git_directory / "HEAD").write_text(spec.mathlib_revision, encoding="ascii")
    olean = backend.workspace_root / ".lake/packages/mathlib/.lake/build/lib/lean/Mathlib.olean"
    olean.parent.mkdir(parents=True)
    olean.write_bytes(b"olean")
    monkeypatch.setattr(
        backend,
        "_execute",
        lambda *args, **kwargs: ProcessExecutionResult(
            success=True,
            exit_code=0,
            stdout="Lean (version 4.19.0, commit 6caaee842e94, Release)",
        ),
    )

    assert backend.is_ready(spec)
    (backend.workspace_root / "lake-manifest.json").write_text("{}", encoding="utf-8")
    assert not backend.is_ready(spec)


def test_mathlib_revision_mismatch_is_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    tool_directory = tmp_path / "tools"
    _fake_tool(tool_directory, "lake")
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        executable_search_paths=(tool_directory,),
    )
    backend.workspace_root.mkdir(parents=True)
    git_directory = backend.workspace_root / ".lake/packages/mathlib/.git"
    git_directory.mkdir(parents=True)
    (git_directory / "HEAD").write_text("0" * 40, encoding="ascii")
    monkeypatch.setattr(
        backend,
        "_execute",
        lambda *args, **kwargs: ProcessExecutionResult(success=True, exit_code=0),
    )

    result = backend.run_step(
        InitializationStep.CONFIGURE_MATHLIB,
        EnvironmentSpec.from_project(project),
        threading.Event(),
        lambda _line: None,
    )

    assert not result.success
    assert result.recoverable
    assert result.error_code == "MATHLIB_REVISION_MISMATCH"


def test_environment_verification_compiles_workspace_and_runs_smoke_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    tool_directory = tmp_path / "tools"
    _fake_tool(tool_directory, "lake")
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        executable_search_paths=(tool_directory,),
    )
    spec = EnvironmentSpec.from_project(project)
    assert backend.run_step(
        InitializationStep.CHECK_SYSTEM,
        spec,
        threading.Event(),
        lambda _line: None,
    ).success
    calls: list[tuple[str, tuple[str, ...]]] = []

    def execute(
        name: str,
        executable: Path,
        arguments: tuple[str, ...],
        cancel_event: threading.Event,
        emit_log: object,
        *,
        timeout: float,
    ) -> ProcessExecutionResult:
        calls.append((name, arguments))
        stdout = (
            "Lean (version 4.19.0, commit 6caaee842e94, Release)"
            if name == "lean_version"
            else ""
        )
        return ProcessExecutionResult(success=True, exit_code=0, stdout=stdout)

    monkeypatch.setattr(backend, "_execute", execute)
    monkeypatch.setattr(backend, "_mathlib_head", lambda: spec.mathlib_revision)

    result = backend.run_step(
        InitializationStep.VERIFY_ENVIRONMENT,
        spec,
        threading.Event(),
        lambda _line: None,
    )

    assert result.success
    assert calls == [
        ("lean_version", ("env", "lean", "--version")),
        ("lean_workspace_compile", ("env", "lean", LEAN_ROOT_FILE.as_posix())),
        ("lean_smoke_test", ("env", "lean", SMOKE_FILE.as_posix())),
        ("application_version", ("-m", "chinese2lean.cli", "version")),
    ]


def test_external_elan_home_reuses_the_exact_installed_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _copy_project_assets(project)
    external_home = tmp_path / "user" / ".elan"
    bin_directory = external_home / "bin"
    _fake_tool(bin_directory, "elan")
    _fake_tool(bin_directory, "lake")
    toolchain = external_home / "toolchains" / "leanprover--lean4---v4.19.0" / "bin"
    _fake_tool(toolchain, "lean")
    _fake_tool(toolchain, "lake")
    backend = SystemEnvironmentBackend(
        project,
        tmp_path / "environment",
        executable_search_paths=(bin_directory,),
    )
    calls: list[tuple[str, tuple[str, ...]]] = []

    def execute(
        name: str,
        executable: Path,
        arguments: tuple[str, ...],
        cancel_event: threading.Event,
        emit_log: object,
        *,
        timeout: float,
    ) -> ProcessExecutionResult:
        calls.append((name, arguments))
        return ProcessExecutionResult(
            success=True,
            exit_code=0,
            stdout="Lean (version 4.19.0, commit 6caaee842e94, Release)",
        )

    monkeypatch.setattr(backend, "_execute", execute)

    result = backend.run_step(
        InitializationStep.CONFIGURE_LEAN,
        EnvironmentSpec.from_project(project),
        threading.Event(),
        lambda _line: None,
    )

    assert result.success
    assert calls == [("existing_lean_version", ("--version",))]
    assert backend.elan_home == external_home.resolve()
    assert backend._safe_environment(bin_directory)["ELAN_HOME"] == str(external_home)
