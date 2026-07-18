from __future__ import annotations

import json
import os
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from chinese2lean.application import build_product_runtime
from chinese2lean.product.environment_backend import (
    SystemEnvironmentBackend,
    load_bundled_elan_asset,
)
from chinese2lean.product.initialization import EnvironmentInitializer
from chinese2lean.product.logging import configure_product_logging
from desktop.controller import DesktopController, DesktopDocument
from desktop.initialization import launch_desktop
from desktop.local_api import LocalApiClient, LocalApiServer

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Chinese2LeanWindow:
    """Tk delivery adapter for the shared Chinese2Lean application service."""

    def __init__(self, root: tk.Tk, controller: DesktopController) -> None:
        self.root = root
        self.controller = controller
        self.document: DesktopDocument | None = None
        self.buttons: dict[str, ttk.Button] = {}
        self.tab_names = ["解析结果", "IR", "Lean 代码", "验证结果"]
        root.title("Chinese2Lean")
        root.geometry("1100x760")
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self.root, padding=10)
        container.pack(fill="both", expand=True)

        input_frame = ttk.LabelFrame(container, text="中文数学输入", padding=8)
        input_frame.pack(fill="both", expand=True)
        self.input_text = tk.Text(input_frame, height=14, wrap="word", undo=True)
        self.input_text.pack(fill="both", expand=True)

        source_bar = ttk.Frame(input_frame)
        source_bar.pack(fill="x", pady=(6, 0))
        ttk.Button(source_bar, text="打开文件", command=self.on_open).pack(side="left")
        self.example_name = tk.StringVar()
        self.example_box = ttk.Combobox(
            source_bar,
            textvariable=self.example_name,
            values=self.controller.list_examples(),
            state="readonly",
            width=36,
        )
        self.example_box.pack(side="left", padx=6)
        ttk.Button(source_bar, text="加载示例", command=self.on_load_example).pack(side="left")

        toolbar = ttk.Frame(container)
        toolbar.pack(fill="x", pady=8)
        commands = {
            "解析": self.on_parse,
            "生成 Lean": self.on_generate,
            "验证": self.on_verify,
            "导出": self.on_export,
            "历史": self.on_history,
        }
        for label, command in commands.items():
            button = ttk.Button(toolbar, text=label, command=command)
            button.pack(side="left", padx=(0, 6))
            self.buttons[label] = button

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)
        frames = [ttk.Frame(self.notebook) for _ in self.tab_names]
        for frame, name in zip(frames, self.tab_names, strict=True):
            self.notebook.add(frame, text=name)

        self.semantic_text = self._readonly_text(frames[0])

        ir_actions = ttk.Frame(frames[1])
        ir_actions.pack(fill="x")
        ttk.Button(ir_actions, text="复制 IR JSON", command=self.copy_ir).pack(side="left")
        self.ir_tree = ttk.Treeview(frames[1], columns=("value",), show="tree headings")
        self.ir_tree.heading("#0", text="字段")
        self.ir_tree.heading("value", text="值")
        self.ir_tree.pack(fill="both", expand=True)

        lean_actions = ttk.Frame(frames[2])
        lean_actions.pack(fill="x")
        ttk.Button(lean_actions, text="复制 Lean", command=self.copy_lean).pack(side="left")
        ttk.Button(lean_actions, text="保存 Lean", command=self.save_lean).pack(side="left", padx=6)
        self.lean_text = tk.Text(frames[2], wrap="none", state="disabled")
        self.lean_text.tag_configure(
            "keyword",
            foreground="#7A3E9D",
            font=("TkFixedFont", 10, "bold"),
        )
        self.lean_text.pack(fill="both", expand=True)

        self.verification_text = self._readonly_text(frames[3])
        self.status = tk.StringVar(value="就绪")
        ttk.Label(container, textvariable=self.status, anchor="w").pack(fill="x", pady=(6, 0))

    @staticmethod
    def _readonly_text(parent: ttk.Frame) -> tk.Text:
        widget = tk.Text(parent, wrap="word", state="disabled")
        widget.pack(fill="both", expand=True)
        return widget

    def on_parse(self) -> None:
        document = self.controller.parse(self._source())
        self._show(document, 0)

    def on_generate(self) -> None:
        document = self.controller.generate(self._source())
        self._show(document, 2)

    def on_verify(self) -> None:
        document = self.document
        if document is None:
            document = self.controller.generate(self._source())
        lean_code = self.lean_text.get("1.0", "end-1c") or document.lean_code
        self._show(self.controller.verify(lean_code, document), 3)

    def on_open(self) -> None:
        filename = filedialog.askopenfilename(
            title="打开中文数学文件",
            filetypes=(("Markdown/文本", "*.md *.txt"), ("所有文件", "*.*")),
        )
        if filename:
            self._set_input(self.controller.open_input(Path(filename)))

    def on_load_example(self) -> None:
        name = self.example_name.get()
        if name:
            self._set_input(self.controller.load_example(name))

    def on_export(self) -> None:
        if self.document is None:
            messagebox.showwarning("Chinese2Lean", "请先生成结果。")
            return
        directory = filedialog.askdirectory(title="选择导出目录")
        if directory:
            paths = self.controller.export(self.document, Path(directory))
            messagebox.showinfo("Chinese2Lean", f"已导出 {len(paths)} 个文件。")

    def on_history(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Chinese2Lean 历史")
        tree = ttk.Treeview(window, columns=("time", "status"), show="headings")
        tree.heading("time", text="时间")
        tree.heading("status", text="状态")
        for record in self.controller.history():
            tree.insert(
                "",
                "end",
                values=(str(getattr(record, "created_at", "")), str(getattr(record, "status", ""))),
            )
        tree.pack(fill="both", expand=True)

    def copy_ir(self) -> None:
        if self.document is not None:
            self._clipboard(self.document.ir_json)

    def copy_lean(self) -> None:
        self._clipboard(self.lean_text.get("1.0", "end-1c"))

    def save_lean(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="保存 Lean 文件",
            defaultextension=".lean",
            filetypes=(("Lean", "*.lean"),),
        )
        if filename:
            Path(filename).write_text(
                self.lean_text.get("1.0", "end-1c"),
                encoding="utf-8",
                newline="\n",
            )

    def _show(self, document: DesktopDocument, tab_index: int) -> None:
        self.document = document
        self._replace_readonly(self.semantic_text, document.semantic_text)
        self._replace_readonly(self.verification_text, document.verification_text)
        self.lean_text.configure(state="normal")
        self.lean_text.delete("1.0", "end")
        self.lean_text.insert("1.0", document.lean_code)
        self._highlight_lean()
        self.lean_text.configure(state="disabled")
        self._populate_ir(document.ir_json)
        self.notebook.select(tab_index)  # type: ignore[no-untyped-call]
        self.status.set(document.status)

    def _populate_ir(self, ir_json: str) -> None:
        for item in self.ir_tree.get_children():
            self.ir_tree.delete(item)
        self._insert_json("", "IR", json.loads(ir_json))

    def _insert_json(self, parent: str, key: str, value: Any) -> None:
        if isinstance(value, dict):
            node = self.ir_tree.insert(parent, "end", text=key, open=True)
            for child_key, child_value in value.items():
                self._insert_json(node, str(child_key), child_value)
        elif isinstance(value, list):
            node = self.ir_tree.insert(parent, "end", text=key, open=True)
            for index, child_value in enumerate(value):
                self._insert_json(node, str(index), child_value)
        else:
            self.ir_tree.insert(parent, "end", text=key, values=(str(value),))

    def _highlight_lean(self) -> None:
        self.lean_text.tag_remove("keyword", "1.0", "end")
        source = self.lean_text.get("1.0", "end-1c")
        pattern = r"\b(import|theorem|def|by|where|let|have|show|from)\b"
        for match in re.finditer(pattern, source):
            self.lean_text.tag_add(
                "keyword",
                f"1.0+{match.start()}c",
                f"1.0+{match.end()}c",
            )

    def _source(self) -> str:
        source = self.input_text.get("1.0", "end-1c")
        if not source.strip():
            raise ValueError("请输入中文数学文本。")
        return source

    def _set_input(self, text: str) -> None:
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", text)

    def _clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    @staticmethod
    def _replace_readonly(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")


def _user_data_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / "Chinese2Lean").resolve()


def _close_loggers(loggers: dict[str, Any]) -> None:
    for logger in loggers.values():
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)


def _launch_product(
    root: tk.Tk,
    initializer: EnvironmentInitializer,
    data_root: Path,
    elan_home: Path,
) -> Any:
    runtime = build_product_runtime(
        PROJECT_ROOT,
        storage_root=data_root / "storage",
        log_root=data_root / "logs",
        verification_root=initializer.workspace_root,
        elan_home=elan_home,
    )
    server = LocalApiServer(runtime)
    try:
        server.start()
        controller = DesktopController(
            LocalApiClient(server.base_url),
            runtime.history,
            PROJECT_ROOT / "examples" / "chinese",
        )
        Chinese2LeanWindow(root, controller)
    except Exception:
        server.stop()
        _close_loggers(runtime.loggers)
        raise

    def cleanup() -> None:
        server.stop()
        _close_loggers(runtime.loggers)

    return cleanup


def main() -> None:
    root = tk.Tk()
    data_root = _user_data_root()
    bootstrap_loggers = configure_product_logging(data_root / "logs")
    environment_backend = SystemEnvironmentBackend(
        PROJECT_ROOT,
        data_root / "environment",
        bootstrap_asset=load_bundled_elan_asset(PROJECT_ROOT / "runtime"),
    )
    initializer = EnvironmentInitializer(
        PROJECT_ROOT,
        data_root / "state",
        environment_backend,
        bootstrap_loggers["environment"],
    )
    application = launch_desktop(
        root,
        initializer,
        lambda application_root: _launch_product(
            application_root,
            initializer,
            data_root,
            environment_backend.elan_home,
        ),
    )
    try:
        application.start()
        root.mainloop()
    finally:
        application.shutdown()
        _close_loggers(bootstrap_loggers)
