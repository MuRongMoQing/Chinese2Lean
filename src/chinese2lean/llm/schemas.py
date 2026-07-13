from pydantic import BaseModel, Field


class LeanCandidate(BaseModel):
    code: str
    rationale: str
    assumptions_added: list[str] = Field(default_factory=list)
