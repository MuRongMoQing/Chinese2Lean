from pathlib import Path

import pytest

from chinese2lean.verification.diagnostics import parse_diagnostics
from chinese2lean.verification.runner import ForbiddenLeanConstruct, LeanRunner


def test_diagnostics_parse_location_severity_and_message() -> None:
    stderr = (
        "Generated.lean:4:3: error: unknown tactic\nGenerated.lean:1:1: warning: unused variable"
    )
    diagnostics = parse_diagnostics(stderr)
    assert diagnostics[0].model_dump() == {
        "severity": "error",
        "file": "Generated.lean",
        "line": 4,
        "column": 3,
        "code": "UNKNOWN_TACTIC",
        "message": "unknown tactic",
        "raw_message": "unknown tactic",
    }
    assert diagnostics[1].severity == "warning"


@pytest.mark.parametrize("keyword", ["sorry", "admit", "axiom bad : False", "unsafe def x := 1"])
def test_runner_rejects_proof_escape_constructs(keyword: str, tmp_path: Path) -> None:
    runner = LeanRunner(workspace=tmp_path)
    with pytest.raises(ForbiddenLeanConstruct):
        runner.verify_code(f"import Mathlib\ntheorem bad : True := by\n  {keyword}\n")


def test_comments_do_not_trigger_forbidden_scan(tmp_path: Path) -> None:
    LeanRunner(workspace=tmp_path).validate_source(
        "-- sorry is forbidden\ntheorem ok : True := by\n  trivial\n"
    )
