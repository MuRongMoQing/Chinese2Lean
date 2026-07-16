from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HistoryResponse(BaseModel):
    """Public, JSON-safe representation of one conversion history record."""

    id: int
    input_text: str
    created_at: datetime
    status: str
    output: dict[str, Any]
    versions: dict[str, str]


class UploadResponse(BaseModel):
    """Metadata and decoded text for a safely persisted upload."""

    id: str
    filename: str
    text: str
    size: int
