from chinese2lean.application import Chinese2LeanService
from chinese2lean.ir.models import Expr, TheoremIR, WarningItem
from chinese2lean.pipeline.result import ConversionResult, ConversionStatus
from chinese2lean.verification.diagnostics import LeanDiagnostic
from chinese2lean.verification.runner import LeanRunResult


class FakeConverter:
    def convert_text(self, source: str, *, verify: bool = False) -> ConversionResult:
        assert source == "任意实数 x，x = x。"
        assert verify is True
        ir = TheoremIR(
            theorem_name="identity",
            variables=[],
            assumptions=[],
            conclusion=Expr(kind="relation", operator="=", args=[]),
            name_mappings={"恒等式": "identity"},
        )
        return ConversionResult(
            status=ConversionStatus.VERIFIED,
            source_text=source,
            normalized_text="对任意实数 x, x = x.",
            lean_code="theorem identity : True := by trivial\n",
            verified=True,
            ir=ir,
            diagnostics=[LeanDiagnostic(severity="info", code="LEAN_OK", message="verified")],
            warnings=[WarningItem(code="TRACE_NOTE", message="kept")],
            terminology_mappings=[{"original": "任意", "normalized": "对任意"}],
            name_mappings={"恒等式": "identity"},
            repair_attempts=[{"attempt": 1, "change_summary": "none"}],
            versions={"generator_version": "0.1.0"},
            statement_hash="sha256:abc",
        )


class FakeVerifier:
    def verify_code(self, source: str) -> LeanRunResult:
        assert source == "theorem identity : True := by trivial\n"
        return LeanRunResult(
            success=True,
            exit_code=0,
            stdout="",
            diagnostics=[],
            duration_ms=12.5,
            command=["pinned-lake", "env", "lean", "Generated.lean"],
            locked_environment=True,
        )


class FakeVersionProvider:
    def get_versions(self) -> dict[str, str]:
        return {
            "chinese2lean_version": "0.1.0",
            "core_version": "0.1.0",
            "desktop_version": "0.1.0",
            "web_version": "0.1.0",
            "lean_version": "4.19.0",
            "mathlib_revision": "c44e0c8",
            "dictionary_version": "0.1.0",
            "ir_schema_version": "1",
        }


def test_health_reports_the_shared_core_version() -> None:
    service = Chinese2LeanService(FakeConverter(), FakeVerifier(), FakeVersionProvider())

    assert service.health().model_dump() == {"status": "ok", "version": "0.1.0"}


def test_convert_adapts_core_result_without_losing_traceability() -> None:
    service = Chinese2LeanService(FakeConverter(), FakeVerifier(), FakeVersionProvider())

    response = service.convert("任意实数 x，x = x。", verify=True)

    assert response.status == "VERIFIED"
    assert response.success is True
    assert response.lean == "theorem identity : True := by trivial\n"
    assert response.lean_code == response.lean
    assert response.ir["theorem_name"] == "identity"
    assert response.diagnostics == [
        {
            "severity": "info",
            "file": None,
            "line": None,
            "column": None,
            "code": "LEAN_OK",
            "message": "verified",
            "raw_message": None,
        }
    ]
    assert response.source_text == "任意实数 x，x = x。"
    assert response.normalized_text == "对任意实数 x, x = x."
    assert response.terminology_mappings == [{"original": "任意", "normalized": "对任意"}]
    assert response.name_mappings == {"恒等式": "identity"}
    assert response.statement_hash == "sha256:abc"


def test_verify_reports_pinned_kernel_success_with_run_metadata() -> None:
    service = Chinese2LeanService(FakeConverter(), FakeVerifier(), FakeVersionProvider())

    response = service.verify("theorem identity : True := by trivial\n")

    assert response.status == "VERIFIED"
    assert response.verified is True
    assert response.success is True
    assert response.exit_code == 0
    assert response.locked_environment is True
    assert response.command[0] == "pinned-lake"
