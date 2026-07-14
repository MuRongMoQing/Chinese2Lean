from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from chinese2lean.ir.models import TheoremIR, WarningItem
from chinese2lean.lean.proof_renderer import ProofStrategy
from chinese2lean.verification.diagnostics import LeanDiagnostic


class ConversionStatus(StrEnum):
    NORMALIZATION_FAILED = "normalization_failed"
    PARSE_FAILED = "parse_failed"
    AMBIGUOUS = "ambiguous"
    IR_INVALID = "ir_invalid"
    GENERATED = "generated"
    VERIFICATION_FAILED = "verification_failed"
    VERIFIED = "verified"


class LeanLineMapping(BaseModel):
    """Map a source IR component to its generated Lean line."""

    source_kind: Literal["variable", "assumption", "conclusion", "proof_step"]
    source_name: str
    source_text: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    lean_line: int


class ConversionResult(BaseModel):
    status: ConversionStatus
    source_text: str = ""
    normalized_text: str = ""
    lean_code: str = ""
    verified: bool = False
    ir: TheoremIR
    diagnostics: list[LeanDiagnostic] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    terminology_mappings: list[dict[str, object]] = Field(default_factory=list)
    name_mappings: dict[str, str] = Field(default_factory=dict)
    repair_attempts: list[dict[str, object]] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)
    lean_line_mappings: list[LeanLineMapping] = Field(default_factory=list)
    statement_hash: str = ""
    selected_strategy: ProofStrategy | None = None

    @property
    def success(self) -> bool:
        return self.status is ConversionStatus.VERIFIED
