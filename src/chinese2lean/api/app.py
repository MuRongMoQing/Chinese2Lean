from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from chinese2lean.api.schemas import TextRequest, VerifyRequest
from chinese2lean.normalization.terminology import Terminology
from chinese2lean.pipeline.converter import Converter
from chinese2lean.verification.runner import ForbiddenLeanConstruct, LeanRunner

PROJECT_ROOT = Path(__file__).resolve().parents[3]
app = FastAPI(title="Chinese2Lean", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse")
def parse(request: TextRequest) -> dict[str, object]:
    result = Converter.default(PROJECT_ROOT).convert_text(request.text, verify=False)
    return {
        "success": result.success,
        "status": result.status.value,
        "ir": result.ir.model_dump(),
        "warnings": [item.model_dump() for item in result.warnings],
    }


@app.post("/convert")
def convert(request: TextRequest) -> dict[str, object]:
    result = Converter.default(PROJECT_ROOT).convert_text(request.text, verify=request.verify)
    return {
        "success": result.success,
        "status": result.status.value,
        "lean_code": result.lean_code,
        "verified": result.verified,
        "ir": result.ir.model_dump(),
        "diagnostics": result.diagnostics,
        "warnings": [item.model_dump() for item in result.warnings],
        "terminology_mappings": result.terminology_mappings,
    }


@app.post("/verify")
def verify(request: VerifyRequest) -> dict[str, object]:
    try:
        result = LeanRunner(PROJECT_ROOT / "lean_workspace").verify_code(request.lean_code)
    except ForbiddenLeanConstruct as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return result.model_dump()


@app.get("/terminology/search")
def search_terminology(
    q: str = Query(min_length=1, max_length=100),
) -> list[dict[str, object]]:
    entries = Terminology.load(PROJECT_ROOT / "terminology").lookup(q)
    return [item.model_dump() for item in entries]
