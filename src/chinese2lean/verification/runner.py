from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, Field

from chinese2lean.verification.diagnostics import LeanDiagnostic, parse_diagnostics
from chinese2lean.verification.forbidden import find_forbidden_construct


class ForbiddenLeanConstruct(ValueError):
    pass


class LeanRunResult(BaseModel):
    success: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    diagnostics: list[LeanDiagnostic] = Field(default_factory=list)
    duration_ms: float = 0.0
    command: list[str] = Field(default_factory=list)
    locked_environment: bool = False


def _as_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


class LeanRunner:
    def __init__(
        self, workspace: Path, *, timeout_seconds: float = 20.0, max_source_bytes: int = 1_000_000
    ) -> None:
        self.workspace = workspace.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_source_bytes = max_source_bytes

    def _lake_root(self) -> Path | None:
        current = self.workspace
        for candidate in (current, *current.parents):
            if (candidate / "lakefile.toml").is_file() or (candidate / "lakefile.lean").is_file():
                return candidate
        return None

    @staticmethod
    def _locked_lake(lake_root: Path) -> tuple[str, bool]:
        toolchain_path = lake_root / "lean-toolchain"
        if toolchain_path.is_file():
            specification = toolchain_path.read_text(encoding="utf-8").strip()
            directory = specification.replace("/", "--").replace(":", "---")
            elan_home_value = os.environ.get("ELAN_HOME")
            if elan_home_value:
                elan_home = Path(elan_home_value)
            else:
                profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
                elan_home = profile / ".elan"
            executable = "lake.exe" if os.name == "nt" else "lake"
            pinned = elan_home / "toolchains" / directory / "bin" / executable
            if pinned.is_file():
                return str(pinned), True
        discovered = shutil.which("lake")
        return discovered or "lake", False

    @staticmethod
    def _subprocess_environment(lake_root: Path) -> dict[str, str]:
        environment = dict(os.environ)
        repositories = [lake_root]
        packages = lake_root / ".lake" / "packages"
        if packages.is_dir():
            repositories.extend(sorted(path.parent.resolve() for path in packages.glob("*/.git")))
        environment["GIT_CONFIG_COUNT"] = str(len(repositories))
        for index, repository in enumerate(repositories):
            environment[f"GIT_CONFIG_KEY_{index}"] = "safe.directory"
            environment[f"GIT_CONFIG_VALUE_{index}"] = str(repository)
        return environment

    def validate_source(self, source: str) -> None:
        if len(source.encode("utf-8")) > self.max_source_bytes:
            raise ValueError("Lean 源文件超过大小限制。")
        forbidden = find_forbidden_construct(source)
        if forbidden:
            raise ForbiddenLeanConstruct(f"禁止的 Lean 构造：{forbidden}")

    def verify_file(self, path: Path) -> LeanRunResult:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        if resolved.suffix.lower() != ".lean":
            raise ValueError("只能验证 .lean 文件。")
        return self.verify_code(resolved.read_text(encoding="utf-8"))

    def verify_code(self, source: str) -> LeanRunResult:
        self.validate_source(source)
        lake_root = self._lake_root()
        if lake_root is None:
            return LeanRunResult(
                success=False,
                exit_code=None,
                stderr="Lean 工作区不存在",
                diagnostics=[
                    LeanDiagnostic(
                        severity="error", code="WORKSPACE_MISSING", message="找不到 Lake 项目根目录"
                    )
                ],
            )
        lake, locked = self._locked_lake(lake_root)
        with tempfile.TemporaryDirectory(prefix="chinese2lean-") as temporary:
            generated = Path(temporary) / "Generated.lean"
            generated.write_text(source, encoding="utf-8", newline="\n")
            command = [lake, "env", "lean", str(generated)]
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    cwd=lake_root,
                    env=self._subprocess_environment(lake_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired as error:
                return LeanRunResult(
                    success=False,
                    exit_code=None,
                    stdout=_as_text(error.stdout),
                    stderr=_as_text(error.stderr),
                    timed_out=True,
                    diagnostics=[
                        LeanDiagnostic(severity="error", code="TIMEOUT", message="Lean 验证超时")
                    ],
                    duration_ms=(time.perf_counter() - started) * 1000,
                    command=command,
                    locked_environment=locked,
                )
            except FileNotFoundError:
                return LeanRunResult(
                    success=False,
                    exit_code=None,
                    stderr="找不到 lake 可执行文件",
                    diagnostics=[
                        LeanDiagnostic(
                            severity="error",
                            code="LAKE_NOT_FOUND",
                            message="找不到 lake 可执行文件",
                        )
                    ],
                    duration_ms=(time.perf_counter() - started) * 1000,
                    command=command,
                    locked_environment=locked,
                )
            combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
            process_succeeded = completed.returncode == 0
            diagnostics = parse_diagnostics(combined)
            if process_succeeded and not locked:
                diagnostics.append(
                    LeanDiagnostic(
                        severity="error",
                        code="UNLOCKED_ENVIRONMENT",
                        message="Lean 进程返回 0，但没有使用 lean-toolchain 锁定的工具链。",
                    )
                )
            return LeanRunResult(
                success=process_succeeded and locked,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                diagnostics=diagnostics,
                duration_ms=(time.perf_counter() - started) * 1000,
                command=command,
                locked_environment=locked,
            )
