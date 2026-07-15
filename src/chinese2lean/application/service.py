from typing import cast

from chinese2lean.application.models import (
    ConversionResponseStatus,
    ConvertResponse,
    HealthResponse,
    ProductVersion,
    VerifyResponse,
)
from chinese2lean.application.ports import ConverterPort, VerifierPort, VersionProvider


class Chinese2LeanService:
    """Shared application facade for desktop and web delivery adapters."""

    def __init__(
        self,
        converter: ConverterPort,
        verifier: VerifierPort,
        version_provider: VersionProvider,
    ) -> None:
        self._converter = converter
        self._verifier = verifier
        self._version_provider = version_provider

    def health(self) -> HealthResponse:
        return HealthResponse(version=self.version().core_version)

    def convert(self, text: str, *, verify: bool = True) -> ConvertResponse:
        result = self._converter.convert_text(text, verify=verify)
        lean = result.lean_code
        status = cast(ConversionResponseStatus, result.status.value.upper())
        return ConvertResponse(
            status=status,
            lean=lean,
            lean_code=lean,
            success=result.success,
            verified=result.verified,
            ir=result.ir.model_dump(mode="json"),
            diagnostics=[item.model_dump(mode="json") for item in result.diagnostics],
            source_text=result.source_text,
            normalized_text=result.normalized_text,
            warnings=[item.model_dump(mode="json") for item in result.warnings],
            terminology_mappings=result.terminology_mappings,
            name_mappings=result.name_mappings,
            repair_attempts=result.repair_attempts,
            versions=result.versions,
            lean_line_mappings=[item.model_dump(mode="json") for item in result.lean_line_mappings],
            statement_hash=result.statement_hash,
            selected_strategy=(
                result.selected_strategy.model_dump(mode="json")
                if result.selected_strategy is not None
                else None
            ),
        )

    def verify(self, lean_code: str) -> VerifyResponse:
        result = self._verifier.verify_code(lean_code)
        verified = result.success and result.locked_environment
        return VerifyResponse(
            status="VERIFIED" if verified else "VERIFICATION_FAILED",
            verified=verified,
            success=result.success,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            diagnostics=[item.model_dump(mode="json") for item in result.diagnostics],
            duration_ms=result.duration_ms,
            command=result.command,
            locked_environment=result.locked_environment,
        )

    def version(self) -> ProductVersion:
        return ProductVersion.model_validate(self._version_provider.get_versions())
