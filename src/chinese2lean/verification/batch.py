from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from chinese2lean.verification.diagnostics import LeanDiagnostic
from chinese2lean.verification.runner import LeanRunner


class BatchFileResult(BaseModel):
    path: str
    verified: bool
    duration_ms: float
    diagnostics: list[LeanDiagnostic] = Field(default_factory=list)


class BatchVerificationResult(BaseModel):
    total: int
    verified: int
    failed: int
    files: list[BatchFileResult]

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0


def verify_all(directory: Path, runner: LeanRunner) -> BatchVerificationResult:
    """Compile every Lean file below a directory in stable path order."""
    root = directory.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    files: list[BatchFileResult] = []
    for path in sorted(root.rglob("*.lean"), key=lambda item: item.as_posix()):
        try:
            run = runner.verify_file(path)
            files.append(
                BatchFileResult(
                    path=str(path),
                    verified=run.success and run.locked_environment,
                    duration_ms=run.duration_ms,
                    diagnostics=run.diagnostics,
                )
            )
        except (OSError, ValueError) as error:
            files.append(
                BatchFileResult(
                    path=str(path),
                    verified=False,
                    duration_ms=0,
                    diagnostics=[
                        LeanDiagnostic(
                            severity="error",
                            code="BATCH_FILE_ERROR",
                            message=str(error),
                        )
                    ],
                )
            )
    verified = sum(item.verified for item in files)
    return BatchVerificationResult(
        total=len(files),
        verified=verified,
        failed=len(files) - verified,
        files=files,
    )
