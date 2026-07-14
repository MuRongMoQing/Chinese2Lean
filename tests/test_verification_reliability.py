from pathlib import Path

import pytest

from chinese2lean.verification.diagnostics import parse_diagnostics
from chinese2lean.verification.invariance import (
    StatementChanged,
    ensure_statement_unchanged,
    statement_source_fingerprint,
)
from chinese2lean.verification.runner import ForbiddenLeanConstruct, LeanRunner

ROOT = Path(__file__).parents[1]


def test_forbidden_scanner_is_token_aware() -> None:
    runner = LeanRunner(ROOT)
    runner.validate_source(
        "-- sorry in a comment\n"
        'def sorryName : String := "sorry"\n'
        "/- axiom unsafe admit -/\n"
        "theorem ok : True := by\n  trivial\n"
    )
    for forbidden in (
        "theorem bad : True := by\n  sorry",
        "theorem bad : True := by\n  admit",
        "axiom bad : False",
        "unsafe def bad := 1",
    ):
        with pytest.raises(ForbiddenLeanConstruct):
            runner.validate_source(forbidden)


def test_statement_fingerprint_allows_proof_changes_but_not_statement_changes() -> None:
    original = "import Mathlib\n\ntheorem t (x : ℝ) : x = x := by\n  rfl\n"
    proof_change = "import Mathlib\n\ntheorem t (x : ℝ) : x = x := by\n  simp\n"
    statement_change = "import Mathlib\n\ntheorem t (x : ℝ) : x + 0 = x := by\n  simp\n"
    assert statement_source_fingerprint(original) == statement_source_fingerprint(proof_change)
    ensure_statement_unchanged(original, proof_change)
    with pytest.raises(StatementChanged):
        ensure_statement_unchanged(original, statement_change)


def test_diagnostics_keep_raw_message_and_normalize_categories() -> None:
    output = (
        "Generated.lean:4:3: error: application type mismatch\n"
        "Generated.lean:7:2: error: failed to synthesize instance"
    )
    diagnostics = parse_diagnostics(output)
    assert diagnostics[0].code == "APPLICATION_TYPE_MISMATCH"
    assert diagnostics[0].raw_message == "application type mismatch"
    assert diagnostics[1].code == "FAILED_TO_SYNTHESIZE"


def test_runner_uses_locked_lake_environment_for_real_compilation() -> None:
    result = LeanRunner(ROOT, timeout_seconds=60).verify_code(
        "import Mathlib\n\ntheorem locked_environment_smoke : (2 : ℕ) + 3 = 5 := by\n  norm_num\n"
    )
    assert result.success, result.stderr
    assert result.exit_code == 0
    assert result.locked_environment
    assert result.command[-3:-1] == ["env", "lean"]
    assert result.duration_ms > 0


def test_repair_attempts_are_bounded_audited_and_statement_preserving() -> None:
    from chinese2lean.verification.diagnostics import LeanDiagnostic
    from chinese2lean.verification.repair import DeterministicRepairer
    from chinese2lean.verification.runner import LeanRunResult

    class SequenceRunner:
        def __init__(self) -> None:
            self.calls = 0

        def verify_code(self, source: str) -> LeanRunResult:
            self.calls += 1
            if self.calls == 1:
                return LeanRunResult(
                    success=False,
                    exit_code=1,
                    diagnostics=[
                        LeanDiagnostic(
                            severity="error",
                            code="UNKNOWN_TACTIC",
                            message="unknown tactic",
                        )
                    ],
                )
            return LeanRunResult(success=True, exit_code=0)

    source = "import Mathlib\n\ntheorem repair_audit (x : ℝ) : x = x := by\n  bad_tactic\n"
    runner = SequenceRunner()
    repaired = DeterministicRepairer(runner, max_attempts=99).verify_and_repair(source)  # type: ignore[arg-type]
    assert repaired.run.success
    assert len(repaired.attempts) == 1
    attempt = repaired.attempts[0]
    assert attempt.attempt == 1
    assert attempt.diagnostic_category == "UNKNOWN_TACTIC"
    assert attempt.statement_hash_before == attempt.statement_hash_after
    assert attempt.verified


def test_timeout_returns_structured_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["lake", "env", "lean"], timeout=0.01)

    monkeypatch.setattr(subprocess, "run", timeout)
    result = LeanRunner(ROOT, timeout_seconds=0.01).verify_code(
        "theorem timeout_case : True := by\n  trivial\n"
    )
    assert result.timed_out
    assert not result.success
    assert result.diagnostics[0].code == "TIMEOUT"
    assert result.command[-3:-1] == ["env", "lean"]


def test_successful_system_lake_fallback_is_not_a_verified_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    completed = subprocess.CompletedProcess(
        args=["lake", "env", "lean"],
        returncode=0,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)
    monkeypatch.setattr(
        LeanRunner,
        "_locked_lake",
        staticmethod(lambda lake_root: ("lake", False)),
    )
    result = LeanRunner(ROOT).verify_code("theorem unlocked : True := by\n  trivial\n")
    assert not result.success
    assert not result.locked_environment
    assert result.exit_code == 0
    assert {item.code for item in result.diagnostics} == {"UNLOCKED_ENVIRONMENT"}


def test_repair_can_add_a_missing_mathlib_import() -> None:
    from chinese2lean.verification.diagnostics import LeanDiagnostic
    from chinese2lean.verification.repair import DeterministicRepairer
    from chinese2lean.verification.runner import LeanRunResult

    class SequenceRunner:
        def __init__(self) -> None:
            self.calls = 0

        def verify_code(self, source: str) -> LeanRunResult:
            self.calls += 1
            if self.calls == 1:
                return LeanRunResult(
                    success=False,
                    exit_code=1,
                    diagnostics=[
                        LeanDiagnostic(
                            severity="error",
                            code="UNKNOWN_IDENTIFIER",
                            message="unknown identifier Real",
                        )
                    ],
                )
            return LeanRunResult(success=True, exit_code=0, locked_environment=True)

    source = "theorem import_repair (x : ℝ) : x = x := by\n  rfl\n"
    repaired = DeterministicRepairer(SequenceRunner()).verify_and_repair(source)  # type: ignore[arg-type]
    assert repaired.code.startswith("import Mathlib\n\n")
    attempt = repaired.attempts[0]
    assert attempt.diagnostic_category == "UNKNOWN_IDENTIFIER"
    assert attempt.change_summary == "添加锁定 Mathlib 的显式 import"
    assert attempt.statement_hash_before == attempt.statement_hash_after
