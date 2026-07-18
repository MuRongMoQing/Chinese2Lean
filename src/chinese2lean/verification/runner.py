from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, Field

from chinese2lean.verification.diagnostics import LeanDiagnostic, parse_diagnostics
from chinese2lean.verification.forbidden import find_forbidden_construct
from chinese2lean.verification.process import AllowedCommand, ControlledProcessRunner


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


class LeanRunner:
    def __init__(
        self,
        workspace: Path,
        *,
        timeout_seconds: float = 120.0,
        max_source_bytes: int = 1_000_000,
        elan_home: Path | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_source_bytes = max_source_bytes
        self.elan_home = elan_home.resolve() if elan_home is not None else None

    def _lake_root(self) -> Path | None:
        current = self.workspace
        for candidate in (current, *current.parents):
            if (candidate / "lakefile.toml").is_file() or (candidate / "lakefile.lean").is_file():
                return candidate
        return None

    def _locked_lake(self, lake_root: Path) -> tuple[str, bool] | None:
        toolchain_path = lake_root / "lean-toolchain"
        if toolchain_path.is_file():
            specification = toolchain_path.read_text(encoding="utf-8").strip()
            directory = specification.replace("/", "--").replace(":", "---")
            if self.elan_home is not None:
                elan_home = self.elan_home
            else:
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
        return None

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
        locked_lake = self._locked_lake(lake_root)
        if locked_lake is None:
            return LeanRunResult(
                success=False,
                exit_code=None,
                stderr="找不到 lean-toolchain 锁定的 lake 可执行文件",
                diagnostics=[
                    LeanDiagnostic(
                        severity="error",
                        code="LOCKED_TOOLCHAIN_MISSING",
                        message="找不到 lean-toolchain 锁定的 lake 可执行文件",
                    )
                ],
            )
        lake, locked = locked_lake
        with tempfile.TemporaryDirectory(prefix="chinese2lean-") as temporary:
            generated = Path(temporary) / "Generated.lean"
            generated.write_text(source, encoding="utf-8", newline="\n")
            started = time.perf_counter()
            completed = ControlledProcessRunner(
                {
                    "lean_verify": AllowedCommand(
                        executable=Path(lake),
                        working_directory=lake_root,
                        timeout_seconds=self.timeout_seconds,
                        fixed_arguments=("env", "lean"),
                        argument_policy=lambda arguments: arguments == (str(generated),),
                    )
                }
            ).execute(
                "lean_verify",
                arguments=(str(generated),),
                environment=self._subprocess_environment(lake_root),
            )
            if completed.timed_out:
                return LeanRunResult(
                    success=False,
                    exit_code=None,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    timed_out=True,
                    diagnostics=[
                        LeanDiagnostic(severity="error", code="TIMEOUT", message="Lean 验证超时")
                    ],
                    duration_ms=(time.perf_counter() - started) * 1000,
                    command=completed.command,
                    locked_environment=locked,
                )
            if completed.error_code == "PROCESS_ERROR":
                return LeanRunResult(
                    success=False,
                    exit_code=None,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    diagnostics=[
                        LeanDiagnostic(
                            severity="error",
                            code="PROCESS_ERROR",
                            message=completed.stderr or "Lean 进程执行失败",
                        )
                    ],
                    duration_ms=(time.perf_counter() - started) * 1000,
                    command=completed.command,
                    locked_environment=locked,
                )
            combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
            process_succeeded = completed.success
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
                exit_code=completed.exit_code,
                stdout=completed.stdout,
                stderr=completed.stderr,
                diagnostics=diagnostics,
                duration_ms=(time.perf_counter() - started) * 1000,
                command=completed.command,
                locked_environment=locked,
            )
