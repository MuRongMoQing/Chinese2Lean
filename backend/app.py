from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import unquote_to_bytes

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from backend.models import HistoryResponse, UploadResponse
from chinese2lean.api.app import create_app
from chinese2lean.application import ProductRuntime, build_product_runtime
from chinese2lean.storage import HistoryRecord

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DownloadKind = Literal["lean", "ir", "report"]
ALLOWED_UPLOAD_SUFFIXES = frozenset({".md", ".txt"})
MAX_UPLOAD_FILENAME_CHARS = 255


def _history_response(record: HistoryRecord) -> HistoryResponse:
    return HistoryResponse(
        id=record.id,
        input_text=record.input_text,
        created_at=record.created_at,
        status=record.status,
        output=record.output,
        versions=record.versions,
    )


async def _read_bounded_body(request: Request, *, max_bytes: int) -> bytes:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > max_bytes:
            raise ValueError("Upload exceeds the configured size limit")
        content.extend(chunk)
    return bytes(content)


def _decode_upload_filename(filename: str) -> str:
    try:
        decoded = unquote_to_bytes(filename).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Upload filename must be percent-encoded UTF-8") from error
    if not decoded or len(decoded) > MAX_UPLOAD_FILENAME_CHARS:
        raise ValueError("Upload filename must contain between 1 and 255 characters")
    return decoded


def _validate_upload_suffix(filename: str) -> None:
    if Path(filename).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        raise ValueError("Upload filename must use a .md or .txt extension")


def _download_content(record: HistoryRecord, kind: DownloadKind) -> tuple[str, str, str]:
    if kind == "lean":
        lean = record.output.get("lean")
        if not isinstance(lean, str):
            raise HTTPException(status_code=404, detail="Lean output is not available")
        return lean, ".lean", "text/plain"
    if kind == "ir":
        ir = record.output.get("ir")
        if not isinstance(ir, dict):
            raise HTTPException(status_code=404, detail="IR output is not available")
        return json.dumps(ir, ensure_ascii=False, indent=2) + "\n", ".ir.json", "application/json"
    return (
        json.dumps(record.output, ensure_ascii=False, indent=2) + "\n",
        ".report.json",
        "application/json",
    )


def create_backend_app(
    runtime: ProductRuntime | None = None,
    *,
    project_root: Path = PROJECT_ROOT,
) -> FastAPI:
    """Create the Web backend around the shared Chinese2Lean product runtime."""

    root = project_root.resolve()
    product = runtime if runtime is not None else build_product_runtime(root)
    api = create_app(product, project_root=root)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=[product.config.frontend.url],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Filename"],
    )

    @api.get("/api/history", response_model=list[HistoryResponse])
    def list_history() -> list[HistoryResponse]:
        records = [_history_response(record) for record in product.history.list()]
        product.loggers["api"].info("history list count=%d", len(records))
        return records

    @api.get("/api/history/{record_id}", response_model=HistoryResponse)
    def get_history(record_id: int) -> HistoryResponse:
        record = product.history.get(record_id)
        if record is None:
            product.loggers["api"].warning("history not found id=%d", record_id)
            raise HTTPException(status_code=404, detail="History record does not exist")
        product.loggers["api"].info("history detail id=%d", record_id)
        return _history_response(record)

    @api.post("/api/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
    async def upload_file(
        request: Request,
        filename: Annotated[
            str,
            Header(alias="X-Filename", min_length=1, max_length=3072),
        ],
    ) -> UploadResponse:
        try:
            filename = _decode_upload_filename(filename)
            _validate_upload_suffix(filename)
            content = await _read_bounded_body(
                request,
                max_bytes=product.history.max_upload_bytes,
            )
            upload = product.history.save_upload(filename, content)
        except ValueError as error:
            product.loggers["api"].warning("upload rejected: %s", error)
            product.loggers["error"].warning("upload rejected: %s", error)
            raise HTTPException(status_code=422, detail=str(error)) from error
        product.loggers["api"].info("upload saved id=%s size=%d", upload.id, upload.size)
        return UploadResponse(
            id=upload.id,
            filename=upload.original_name,
            text=upload.text,
            size=upload.size,
        )

    @api.get("/api/history/{record_id}/download/{kind}")
    def download_history(record_id: int, kind: DownloadKind) -> Response:
        record = product.history.get(record_id)
        if record is None:
            product.loggers["api"].warning("download history not found id=%d", record_id)
            raise HTTPException(status_code=404, detail="History record does not exist")
        content, suffix, media_type = _download_content(record, kind)
        filename = f"history-{record_id}{suffix}"
        product.loggers["api"].info("history download id=%d kind=%s", record_id, kind)
        return Response(
            content=content.encode("utf-8"),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return api
