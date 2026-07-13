from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from chinese2lean.verification.diagnostics import LeanDiagnostic, parse_diagnostics


class ForbiddenLeanConstruct(ValueError):
    pass


class LeanRunResult(BaseModel):
    success: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    diagnostics: list[LeanDiagnostic] = Field(default_factory=list)


_FORBIDDEN = re.compile(r"\b(sorry|admit|axiom|unsafe)\b")


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

    def validate_source(self, source: str) -> None:
        if len(source.encode("utf-8")) > self.max_source_bytes:
            raise ValueError("Lean 源文件超过大小限制。")
        lines = "\n".join(line.split("--", 1)[0] for line in source.splitlines())
        without_comments = re.sub(r"/-.*?-/", "", lines, flags=re.DOTALL)
        match = _FORBIDDEN.search(without_comments)
        if match:
            raise ForbiddenLeanConstruct(f"禁止的 Lean 构造：{match.group(1)}")

    def verify_file(self, path: Path) -> LeanRunResult:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
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
        with tempfile.TemporaryDirectory(prefix="chinese2lean-") as temporary:
            generated = Path(temporary) / "Generated.lean"
            generated.write_text(source, encoding="utf-8", newline="\n")
            try:
                completed = subprocess.run(
                    ["lake", "env", "lean", str(generated)],
                    cwd=lake_root,
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
                )
            combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
            return LeanRunResult(
                success=completed.returncode == 0,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                diagnostics=parse_diagnostics(combined),
            )
