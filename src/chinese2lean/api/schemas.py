from pydantic import BaseModel, Field


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1_000_000)
    verify: bool = True


class VerifyRequest(BaseModel):
    lean_code: str = Field(min_length=1, max_length=1_000_000)
