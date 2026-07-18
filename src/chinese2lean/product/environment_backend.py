from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from chinese2lean.product.initialization import (
    EnvironmentSpec,
    InitializationStep,
    StepResult,
)

LOCK_FILES = ("lean-toolchain", "lakefile.toml", "lake-manifest.json")
SMOKE_FILE = Path("examples/generated/positive_add_one.lean")
LEAN_ROOT_FILE = Path("lean_workspace/Chinese2Lean.lean")
_FORBIDDEN_TOOLCHAIN_NAMES = {"latest", "stable", "beta", "nightly"}
_SAFE_ENVIRONMENT_NAMES = {
    "ALLUSERSPROFILE",
    "APPDATA",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}


class ProcessPolicyError(ValueError):
    """Raised before an untrusted or out-of-scope process can start."""


@dataclass(frozen=True, slots=True)
class ProcessAction:
    executable: Path
    arguments: tuple[str, ...]
    working_directory: Path
    timeout_seconds: float
    environment: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.executable.is_absolute():
            raise ProcessPolicyError("白名单可执行文件必须使用绝对路径")
        executable = self.executable.resolve()
        working_directory = self.working_directory.resolve()
        if not executable.is_file():
            raise ProcessPolicyError(f"白名单可执行文件不存在：{executable}")
        if not working_directory.is_dir():
            raise ProcessPolicyError(f"白名单工作目录不存在：{working_directory}")
        if not 0 < self.timeout_seconds <= 3600:
            raise ProcessPolicyError("subprocess timeout 必须在 0 到 3600 秒之间")
        if any("\x00" in item for item in self.arguments):
            raise ProcessPolicyError("subprocess 参数包含非法空字符")
        object.__setattr__(self, "executable", executable)
        object.__setattr__(self, "working_directory", working_directory)
        object.__setattr__(self, "environment", dict(self.environment))


@dataclass(frozen=True, slots=True)
class ProcessExecutionResult:
    success: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    error_code: str | None = None
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False
    command: list[str] = field(default_factory=list)


class _BoundedOutput:
    def __init__(self, limit: int) -> None:
        self._remaining = limit
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._lock = threading.Lock()
        self.truncated = False

    def append(self, destination: str, chunk: bytes) -> bytes:
        with self._lock:
            accepted = chunk[: self._remaining]
            self._remaining -= len(accepted)
            if len(accepted) != len(chunk):
                self.truncated = True
            if destination == "stdout":
                self._stdout.extend(accepted)
            else:
                self._stderr.extend(accepted)
            return accepted

    def text(self) -> tuple[str, str]:
        with self._lock:
            return (
                self._stdout.decode("utf-8", errors="replace"),
                self._stderr.decode("utf-8", errors="replace"),
            )


class AllowlistedProcessRunner:
    """Run fixed actions without a shell, with cancellation and bounded output."""

    def __init__(
        self,
        managed_root: Path,
        actions: Mapping[str, ProcessAction],
        *,
        output_limit_bytes: int = 1_000_000,
    ) -> None:
        self._managed_root = managed_root.resolve()
        if not self._managed_root.is_dir():
            raise ProcessPolicyError(f"受控根目录不存在：{self._managed_root}")
        if not actions:
            raise ProcessPolicyError("subprocess 动作白名单不能为空")
        if output_limit_bytes <= 0:
            raise ProcessPolicyError("subprocess 输出上限必须为正数")
        for action in actions.values():
            cwd = action.working_directory
            if cwd != self._managed_root and not cwd.is_relative_to(self._managed_root):
                raise ProcessPolicyError(f"白名单工作目录超出受控根目录：{cwd}")
        self._actions = dict(actions)
        self._output_limit = output_limit_bytes

    def execute(
        self,
        action_name: str,
        *,
        cancel_event: threading.Event | None = None,
        emit_log: Callable[[str], None] | None = None,
    ) -> ProcessExecutionResult:
        action = self._actions.get(action_name)
        if action is None:
            raise ProcessPolicyError(f"动作未列入白名单：{action_name}")
        token = cancel_event or threading.Event()
        command = [str(action.executable), *action.arguments]
        if token.is_set():
            return ProcessExecutionResult(
                success=False,
                exit_code=None,
                error_code="PROCESS_CANCELLED",
                cancelled=True,
                command=command,
            )

        try:
            if os.name == "nt":
                process = subprocess.Popen(
                    command,
                    cwd=action.working_directory,
                    env=dict(action.environment),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                process = subprocess.Popen(
                    command,
                    cwd=action.working_directory,
                    env=dict(action.environment),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    start_new_session=True,
                )
        except OSError as error:
            return ProcessExecutionResult(
                success=False,
                exit_code=None,
                stderr=str(error),
                error_code="PROCESS_ERROR",
                command=command,
            )

        output = _BoundedOutput(self._output_limit)
        readers = [
            self._start_reader(process.stdout, "stdout", output, emit_log),
            self._start_reader(process.stderr, "stderr", output, emit_log),
        ]
        deadline = time.monotonic() + action.timeout_seconds
        cancelled = False
        timed_out = False
        while process.poll() is None:
            if token.wait(0.025):
                cancelled = True
                self._terminate_process_tree(process)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                self._terminate_process_tree(process)
                break
        try:
            exit_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=2)
        for reader in readers:
            reader.join(timeout=2)
        stdout, stderr = output.text()
        error_code = None
        if cancelled:
            error_code = "PROCESS_CANCELLED"
        elif timed_out:
            error_code = "PROCESS_TIMEOUT"
        elif exit_code != 0:
            error_code = "PROCESS_FAILED"
        return ProcessExecutionResult(
            success=exit_code == 0 and error_code is None,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error_code=error_code,
            timed_out=timed_out,
            cancelled=cancelled,
            output_truncated=output.truncated,
            command=command,
        )

    @staticmethod
    def _start_reader(
        pipe: IO[bytes] | None,
        destination: str,
        output: _BoundedOutput,
        emit_log: Callable[[str], None] | None,
    ) -> threading.Thread:
        def read() -> None:
            if pipe is None:
                return
            try:
                while chunk := pipe.read(4096):
                    accepted = output.append(destination, chunk)
                    if accepted and emit_log is not None:
                        text = accepted.decode("utf-8", errors="replace").strip()
                        if text:
                            emit_log(text)
            finally:
                pipe.close()

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
            taskkill = system_root / "System32" / "taskkill.exe"
            if taskkill.is_file():
                try:
                    completed = subprocess.run(
                        [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                        check=False,
                        shell=False,
                    )
                    if completed.returncode == 0:
                        return
                except (OSError, subprocess.TimeoutExpired):
                    pass
        else:
            try:
                getpgid = getattr(os, "getpgid", None)
                killpg = getattr(os, "killpg", None)
                if callable(getpgid) and callable(killpg):
                    killpg(getpgid(process.pid), signal.SIGTERM)
                    return
            except OSError:
                pass
        process.terminate()


@dataclass(frozen=True, slots=True)
class ElanBootstrapAsset:
    path: Path
    sha256: str

    def verify(self) -> bool:
        if not self.path.is_absolute() or not self.path.is_file():
            return False
        if self.path.suffix.casefold() not in {".exe", ""}:
            return False
        if len(self.sha256) != 64:
            return False
        try:
            expected = bytes.fromhex(self.sha256)
        except ValueError:
            return False
        return hashlib.sha256(self.path.read_bytes()).digest() == expected


def load_bundled_elan_asset(runtime_root: Path) -> ElanBootstrapAsset | None:
    """Load a platform-specific installer only from the fixed bundled manifest."""

    root = runtime_root.resolve()
    manifest_path = root / "elan-bootstrap.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    if manifest.get("schema_version") != 1 or manifest.get("platform") != sys.platform:
        return None
    filename = manifest.get("filename")
    sha256 = manifest.get("sha256")
    if not isinstance(filename, str) or Path(filename).name != filename:
        return None
    expected_name = "elan-init.exe" if os.name == "nt" else "elan-init"
    if filename != expected_name or not isinstance(sha256, str):
        return None
    asset = ElanBootstrapAsset((root / filename).resolve(), sha256)
    return asset if asset.verify() else None


class SystemEnvironmentBackend:
    """Prepare an isolated, pinned Lean workspace for the product application."""

    def __init__(
        self,
        project_root: Path,
        environment_root: Path,
        *,
        bootstrap_asset: ElanBootstrapAsset | None = None,
        executable_search_paths: Sequence[Path] | None = None,
    ) -> None:
        self._project_root = project_root.resolve()
        self._environment_root = environment_root.resolve()
        self._workspace_root = self._environment_root / "workspace"
        self._elan_home = self._environment_root / "elan"
        self._bootstrap_asset = bootstrap_asset
        self._search_paths = (
            tuple(path.resolve() for path in executable_search_paths)
            if executable_search_paths is not None
            else self._default_search_paths()
        )

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def elan_home(self) -> Path:
        elan = self._find_executable("elan")
        if elan is None:
            return self._elan_home
        return self._elan_home_for_executable_directory(elan.parent)

    def is_ready(self, spec: EnvironmentSpec) -> bool:
        try:
            self._verify_source_locks(spec)
            self._verify_workspace_assets(spec)
            elan = self._find_executable("elan")
            lake = self._find_executable("lake")
            if elan is None or lake is None:
                return False
            if self._mathlib_head() != spec.mathlib_revision:
                return False
            mathlib_olean = (
                self._workspace_root
                / ".lake/packages/mathlib/.lake/build/lib/lean/Mathlib.olean"
            )
            if not mathlib_olean.is_file():
                return False
            version = self._execute(
                "lean_version",
                lake,
                ("env", "lean", "--version"),
                threading.Event(),
                lambda _line: None,
                timeout=30,
            )
            if not version.success or f"version {spec.lean_version}" not in version.stdout:
                return False
            smoke = self._execute(
                "ready_smoke_test",
                lake,
                ("env", "lean", SMOKE_FILE.as_posix()),
                threading.Event(),
                lambda _line: None,
                timeout=300,
            )
            return smoke.success
        except (OSError, ValueError, ProcessPolicyError):
            return False

    def run_step(
        self,
        step: InitializationStep,
        spec: EnvironmentSpec,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult:
        if cancel_event.is_set():
            return StepResult(success=False, cancelled=True, recoverable=True)
        try:
            if step is InitializationStep.CHECK_SYSTEM:
                self._verify_source_locks(spec)
                self._prepare_workspace(spec)
                emit_log(f"已核验环境锁定指纹：{spec.fingerprint}")
                return StepResult(success=True)
            if step is InitializationStep.PREPARE_RUNTIME:
                return self._prepare_runtime(cancel_event, emit_log)
            if step is InitializationStep.CONFIGURE_LEAN:
                return self._configure_lean(spec, cancel_event, emit_log)
            if step is InitializationStep.CONFIGURE_MATHLIB:
                return self._configure_mathlib(spec, cancel_event, emit_log)
            if step is InitializationStep.VERIFY_ENVIRONMENT:
                return self._verify_environment(spec, cancel_event, emit_log)
            return StepResult(
                success=False,
                error_code="INITIALIZATION_ACTION_NOT_ALLOWED",
                error_message=f"初始化步骤未列入白名单：{step}",
            )
        except (OSError, ValueError, ProcessPolicyError) as error:
            return StepResult(
                success=False,
                recoverable=True,
                error_code="ENVIRONMENT_PREPARATION_FAILED",
                error_message=str(error),
            )

    def _prepare_runtime(
        self,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult:
        if not Path(sys.executable).resolve().is_file():
            return StepResult(
                success=False,
                error_code="PYTHON_RUNTIME_MISSING",
                error_message="应用内置 Python runtime 不存在",
            )
        if self._find_executable("elan") is not None:
            emit_log("已检测到受控 Elan runtime")
            return StepResult(success=True)
        if self._bootstrap_asset is None:
            return StepResult(
                success=False,
                recoverable=True,
                error_code="ELAN_BOOTSTRAP_ASSET_MISSING",
                error_message="缺少固定版本且经过哈希校验的 Elan 安装器资产",
            )
        if not self._bootstrap_asset.verify():
            return StepResult(
                success=False,
                recoverable=True,
                error_code="ELAN_BOOTSTRAP_HASH_MISMATCH",
                error_message="Elan 安装器资产 SHA256 校验失败",
            )
        self._elan_home.mkdir(parents=True, exist_ok=True)
        result = self._execute(
            "install_elan",
            self._bootstrap_asset.path.resolve(),
            ("-y", "--default-toolchain", "none"),
            cancel_event,
            emit_log,
            timeout=300,
        )
        return self._as_step_result(result, "ELAN_BOOTSTRAP_FAILED")

    def _configure_lean(
        self,
        spec: EnvironmentSpec,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult:
        self._reject_floating_toolchain(spec.toolchain)
        elan = self._find_executable("elan")
        if elan is None:
            return StepResult(
                success=False,
                recoverable=True,
                error_code="ELAN_NOT_AVAILABLE",
                error_message="Elan 尚未准备完成",
            )
        toolchain_bin = self._toolchain_bin(elan, spec)
        lean = toolchain_bin / ("lean.exe" if os.name == "nt" else "lean")
        lake = toolchain_bin / ("lake.exe" if os.name == "nt" else "lake")
        if lean.is_file() and lake.is_file():
            version = self._execute(
                "existing_lean_version",
                lean,
                ("--version",),
                cancel_event,
                emit_log,
                timeout=30,
            )
            if not version.success:
                return self._as_step_result(version, "LEAN_VERSION_CHECK_FAILED")
            if f"version {spec.lean_version}" not in version.stdout:
                return StepResult(
                    success=False,
                    recoverable=True,
                    error_code="LEAN_VERSION_MISMATCH",
                    error_message="已安装的锁定 Lean 工具链版本与项目要求不一致。",
                )
            emit_log(f"已复用锁定的 Lean {spec.lean_version} 工具链")
            return StepResult(success=True)
        result = self._execute(
            "install_toolchain",
            elan,
            ("toolchain", "install", spec.toolchain),
            cancel_event,
            emit_log,
            timeout=600,
        )
        return self._as_step_result(result, "LEAN_TOOLCHAIN_INSTALL_FAILED")

    def _configure_mathlib(
        self,
        spec: EnvironmentSpec,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult:
        lake = self._find_executable("lake")
        if lake is None:
            return StepResult(
                success=False,
                recoverable=True,
                error_code="LAKE_NOT_AVAILABLE",
                error_message="固定 Lean 工具链中的 Lake 不可用",
            )
        result = self._execute(
            "mathlib_cache",
            lake,
            ("exe", "cache", "get"),
            cancel_event,
            emit_log,
            timeout=1200,
        )
        if not result.success:
            return self._as_step_result(result, "MATHLIB_CACHE_FAILED")
        actual_revision = self._mathlib_head()
        if actual_revision != spec.mathlib_revision:
            return StepResult(
                success=False,
                recoverable=True,
                error_code="MATHLIB_REVISION_MISMATCH",
                error_message=(
                    "Mathlib checkout 与 lake-manifest.json 不一致："
                    f"expected {spec.mathlib_revision}, got {actual_revision or 'missing'}"
                ),
            )
        return StepResult(success=True)

    def _verify_environment(
        self,
        spec: EnvironmentSpec,
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
    ) -> StepResult:
        lake = self._find_executable("lake")
        if lake is None:
            return StepResult(success=False, error_code="LAKE_NOT_AVAILABLE")
        actions = (
            ("lean_version", lake, ("env", "lean", "--version"), 30),
            (
                "lean_workspace_compile",
                lake,
                ("env", "lean", LEAN_ROOT_FILE.as_posix()),
                300,
            ),
            ("lean_smoke_test", lake, ("env", "lean", SMOKE_FILE.as_posix()), 300),
            (
                "application_version",
                Path(sys.executable).resolve(),
                ("-m", "chinese2lean.cli", "version"),
                60,
            ),
        )
        for name, executable, arguments, timeout in actions:
            result = self._execute(
                name,
                executable,
                arguments,
                cancel_event,
                emit_log,
                timeout=timeout,
            )
            if not result.success:
                return self._as_step_result(result, "ENVIRONMENT_VERIFICATION_FAILED")
            if name == "lean_version" and f"version {spec.lean_version}" not in result.stdout:
                return StepResult(
                    success=False,
                    error_code="LEAN_VERSION_MISMATCH",
                    error_message=f"Lean 版本输出与锁定版本 {spec.lean_version} 不一致",
                )
        self._verify_source_locks(spec)
        self._verify_workspace_assets(spec)
        if self._mathlib_head() != spec.mathlib_revision:
            return StepResult(success=False, error_code="MATHLIB_REVISION_MISMATCH")
        return StepResult(success=True)

    def _execute(
        self,
        name: str,
        executable: Path,
        arguments: tuple[str, ...],
        cancel_event: threading.Event,
        emit_log: Callable[[str], None],
        *,
        timeout: float,
    ) -> ProcessExecutionResult:
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        action = ProcessAction(
            executable=executable,
            arguments=arguments,
            working_directory=self._workspace_root,
            timeout_seconds=timeout,
            environment=self._safe_environment(executable.parent),
        )
        return AllowlistedProcessRunner(
            self._environment_root,
            {name: action},
        ).execute(name, cancel_event=cancel_event, emit_log=emit_log)

    def _prepare_workspace(self, spec: EnvironmentSpec) -> None:
        source_content = self._locked_source_content(spec)
        assets = {
            **source_content,
            LEAN_ROOT_FILE.as_posix(): (self._project_root / LEAN_ROOT_FILE).read_bytes(),
            SMOKE_FILE.as_posix(): (self._project_root / SMOKE_FILE).read_bytes(),
        }
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        for relative, content in assets.items():
            destination = self._workspace_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() == content:
                continue
            temporary = destination.with_name(f".{destination.name}.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, destination)
        if self._locked_source_content(spec) != source_content:
            raise ValueError("复制期间源环境锁定文件发生变化")
        self._verify_workspace_assets(spec)

    def _verify_source_locks(self, spec: EnvironmentSpec) -> None:
        current = EnvironmentSpec.from_project(self._project_root)
        if current.fingerprint != spec.fingerprint:
            raise ValueError("源环境锁定文件指纹发生变化")

    def _locked_source_content(self, spec: EnvironmentSpec) -> dict[str, bytes]:
        self._verify_source_locks(spec)
        return {name: (self._project_root / name).read_bytes() for name in LOCK_FILES}

    def _verify_workspace_assets(self, spec: EnvironmentSpec) -> None:
        workspace_spec = EnvironmentSpec.from_project(self._workspace_root)
        if workspace_spec.fingerprint != spec.fingerprint:
            raise ValueError("应用环境锁定文件与源锁定文件不一致")
        for relative in (LEAN_ROOT_FILE, SMOKE_FILE):
            source = self._project_root / relative
            destination = self._workspace_root / relative
            if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                raise ValueError(f"应用环境固定资产不一致：{relative.as_posix()}")

    def _mathlib_head(self) -> str | None:
        git_directory = self._workspace_root / ".lake/packages/mathlib/.git"
        head_path = git_directory / "HEAD"
        try:
            head = head_path.read_text(encoding="ascii").strip()
        except OSError:
            return None
        if len(head) == 40 and all(character in "0123456789abcdefABCDEF" for character in head):
            return head.casefold()
        if not head.startswith("ref: "):
            return None
        reference = head.removeprefix("ref: ").strip()
        loose = git_directory / Path(reference)
        if loose.is_file():
            return loose.read_text(encoding="ascii").strip().casefold()
        packed = git_directory / "packed-refs"
        try:
            for line in packed.read_text(encoding="ascii").splitlines():
                if not line.startswith(("#", "^")) and line.endswith(f" {reference}"):
                    return line.split(" ", maxsplit=1)[0].casefold()
        except OSError:
            return None
        return None

    def _find_executable(self, name: str) -> Path | None:
        suffix = ".exe" if os.name == "nt" else ""
        candidates = [
            self._elan_home / "bin" / f"{name}{suffix}",
            *(path / f"{name}{suffix}" for path in self._search_paths),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def _default_search_paths(self) -> tuple[Path, ...]:
        candidates: list[Path] = []
        configured_home = os.environ.get("ELAN_HOME")
        if configured_home:
            candidates.append(Path(configured_home).expanduser() / "bin")
        candidates.append(Path.home() / ".elan" / "bin")
        return tuple(path.resolve() for path in candidates)

    def _toolchain_bin(self, elan: Path, spec: EnvironmentSpec) -> Path:
        directory = spec.toolchain.replace("/", "--").replace(":", "---")
        elan_home = self._elan_home_for_executable_directory(elan.parent)
        return elan_home / "toolchains" / directory / "bin"

    def _elan_home_for_executable_directory(self, executable_directory: Path) -> Path:
        directory = executable_directory.resolve()
        if directory == (self._elan_home / "bin").resolve():
            return self._elan_home
        if directory.name.casefold() == "bin":
            if directory.parent.parent.name.casefold() == "toolchains":
                return directory.parent.parent.parent
            if (directory.parent / "toolchains").is_dir():
                return directory.parent
        return self._elan_home

    def _safe_environment(self, executable_directory: Path) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in _SAFE_ENVIRONMENT_NAMES
        }
        existing_path = environment.get("PATH", environment.get("Path", ""))
        environment["PATH"] = os.pathsep.join(
            part for part in (str(executable_directory), existing_path) if part
        )
        environment["ELAN_HOME"] = str(
            self._elan_home_for_executable_directory(executable_directory)
        )
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        return environment

    @staticmethod
    def _reject_floating_toolchain(toolchain: str) -> None:
        lowered = toolchain.casefold()
        if any(name in lowered for name in _FORBIDDEN_TOOLCHAIN_NAMES):
            raise ProcessPolicyError("禁止安装 latest/stable/beta/nightly Lean 工具链")
        if not toolchain.startswith("leanprover/lean4:v"):
            raise ProcessPolicyError("Lean 工具链必须来自锁定的 lean-toolchain")

    @staticmethod
    def _as_step_result(
        result: ProcessExecutionResult,
        failure_code: str,
    ) -> StepResult:
        if result.success:
            return StepResult(success=True)
        if result.cancelled:
            return StepResult(
                success=False,
                cancelled=True,
                recoverable=True,
                error_code="CANCELLED",
                error_message="初始化进程已取消",
            )
        message = result.stderr.strip() or result.stdout.strip() or failure_code
        return StepResult(
            success=False,
            recoverable=True,
            error_code=result.error_code or failure_code,
            error_message=message,
        )
