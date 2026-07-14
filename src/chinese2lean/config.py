from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    terminology_dir: Path = Field(default_factory=lambda: Path("terminology"))
    lean_workspace: Path = Field(default_factory=lambda: Path("lean_workspace"))
    lean_timeout_seconds: float = Field(default=60.0, gt=0, le=120)
    max_input_bytes: int = Field(default=1_000_000, gt=0)
    max_repair_attempts: int = Field(default=3, ge=0, le=3)
