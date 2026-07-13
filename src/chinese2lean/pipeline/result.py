from enum import StrEnum

from pydantic import BaseModel, Field

from chinese2lean.ir.models import TheoremIR, WarningItem


class ConversionStatus(StrEnum):
    PARSE_FAILED = "parse_failed"
    AMBIGUOUS = "ambiguous"
    GENERATED = "generated"
    VERIFICATION_FAILED = "verification_failed"
    VERIFIED = "verified"


class ConversionResult(BaseModel):
    status: ConversionStatus
    lean_code: str = ""
    verified: bool = False
    ir: TheoremIR
    diagnostics: list[dict[str, object]] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    terminology_mappings: list[dict[str, object]] = Field(default_factory=list)
    repair_history: list[dict[str, object]] = Field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status in {ConversionStatus.GENERATED, ConversionStatus.VERIFIED}
