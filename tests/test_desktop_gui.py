from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

from chinese2lean.application.composition import build_product_runtime
from desktop.app import Chinese2LeanWindow
from desktop.controller import DesktopController, DesktopDocument
from desktop.local_api import LocalApiClient, LocalApiServer

ROOT = Path(__file__).parents[1]


class StubController:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _document(self, status: str = "GENERATED") -> DesktopDocument:
        return DesktopDocument(
            source_text="任意实数 x，x = x。",
            semantic_text="变量:\nx : Real\n\n假设:\n（无）\n\n结论:\nx = x",
            ir_json=json.dumps({"theorem_name": "demo", "variables": [{"name": "x"}]}),
            lean_code="theorem demo (x : ℝ) : x = x := by\n  rfl\n",
            status=status,
            verification_text=(
                "✓ Lean Kernel 验证通过" if status == "VERIFIED" else "尚未执行 Lean Kernel 验证"
            ),
            report={"status": status, "ir": {"theorem_name": "demo"}},
        )

    def parse(self, text: str) -> DesktopDocument:
        self.calls.append("parse")
        return self._document()

    def generate(self, text: str) -> DesktopDocument:
        self.calls.append("generate")
        return self._document()

    def verify(
        self, lean_code: str, document: DesktopDocument | None = None
    ) -> DesktopDocument:
        self.calls.append("verify")
        return self._document("VERIFIED")

    def list_examples(self) -> list[str]:
        return ["demo.md"]

    def load_example(self, name: str) -> str:
        return "示例内容"

    def open_input(self, path: Path) -> str:
        return "文件内容"

    def export(self, document: DesktopDocument, directory: Path) -> dict[str, Path]:
        return {}

    def history(self) -> list[object]:
        return [SimpleNamespace(id=1, created_at="2026-07-15", status="VERIFIED")]


def test_desktop_window_starts_and_drives_all_result_views() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        controller = StubController()
        window = Chinese2LeanWindow(root, controller)  # type: ignore[arg-type]

        assert root.title() == "Chinese2Lean"
        assert set(window.buttons) == {"解析", "生成 Lean", "验证", "导出", "历史"}
        assert window.tab_names == ["解析结果", "IR", "Lean 代码", "验证结果"]
        assert str(window.lean_text["state"]) == "disabled"

        window.input_text.insert("1.0", "任意实数 x，x = x。")
        window.on_parse()
        assert "x : Real" in window.semantic_text.get("1.0", "end")
        assert window.ir_tree.get_children()

        window.on_generate()
        assert "theorem demo" in window.lean_text.get("1.0", "end")
        assert window.lean_text.tag_ranges("keyword")

        window.on_verify()
        assert "✓ Lean Kernel 验证通过" in window.verification_text.get("1.0", "end")
        assert controller.calls == ["parse", "generate", "verify"]
    finally:
        root.destroy()


def test_desktop_window_runs_the_shared_core_and_real_pinned_lean(tmp_path: Path) -> None:
    runtime = build_product_runtime(
        ROOT,
        storage_root=tmp_path / "storage",
        log_root=tmp_path / "logs",
    )
    server = LocalApiServer(runtime)
    server.start()
    controller = DesktopController(
        LocalApiClient(server.base_url),
        runtime.history,
        ROOT / "examples" / "chinese",
    )
    root = tk.Tk()
    root.withdraw()
    try:
        window = Chinese2LeanWindow(root, controller)
        source = (ROOT / "examples" / "chinese" / "positive_add_one.md").read_text(
            encoding="utf-8"
        )
        window.input_text.insert("1.0", source)

        window.on_generate()
        window.on_verify()

        assert "✓ Lean Kernel 验证通过" in window.verification_text.get("1.0", "end")
        assert window.document is not None
        assert window.document.status == "VERIFIED"
        history = controller.history()
        assert len(history) == 2
        verified_record = history[0]
        assert verified_record.status == "VERIFIED"
        assert verified_record.input_text == source
        assert verified_record.output["source_text"] == source
        assert verified_record.output["ir"]["theorem_name"] == "positive_add_one"
        assert verified_record.output["statement_hash"]
        assert verified_record.output["verification"]["locked_environment"] is True
    finally:
        root.destroy()
        server.stop()
