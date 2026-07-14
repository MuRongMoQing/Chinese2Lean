from dataclasses import asdict
from pathlib import Path

from chinese2lean.ir.models import TheoremIR
from chinese2lean.lean.proof_renderer import choose_strategy
from chinese2lean.lean.renderer import LeanRenderer
from chinese2lean.normalization.normalizer import NormalizationResult, Normalizer
from chinese2lean.normalization.terminology import Terminology
from chinese2lean.parser.statement_parser import StatementParser
from chinese2lean.pipeline.result import (
    ConversionResult,
    ConversionStatus,
    LeanLineMapping,
)
from chinese2lean.verification.diagnostics import LeanDiagnostic
from chinese2lean.verification.invariance import (
    StatementChanged,
    ensure_statement_unchanged,
    statement_source_fingerprint,
)
from chinese2lean.verification.repair import DeterministicRepairer
from chinese2lean.verification.runner import ForbiddenLeanConstruct, LeanRunner
from chinese2lean.versioning import read_versions


class Converter:
    def __init__(
        self,
        normalizer: Normalizer,
        parser: StatementParser,
        renderer: LeanRenderer,
        runner: LeanRunner | None = None,
        *,
        project_root: Path | None = None,
    ) -> None:
        self.normalizer = normalizer
        self.parser = parser
        self.renderer = renderer
        self.runner = runner
        self.project_root = (project_root or Path.cwd()).resolve()

    @classmethod
    def default(cls, root: Path | None = None) -> "Converter":
        project_root = (root or Path.cwd()).resolve()
        terminology = Terminology.load(project_root / "terminology")
        return cls(
            Normalizer(terminology),
            StatementParser(),
            LeanRenderer(),
            LeanRunner(project_root),
            project_root=project_root,
        )

    @staticmethod
    def _lean_line_mappings(ir: TheoremIR) -> list[LeanLineMapping]:
        declaration_line = len(ir.imports) + 2
        mappings: list[LeanLineMapping] = []
        for variable in ir.variables:
            span = variable.source_span
            mappings.append(
                LeanLineMapping(
                    source_kind="variable",
                    source_name=variable.source_name,
                    source_text=span.text if span else None,
                    source_start=span.start if span else None,
                    source_end=span.end if span else None,
                    lean_line=declaration_line,
                )
            )
        for assumption in ir.assumptions:
            span = assumption.source_span or assumption.proposition.source_span
            mappings.append(
                LeanLineMapping(
                    source_kind="assumption",
                    source_name=assumption.name,
                    source_text=span.text if span else None,
                    source_start=span.start if span else None,
                    source_end=span.end if span else None,
                    lean_line=declaration_line,
                )
            )
        span = ir.conclusion.source_span
        mappings.append(
            LeanLineMapping(
                source_kind="conclusion",
                source_name="conclusion",
                source_text=span.text if span else None,
                source_start=span.start if span else None,
                source_end=span.end if span else None,
                lean_line=declaration_line,
            )
        )
        proof_line = declaration_line + 1
        for step in ir.proof_steps:
            span = step.source_span
            mappings.append(
                LeanLineMapping(
                    source_kind="proof_step",
                    source_name=step.step_id,
                    source_text=span.text if span else step.source_text,
                    source_start=span.start if span else None,
                    source_end=span.end if span else None,
                    lean_line=proof_line,
                )
            )
        return mappings

    def _result(
        self,
        status: ConversionStatus,
        source: str,
        normalized: NormalizationResult,
        ir: TheoremIR,
    ) -> ConversionResult:
        return ConversionResult(
            status=status,
            source_text=source,
            normalized_text=normalized.normalized_text,
            ir=ir,
            warnings=ir.warnings,
            terminology_mappings=[asdict(item) for item in normalized.mappings],
            name_mappings=ir.name_mappings,
            versions=read_versions(
                self.project_root,
                dictionary_version=self.normalizer.terminology.version,
                ir_schema_version=ir.schema_version,
            ),
        )

    def convert_text(self, source: str, *, verify: bool = False) -> ConversionResult:
        normalized = self.normalizer.normalize(source)
        ir = self.parser.parse(normalized.text)
        fatal_codes = {
            "UNDECLARED_VARIABLE",
            "MISSING_CONCLUSION",
            "INVALID_CONCLUSION",
            "INVALID_ASSUMPTION",
            "INVALID_VARIABLE_DECLARATION",
            "UNSUPPORTED_SYNTAX",
        }
        ir_invalid_codes = {"CONFLICTING_VARIABLE_TYPES", "INVALID_LEAN_NAME"}
        if any(item.code in ir_invalid_codes for item in ir.warnings):
            return self._result(ConversionStatus.IR_INVALID, source, normalized, ir)
        if any(item.code in fatal_codes for item in ir.warnings):
            return self._result(ConversionStatus.PARSE_FAILED, source, normalized, ir)
        if ir.ambiguities:
            return self._result(ConversionStatus.AMBIGUOUS, source, normalized, ir)

        lean_code = self.renderer.render(ir)
        result = self._result(ConversionStatus.GENERATED, source, normalized, ir)
        result.lean_code = lean_code
        result.lean_line_mappings = self._lean_line_mappings(ir)
        result.selected_strategy = choose_strategy(ir)
        result.statement_hash = statement_source_fingerprint(lean_code)
        if not verify or self.runner is None:
            return result

        try:
            repaired = DeterministicRepairer(self.runner).verify_and_repair(lean_code)
        except ForbiddenLeanConstruct as error:
            result.status = ConversionStatus.VERIFICATION_FAILED
            result.diagnostics = [
                LeanDiagnostic(
                    severity="error",
                    code="FORBIDDEN_CONSTRUCT",
                    message=str(error),
                )
            ]
            return result

        result.lean_code = repaired.code
        result.diagnostics = list(repaired.run.diagnostics)
        result.repair_attempts = [item.model_dump() for item in repaired.attempts]
        if result.selected_strategy is not None:
            result.selected_strategy.alternatives_tried = [
                item.change_summary for item in repaired.attempts
            ]
        statement_unchanged = True
        try:
            ensure_statement_unchanged(lean_code, repaired.code)
        except StatementChanged as error:
            statement_unchanged = False
            result.diagnostics.append(
                LeanDiagnostic(
                    severity="error",
                    code="STATEMENT_CHANGED",
                    message=str(error),
                )
            )
        if repaired.run.success and not repaired.run.locked_environment:
            result.diagnostics.append(
                LeanDiagnostic(
                    severity="error",
                    code="UNLOCKED_ENVIRONMENT",
                    message="Lean 编译成功，但未使用 lean-toolchain 锁定的本地工具链。",
                )
            )
        result.verified = (
            repaired.run.success and repaired.run.locked_environment and statement_unchanged
        )
        result.status = (
            ConversionStatus.VERIFIED if result.verified else ConversionStatus.VERIFICATION_FAILED
        )
        return result
