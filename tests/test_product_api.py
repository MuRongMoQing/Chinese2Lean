import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chinese2lean.api.app import create_app
from chinese2lean.application.composition import ProductRuntime, build_product_runtime

ROOT = Path(__file__).parents[1]


def _runtime(tmp_path: Path) -> ProductRuntime:
    return build_product_runtime(
        ROOT,
        storage_root=tmp_path / "storage",
        log_root=tmp_path / "logs",
    )


def test_product_api_uses_the_shared_default_runtime_and_records_history(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    client = TestClient(create_app(runtime))

    assert client.get("/api/health").json() == {"status": "ok", "version": "0.1.0"}
    version = client.get("/api/version")
    assert version.status_code == 200
    assert version.json() == {
        "chinese2lean_version": "0.1.0",
        "core_version": "0.1.0",
        "desktop_version": "0.1.0",
        "web_version": "0.1.0",
        "lean_version": "4.19.0",
        "mathlib_revision": "c44e0c8ee63ca166450922a373c7409c5d26b00b",
        "dictionary_version": "0.1.0",
        "ir_schema_version": "1",
    }

    source = (ROOT / "examples" / "chinese" / "positive_add_one.md").read_text(
        encoding="utf-8"
    )
    converted = client.post("/api/convert", json={"text": source, "verify": False})
    assert converted.status_code == 200
    payload = converted.json()
    assert payload["status"] == "GENERATED"
    assert payload["lean"].startswith("import Mathlib")
    assert payload["ir"]["theorem_name"] == "positive_add_one"
    assert payload["source_text"] == source
    assert payload["normalized_text"]

    history = runtime.history.list()
    assert len(history) == 1
    assert history[0].input_text == source
    assert history[0].status == "GENERATED"
    assert history[0].output["statement_hash"] == payload["statement_hash"]


def test_product_api_rejects_forbidden_lean_before_starting_a_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)

    def unexpected_process(*args: object, **kwargs: object) -> None:
        raise AssertionError("forbidden Lean must be rejected before subprocess execution")

    monkeypatch.setattr(subprocess, "run", unexpected_process)
    client = TestClient(create_app(runtime))

    response = client.post(
        "/api/verify",
        json={"lean_code": "theorem forbidden_probe : True := by\n  sorry\n"},
    )

    assert response.status_code == 422
    assert "sorry" in response.json()["detail"]


def test_product_api_enforces_the_shared_input_size_limit(tmp_path: Path) -> None:
    client = TestClient(create_app(_runtime(tmp_path)))

    response = client.post(
        "/api/convert",
        json={"text": "x" * 1_000_001, "verify": False},
    )

    assert response.status_code == 422


def test_product_api_verifies_with_the_pinned_real_lean_kernel(tmp_path: Path) -> None:
    client = TestClient(create_app(_runtime(tmp_path)))

    response = client.post(
        "/api/verify",
        json={"lean_code": "theorem api_true : True := by\n  trivial\n"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "VERIFIED"
    assert payload["verified"] is True
    assert payload["success"] is True
    assert payload["locked_environment"] is True


def test_product_convert_verifies_with_real_lean_and_records_lean_log(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    client = TestClient(create_app(runtime))
    source = (ROOT / "examples" / "chinese" / "positive_add_one.md").read_text(
        encoding="utf-8"
    )

    response = client.post("/api/convert", json={"text": source, "verify": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "VERIFIED"
    assert payload["verified"] is True
    lean_log = (tmp_path / "logs" / "lean.log").read_text(encoding="utf-8")
    assert "convert verification status=VERIFIED" in lean_log
