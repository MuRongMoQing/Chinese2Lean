import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from urllib.parse import quote

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import backend.app as backend_app_module
from backend.app import _read_bounded_body, create_backend_app
from chinese2lean.application.composition import ProductRuntime, build_product_runtime

ROOT = Path(__file__).parents[1]
FRONTEND_ORIGIN = "http://127.0.0.1:5173"


def _runtime(tmp_path: Path) -> ProductRuntime:
    return build_product_runtime(
        ROOT,
        storage_root=tmp_path / "storage",
        log_root=tmp_path / "logs",
    )


def _client(tmp_path: Path) -> tuple[TestClient, ProductRuntime]:
    runtime = _runtime(tmp_path)
    return TestClient(create_backend_app(runtime)), runtime


def test_backend_preserves_core_routes_and_records_unverified_conversion(
    tmp_path: Path,
) -> None:
    client, runtime = _client(tmp_path)
    source = (ROOT / "examples" / "chinese" / "positive_add_one.md").read_text(
        encoding="utf-8"
    )

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/version").status_code == 200
    assert {
        "/api/health",
        "/api/convert",
        "/api/verify",
        "/api/version",
    } <= set(client.get("/openapi.json").json()["paths"])
    converted = client.post("/api/convert", json={"text": source, "verify": False})

    assert converted.status_code == 200
    assert converted.json()["status"] == "GENERATED"
    records = runtime.history.list()
    assert len(records) == 1
    assert records[0].input_text == source
    assert records[0].output["lean"] == converted.json()["lean"]


def test_backend_builds_the_shared_product_runtime_when_not_injected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    built_for: list[Path] = []

    def fake_build_product_runtime(project_root: Path) -> ProductRuntime:
        built_for.append(project_root)
        return runtime

    monkeypatch.setattr(
        backend_app_module,
        "build_product_runtime",
        fake_build_product_runtime,
    )

    client = TestClient(create_backend_app(project_root=ROOT))

    assert client.get("/api/health").status_code == 200
    assert built_for == [ROOT.resolve()]


def test_history_list_and_detail_expose_input_time_status_and_output(tmp_path: Path) -> None:
    client, runtime = _client(tmp_path)
    record = runtime.history.save(
        input_text="任意实数 x，x = x。",
        status="GENERATED",
        output={"lean": "theorem refl (x : Real) : x = x := by rfl", "ir": {"kind": "theorem"}},
        versions={"core_version": "0.1.0"},
    )

    listed = client.get("/api/history")
    detail = client.get(f"/api/history/{record.id}")

    assert listed.status_code == 200
    assert listed.json() == [detail.json()]
    assert detail.status_code == 200
    assert detail.json()["input_text"] == "任意实数 x，x = x。"
    assert detail.json()["created_at"]
    assert detail.json()["status"] == "GENERATED"
    assert detail.json()["output"]["ir"] == {"kind": "theorem"}
    assert client.get(f"/api/history/{record.id + 1}").status_code == 404


def test_upload_accepts_raw_bounded_utf8_and_never_executes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _runtime_value = _client(tmp_path)

    def unexpected_process(*args: object, **kwargs: object) -> None:
        raise AssertionError("uploaded text must never be executed")

    monkeypatch.setattr("subprocess.run", unexpected_process)
    response = client.post(
        "/api/upload",
        content="任意实数 x，x = x。".encode(),
        headers={"X-Filename": "input.md", "Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "input.md"
    assert response.json()["text"] == "任意实数 x，x = x。"
    assert response.json()["size"] == len("任意实数 x，x = x。".encode())


def test_upload_decodes_a_browser_safe_chinese_filename(tmp_path: Path) -> None:
    client, _runtime_value = _client(tmp_path)

    response = client.post(
        "/api/upload",
        content="任意实数 x，x = x。".encode(),
        headers={
            "X-Filename": quote("输入.md", safe=""),
            "Content-Type": "application/octet-stream",
        },
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "输入.md"


def test_bounded_upload_rejects_an_oversized_chunk_before_extending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GuardedBytearray(bytearray):
        def extend(self, data: bytes) -> None:
            if len(self) + len(data) > 4:
                raise AssertionError("oversized chunks must be rejected before allocation")
            super().extend(data)

    class OneChunkRequest:
        async def stream(self) -> AsyncIterator[bytes]:
            yield b"12345"

    monkeypatch.setattr(backend_app_module, "bytearray", GuardedBytearray, raising=False)

    with pytest.raises(ValueError, match="configured size limit"):
        asyncio.run(
            _read_bounded_body(cast(Request, OneChunkRequest()), max_bytes=4)
        )


@pytest.mark.parametrize(
    ("headers", "content"),
    [
        ({}, b"safe"),
        ({"X-Filename": "../input.md"}, b"safe"),
        ({"X-Filename": "bad.txt"}, b"\xff"),
        ({"X-Filename": "%FF.md"}, b"safe"),
        ({"X-Filename": "large.md"}, b"x" * 1_048_577),
        ({"X-Filename": "script.ps1"}, b"Write-Output unsafe"),
        ({"X-Filename": "program.exe"}, b"MZ"),
    ],
    ids=[
        "missing-filename",
        "unsafe-filename",
        "invalid-utf8",
        "invalid-filename-utf8",
        "too-large",
        "script-extension",
        "executable-extension",
    ],
)
def test_upload_rejects_missing_or_unsafe_filename_and_invalid_content(
    tmp_path: Path,
    headers: dict[str, str],
    content: bytes,
) -> None:
    client, _runtime_value = _client(tmp_path)

    response = client.post("/api/upload", content=content, headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("kind", "suffix", "media_type"),
    [
        ("lean", ".lean", "text/plain"),
        ("ir", ".ir.json", "application/json"),
        ("report", ".report.json", "application/json"),
    ],
)
def test_downloads_are_derived_from_history_output(
    tmp_path: Path,
    kind: str,
    suffix: str,
    media_type: str,
) -> None:
    client, runtime = _client(tmp_path)
    output = {
        "status": "GENERATED",
        "lean": "theorem refl (x : Real) : x = x := by rfl",
        "ir": {"theorem_name": "refl"},
        "diagnostics": [],
    }
    record = runtime.history.save(
        input_text="任意实数 x，x = x。",
        status="GENERATED",
        output=output,
        versions={},
    )

    response = client.get(f"/api/history/{record.id}/download/{kind}")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        f'attachment; filename="history-{record.id}{suffix}"'
    )
    assert response.headers["content-type"].startswith(media_type)
    if kind == "lean":
        assert response.text == output["lean"]
    elif kind == "ir":
        assert response.json() == output["ir"]
    else:
        assert response.json() == output


def test_download_rejects_unknown_types_records_and_paths(tmp_path: Path) -> None:
    client, runtime = _client(tmp_path)
    record = runtime.history.save(
        input_text="input",
        status="GENERATED",
        output={"lean": "code", "ir": {}},
        versions={},
    )

    assert client.get(f"/api/history/{record.id}/download/text").status_code == 422
    assert client.get(f"/api/history/{record.id + 1}/download/lean").status_code == 404
    assert client.get("/api/history/../download/lean").status_code in {404, 422}
    assert client.get("/api/history/%2e%2e/download/lean").status_code in {404, 422}


def test_cors_allows_only_the_configured_frontend_origin(tmp_path: Path) -> None:
    client, _runtime_value = _client(tmp_path)
    allowed = client.options(
        "/api/history",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = client.options(
        "/api/history",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers
