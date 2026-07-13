from typing import ClassVar

from pydantic import BaseModel

from chinese2lean.verification.runner import LeanRunner, LeanRunResult


class RepairAttempt(BaseModel):
    before_code: str
    diagnostics: list[dict[str, object]]
    change: str
    after_code: str
    success: bool


class RepairResult(BaseModel):
    code: str
    run: LeanRunResult
    attempts: list[RepairAttempt]


class DeterministicRepairer:
    TACTICS: ClassVar[tuple[str, ...]] = (
        "norm_num",
        "ring_nf",
        "linarith",
        "nlinarith",
        "positivity",
        "omega",
        "aesop",
    )
    REPAIRABLE_CODES: ClassVar[frozenset[str]] = frozenset(
        {"UNKNOWN_TACTIC", "UNSOLVED_GOALS", "TYPE_MISMATCH", "SYNTHESIS_FAILED"}
    )

    def __init__(self, runner: LeanRunner, max_attempts: int = 3) -> None:
        self.runner = runner
        self.max_attempts = min(max(max_attempts, 0), 3)

    def verify_and_repair(self, source: str) -> RepairResult:
        current, attempts = source, []
        run = self.runner.verify_code(current)
        used = self._last_tactic(current)
        for candidate in [item for item in self.TACTICS if item != used][: self.max_attempts]:
            if run.success or not self._is_repairable(run):
                break
            updated = self._replace_last_tactic(current, candidate)
            next_run = self.runner.verify_code(updated)
            attempts.append(
                RepairAttempt(
                    before_code=current,
                    diagnostics=[item.model_dump() for item in run.diagnostics],
                    change=f"将末行 tactic {used!r} 替换为 {candidate!r}",
                    after_code=updated,
                    success=next_run.success,
                )
            )
            current, run, used = updated, next_run, candidate
        return RepairResult(code=current, run=run, attempts=attempts)

    def _is_repairable(self, run: LeanRunResult) -> bool:
        return bool(run.diagnostics) and all(
            item.code in self.REPAIRABLE_CODES for item in run.diagnostics
        )

    @staticmethod
    def _last_tactic(source: str) -> str:
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        return lines[-1] if lines else ""

    @staticmethod
    def _replace_last_tactic(source: str, tactic: str) -> str:
        lines = source.rstrip().splitlines()
        lines[-1] = f"  {tactic}"
        return "\n".join(lines) + "\n"
