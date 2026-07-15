from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from chinese2lean.application.models import ConvertResponse, VerifyResponse
from desktop.controller import DesktopController


class FakeService:
    records_conversion_history = False

    def convert(self, text: str, *, verify: bool = True) -> ConvertResponse:
        assert verify is False
        return ConvertResponse(
            status="GENERATED",
            lean="theorem demo (x : ℝ) : x = x := by\n  rfl\n",
            lean_code="theorem demo (x : ℝ) : x = x := by\n  rfl\n",
            ir={
                "theorem_name": "demo",
                "variables": [{"source_name": "x", "type": "Real"}],
                "assumptions": [],
                "conclusion": {"kind": "relation", "operator": "="},
            },
            source_text=text,
            normalized_text="对任意实数 x，x = x。",
            versions={"core_version": "0.1.0"},
        )

    def verify(self, lean_code: str) -> VerifyResponse:
        assert "theorem demo" in lean_code
        return VerifyResponse(
            status="VERIFIED",
            verified=True,
            success=True,
            exit_code=0,
            locked_environment=True,
        )


class FakeHistory:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def save(self, **values: Any) -> object:
        self.saved.append(values)
        return object()

    def list(self) -> list[object]:
        return [SimpleNamespace(id=1, status="VERIFIED", input_text="示例")]


def _controller(tmp_path: Path) -> tuple[DesktopController, FakeHistory]:
    examples = tmp_path / "examples"
    examples.mkdir()
    history = FakeHistory()
    return DesktopController(cast(Any, FakeService()), cast(Any, history), examples), history


def test_desktop_controller_uses_shared_service_and_preserves_views(tmp_path: Path) -> None:
    controller, history = _controller(tmp_path)

    document = controller.generate("任意实数 x，x = x。")

    assert document.status == "GENERATED"
    assert "变量:" in document.semantic_text
    assert "x : Real" in document.semantic_text
    assert json.loads(document.ir_json)["theorem_name"] == "demo"
    assert document.lean_code.startswith("theorem demo")
    assert "尚未执行 Lean Kernel 验证" in document.verification_text
    assert history.saved[0]["input_text"] == "任意实数 x，x = x。"

    verified = controller.verify(document.lean_code, document)
    assert verified.source_text == document.source_text
    assert verified.status == "VERIFIED"
    assert verified.verification_text == "✓ Lean Kernel 验证通过"
    assert len(history.saved) == 2


def test_desktop_controller_opens_examples_safely_and_exports_three_files(
    tmp_path: Path,
) -> None:
    controller, _ = _controller(tmp_path)
    example = tmp_path / "examples" / "demo.md"
    example.write_text("中文示例", encoding="utf-8")

    assert controller.list_examples() == ["demo.md"]
    assert controller.load_example("demo.md") == "中文示例"
    with pytest.raises(ValueError):
        controller.load_example("../demo.md")

    document = controller.generate("任意实数 x，x = x。")
    exported = controller.export(document, tmp_path / "exports")
    assert set(exported) == {"lean", "ir", "report"}
    assert exported["lean"].read_text(encoding="utf-8") == document.lean_code
    assert json.loads(exported["ir"].read_text(encoding="utf-8"))["theorem_name"] == "demo"
    assert json.loads(exported["report"].read_text(encoding="utf-8"))["status"] == "GENERATED"


def test_desktop_controller_rejects_oversized_or_non_utf8_input(tmp_path: Path) -> None:
    controller, _ = _controller(tmp_path)
    oversized = tmp_path / "oversized.md"
    oversized.write_bytes(b"x" * 1_000_001)
    with pytest.raises(ValueError, match="大小"):
        controller.open_input(oversized)

    binary = tmp_path / "binary.md"
    binary.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        controller.open_input(binary)
