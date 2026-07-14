from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceSpan(BaseModel):
    sentence_index: int | None = None
    start: int | None = None
    end: int | None = None
    text: str | None = None


class VariableDecl(BaseModel):
    source_name: str
    lean_name: str
    type_name: str
    binder_kind: Literal["explicit", "implicit"] = "explicit"
    source_span: SourceSpan | None = None


class Expr(BaseModel):
    kind: str
    operator: str | None = None
    value: str | int | float | None = None
    args: list[Expr] = Field(default_factory=list)
    inferred_type: str | None = None
    binder_type: str | None = None
    source_span: SourceSpan | None = None


class Assumption(BaseModel):
    name: str
    proposition: Expr
    source_span: SourceSpan | None = None


class ProofStep(BaseModel):
    step_id: str
    source_text: str
    action: str
    premises: list[str] = Field(default_factory=list)
    result: Expr | None = None
    suggested_tactic: str | None = None
    source_span: SourceSpan | None = None


class WarningItem(BaseModel):
    code: str
    message: str
    location: SourceSpan | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TheoremIR(BaseModel):
    schema_version: Literal[1] = 1
    theorem_name: str
    variables: list[VariableDecl]
    assumptions: list[Assumption]
    conclusion: Expr
    proof_steps: list[ProofStep] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=lambda: ["Mathlib"])
    warnings: list[WarningItem] = Field(default_factory=list)
    ambiguities: list[WarningItem] = Field(default_factory=list)
    name_mappings: dict[str, str] = Field(default_factory=dict)


Expr.model_rebuild()
