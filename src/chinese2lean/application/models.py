from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ConversionResponseStatus = Literal[
    "NORMALIZATION_FAILED",
    "PARSE_FAILED",
    "AMBIGUOUS",
    "IR_INVALID",
    "GENERATED",
    "VERIFICATION_FAILED",
    "VERIFIED",
]
VerificationResponseStatus = Literal["VERIFICATION_FAILED", "VERIFIED"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class ProductVersion(BaseModel):
    chinese2lean_version: str
    core_version: str
    desktop_version: str
    web_version: str
    lean_version: str
    mathlib_revision: str
    dictionary_version: str
    ir_schema_version: str


class ConvertResponse(BaseModel):
    status: ConversionResponseStatus
    lean: str
    ir: dict[str, Any]
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    success: bool = False
    lean_code: str = ""
    verified: bool = False
    source_text: str = ""
    normalized_text: str = ""
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    terminology_mappings: list[dict[str, Any]] = Field(default_factory=list)
    name_mappings: dict[str, str] = Field(default_factory=dict)
    repair_attempts: list[dict[str, Any]] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)
    lean_line_mappings: list[dict[str, Any]] = Field(default_factory=list)
    statement_hash: str = ""
    selected_strategy: dict[str, Any] | None = None


class VerifyResponse(BaseModel):
    status: VerificationResponseStatus
    verified: bool
    success: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: float = 0.0
    command: list[str] = Field(default_factory=list)
    locked_environment: bool = False
