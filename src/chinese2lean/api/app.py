from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from chinese2lean.api.schemas import TextRequest, VerifyRequest
from chinese2lean.application.composition import ProductRuntime, build_product_runtime
from chinese2lean.application.models import (
    ConvertResponse,
    HealthResponse,
    ProductVersion,
    VerifyResponse,
)
from chinese2lean.normalization.terminology import Terminology
from chinese2lean.verification.runner import ForbiddenLeanConstruct

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def create_app(
    runtime: ProductRuntime | None = None,
    *,
    project_root: Path = PROJECT_ROOT,
) -> FastAPI:
    """Create the HTTP adapter around the shared product runtime."""

    api = FastAPI(title="Chinese2Lean", version="0.1.0")
    active_runtime = runtime
    root = project_root.resolve()

    def current_runtime() -> ProductRuntime:
        nonlocal active_runtime
        if active_runtime is None:
            active_runtime = build_product_runtime(root)
        return active_runtime

    @api.get("/api/health")
    def product_health() -> HealthResponse:
        return current_runtime().service.health()

    @api.get("/api/version")
    def product_version() -> ProductVersion:
        return current_runtime().service.version()

    @api.post("/api/convert")
    def product_convert(request: TextRequest) -> ConvertResponse:
        product = current_runtime()
        response = product.service.convert(request.text, verify=request.verify)
        product.history.save(
            input_text=request.text,
            status=response.status,
            output=response.model_dump(mode="json"),
            versions=response.versions,
        )
        product.loggers["api"].info("convert status=%s", response.status)
        if request.verify:
            product.loggers["lean"].info("convert verification status=%s", response.status)
        return response

    def run_verify(request: VerifyRequest) -> VerifyResponse:
        product = current_runtime()
        try:
            response = product.service.verify(request.lean_code)
        except (ForbiddenLeanConstruct, ValueError) as error:
            product.loggers["lean"].warning("verify rejected: %s", error)
            product.loggers["error"].warning("verify rejected: %s", error)
            raise HTTPException(status_code=422, detail=str(error)) from error
        product.loggers["lean"].info("verify status=%s", response.status)
        product.loggers["api"].info("verify status=%s", response.status)
        return response

    @api.post("/api/verify")
    def product_verify(request: VerifyRequest) -> VerifyResponse:
        return run_verify(request)

    # Phase-one compatibility routes delegate to the same shared service.
    @api.get("/health", include_in_schema=False)
    def legacy_health() -> dict[str, str]:
        current_runtime().service.health()
        return {"status": "ok"}

    @api.post("/parse", include_in_schema=False)
    def legacy_parse(request: TextRequest) -> dict[str, object]:
        response = current_runtime().service.convert(request.text, verify=False)
        return {
            "success": response.success,
            "status": response.status.lower(),
            "ir": response.ir,
            "warnings": response.warnings,
        }

    @api.post("/convert", include_in_schema=False)
    def legacy_convert(request: TextRequest) -> dict[str, object]:
        response = current_runtime().service.convert(request.text, verify=request.verify)
        return {
            "success": response.success,
            "status": response.status.lower(),
            "lean_code": response.lean_code,
            "verified": response.verified,
            "ir": response.ir,
            "diagnostics": response.diagnostics,
            "warnings": response.warnings,
            "terminology_mappings": response.terminology_mappings,
        }

    @api.post("/verify", include_in_schema=False)
    def legacy_verify(request: VerifyRequest) -> dict[str, object]:
        return run_verify(request).model_dump(mode="json")

    @api.get("/terminology/search", include_in_schema=False)
    def search_terminology(
        q: str = Query(min_length=1, max_length=100),
    ) -> list[dict[str, object]]:
        entries = Terminology.load(root / "terminology").lookup(q)
        return [item.model_dump(mode="json") for item in entries]

    return api


app = create_app()
