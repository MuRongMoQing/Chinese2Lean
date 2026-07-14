from pathlib import Path

from chinese2lean.verification.batch import verify_all
from chinese2lean.verification.runner import LeanRunResult


def test_batch_verification_is_sorted_and_reports_failures(tmp_path: Path) -> None:
    (tmp_path / "b.lean").write_text("theorem b : True := by trivial", encoding="utf-8")
    (tmp_path / "a.lean").write_text("theorem a : True := by trivial", encoding="utf-8")

    class StubRunner:
        def verify_file(self, path: Path) -> LeanRunResult:
            return LeanRunResult(
                success=path.stem == "a",
                exit_code=0 if path.stem == "a" else 1,
                duration_ms=10,
                locked_environment=True,
            )

    result = verify_all(tmp_path, StubRunner())  # type: ignore[arg-type]
    assert result.model_dump()["total"] == 2
    assert result.verified == 1
    assert result.failed == 1
    assert [Path(item.path).name for item in result.files] == ["a.lean", "b.lean"]
    assert not result.success
