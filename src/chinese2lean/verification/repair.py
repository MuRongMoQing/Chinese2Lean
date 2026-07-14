from typing import ClassVar

from pydantic import BaseModel

from chinese2lean.verification.diagnostics import LeanDiagnostic
from chinese2lean.verification.invariance import (
    StatementChanged,
    ensure_statement_unchanged,
    statement_source_fingerprint,
)
from chinese2lean.verification.runner import LeanRunner, LeanRunResult


class RepairAttempt(BaseModel):
    attempt: int
    diagnostic_category: str
    before_code: str
    diagnostics: list[dict[str, object]]
    change_summary: str
    after_code: str
    statement_hash_before: str
    statement_hash_after: str
    verified: bool


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
        {
            "UNKNOWN_TACTIC",
            "UNKNOWN_IDENTIFIER",
            "MISSING_IMPORT",
            "UNSOLVED_GOALS",
            "TYPE_MISMATCH",
            "APPLICATION_TYPE_MISMATCH",
            "FAILED_TO_SYNTHESIZE",
        }
    )

    def __init__(self, runner: LeanRunner, max_attempts: int = 3) -> None:
        self.runner = runner
        self.max_attempts = min(max(max_attempts, 0), 3)

    def verify_and_repair(self, source: str) -> RepairResult:
        current: str = source
        attempts: list[RepairAttempt] = []
        run = self.runner.verify_code(current)
        used = self._last_tactic(current)
        diagnostic_codes = {item.code for item in run.diagnostics}
        candidates: list[str] = []
        if (
            diagnostic_codes & {"MISSING_IMPORT", "UNKNOWN_IDENTIFIER"}
            and "import Mathlib" not in current
        ):
            candidates.append("__add_mathlib_import__")
        candidates.extend(item for item in self.TACTICS if item != used)
        candidates = candidates[: self.max_attempts]
        for attempt_number, candidate in enumerate(candidates, start=1):
            if run.success or not self._is_repairable(run):
                break
            if candidate == "__add_mathlib_import__":
                updated = f"import Mathlib\n\n{current.lstrip()}"
                summary = "添加锁定 Mathlib 的显式 import"
            else:
                updated = self._replace_last_tactic(current, candidate)
                summary = f"将末行 tactic {used!r} 替换为 {candidate!r}"
            before_hash = statement_source_fingerprint(current)
            after_hash = statement_source_fingerprint(updated)
            category = run.diagnostics[0].code or "UNKNOWN"
            try:
                ensure_statement_unchanged(current, updated)
            except StatementChanged as error:
                run = LeanRunResult(
                    success=False,
                    exit_code=None,
                    diagnostics=[
                        LeanDiagnostic(
                            severity="error",
                            code="STATEMENT_CHANGED",
                            message=str(error),
                        )
                    ],
                )
                attempts.append(
                    RepairAttempt(
                        attempt=attempt_number,
                        diagnostic_category=category,
                        before_code=current,
                        diagnostics=[item.model_dump() for item in run.diagnostics],
                        change_summary=summary,
                        after_code=updated,
                        statement_hash_before=before_hash,
                        statement_hash_after=after_hash,
                        verified=False,
                    )
                )
                break
            next_run = self.runner.verify_code(updated)
            attempts.append(
                RepairAttempt(
                    attempt=attempt_number,
                    diagnostic_category=category,
                    before_code=current,
                    diagnostics=[item.model_dump() for item in run.diagnostics],
                    change_summary=summary,
                    after_code=updated,
                    statement_hash_before=before_hash,
                    statement_hash_after=after_hash,
                    verified=next_run.success,
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
