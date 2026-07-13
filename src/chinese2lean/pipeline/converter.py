from pathlib import Path

from chinese2lean.lean.renderer import LeanRenderer
from chinese2lean.normalization.normalizer import Normalizer
from chinese2lean.normalization.terminology import Terminology
from chinese2lean.parser.statement_parser import StatementParser
from chinese2lean.pipeline.result import ConversionResult, ConversionStatus
from chinese2lean.verification.repair import DeterministicRepairer
from chinese2lean.verification.runner import ForbiddenLeanConstruct, LeanRunner


class Converter:
    def __init__(
        self,
        normalizer: Normalizer,
        parser: StatementParser,
        renderer: LeanRenderer,
        runner: LeanRunner | None = None,
    ) -> None:
        self.normalizer = normalizer
        self.parser = parser
        self.renderer = renderer
        self.runner = runner

    @classmethod
    def default(cls, root: Path | None = None) -> "Converter":
        project_root = (root or Path.cwd()).resolve()
        terminology = Terminology.load(project_root / "terminology")
        return cls(
            Normalizer(terminology),
            StatementParser(),
            LeanRenderer(),
            LeanRunner(project_root / "lean_workspace"),
        )

    def convert_text(self, source: str, *, verify: bool = False) -> ConversionResult:
        normalized = self.normalizer.normalize(source)
        ir = self.parser.parse(normalized.text)
        fatal_codes = {
            "UNDECLARED_VARIABLE",
            "MISSING_CONCLUSION",
            "INVALID_CONCLUSION",
            "INVALID_VARIABLE_DECLARATION",
            "UNSUPPORTED_SYNTAX",
        }
        mappings = [item.__dict__ for item in normalized.mappings]
        if any(item.code in fatal_codes for item in ir.warnings):
            return ConversionResult(
                status=ConversionStatus.PARSE_FAILED,
                ir=ir,
                warnings=ir.warnings,
                terminology_mappings=mappings,
            )
        if ir.ambiguities:
            return ConversionResult(
                status=ConversionStatus.AMBIGUOUS,
                ir=ir,
                warnings=ir.warnings,
                terminology_mappings=mappings,
            )
        lean_code = self.renderer.render(ir)
        result = ConversionResult(
            status=ConversionStatus.GENERATED,
            lean_code=lean_code,
            ir=ir,
            warnings=ir.warnings,
            terminology_mappings=mappings,
        )
        if not verify or self.runner is None:
            return result
        try:
            repaired = DeterministicRepairer(self.runner).verify_and_repair(lean_code)
        except ForbiddenLeanConstruct as error:
            result.status = ConversionStatus.VERIFICATION_FAILED
            result.diagnostics = [
                {
                    "severity": "error",
                    "code": "FORBIDDEN_CONSTRUCT",
                    "message": str(error),
                }
            ]
            return result
        result.lean_code = repaired.code
        result.verified = repaired.run.success
        result.status = (
            ConversionStatus.VERIFIED
            if repaired.run.success
            else ConversionStatus.VERIFICATION_FAILED
        )
        result.diagnostics = [item.model_dump() for item in repaired.run.diagnostics]
        result.repair_history = [item.model_dump() for item in repaired.attempts]
        return result
