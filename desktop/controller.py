from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from chinese2lean.application.models import ConvertResponse, VerifyResponse
from chinese2lean.storage.history import HistoryRecord

MAX_INPUT_BYTES = 1_000_000


class DesktopServicePort(Protocol):
    records_conversion_history: bool

    def convert(self, text: str, *, verify: bool = True) -> ConvertResponse: ...

    def verify(self, lean_code: str) -> VerifyResponse: ...


class DesktopHistoryPort(Protocol):
    def save(
        self,
        *,
        input_text: str,
        status: str,
        output: Mapping[str, Any],
        versions: Mapping[str, str],
    ) -> object: ...

    def list(self) -> list[HistoryRecord]: ...


@dataclass(frozen=True, slots=True)
class DesktopDocument:
    source_text: str
    semantic_text: str
    ir_json: str
    lean_code: str
    status: str
    verification_text: str
    report: dict[str, Any]


class DesktopController:
    """Desktop-facing adapter over the shared product runtime."""

    def __init__(
        self,
        service: DesktopServicePort,
        history: DesktopHistoryPort,
        examples_root: Path,
    ) -> None:
        self._service = service
        self._history = history
        self._examples_root = examples_root.resolve()

    def parse(self, text: str) -> DesktopDocument:
        return self._convert(text)

    def generate(self, text: str) -> DesktopDocument:
        return self._convert(text)

    def verify(
        self,
        lean_code: str,
        document: DesktopDocument | None = None,
    ) -> DesktopDocument:
        response = self._service.verify(lean_code)
        previous = document or DesktopDocument(
            source_text="",
            semantic_text="",
            ir_json="{}",
            lean_code=lean_code,
            status="GENERATED",
            verification_text="尚未执行 Lean Kernel 验证",
            report={},
        )
        report = dict(previous.report)
        report["status"] = response.status
        report["verification"] = response.model_dump(mode="json")
        verified = DesktopDocument(
            source_text=previous.source_text,
            semantic_text=previous.semantic_text,
            ir_json=previous.ir_json,
            lean_code=lean_code,
            status=response.status,
            verification_text=self._verification_text(response),
            report=report,
        )
        self._save_history(verified)
        return verified

    def open_input(self, path: Path) -> str:
        content = path.read_bytes()
        if len(content) > MAX_INPUT_BYTES:
            raise ValueError("输入文件超过 1 MB 大小限制。")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("输入文件必须是 UTF-8 文本。") from error

    def list_examples(self) -> list[str]:
        if not self._examples_root.is_dir():
            return []
        return sorted(
            path.name
            for path in self._examples_root.iterdir()
            if path.is_file() and path.suffix.lower() == ".md"
        )

    def load_example(self, name: str) -> str:
        if Path(name).name != name or name not in self.list_examples():
            raise ValueError("示例名称不安全或不存在。")
        path = (self._examples_root / name).resolve()
        if not path.is_relative_to(self._examples_root):
            raise ValueError("示例路径超出示例目录。")
        return self.open_input(path)

    def export(self, document: DesktopDocument, directory: Path) -> dict[str, Path]:
        destination = directory.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        ir = json.loads(document.ir_json)
        raw_name = ir.get("theorem_name", "chinese2lean_result") if isinstance(ir, dict) else ""
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw_name)).strip("_")
        base_name = safe_name or "chinese2lean_result"
        paths = {
            "lean": destination / f"{base_name}.lean",
            "ir": destination / f"{base_name}.ir.json",
            "report": destination / f"{base_name}.report.json",
        }
        paths["lean"].write_text(document.lean_code, encoding="utf-8", newline="\n")
        paths["ir"].write_text(
            json.dumps(ir, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        paths["report"].write_text(
            json.dumps(document.report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return paths

    def history(self) -> list[HistoryRecord]:
        return self._history.list()

    def _convert(self, text: str) -> DesktopDocument:
        response = self._service.convert(text, verify=False)
        report = response.model_dump(mode="json")
        document = DesktopDocument(
            source_text=response.source_text,
            semantic_text=self._semantic_text(response),
            ir_json=json.dumps(response.ir, ensure_ascii=False, indent=2),
            lean_code=response.lean,
            status=response.status,
            verification_text="尚未执行 Lean Kernel 验证",
            report=report,
        )
        if not self._service.records_conversion_history:
            self._save_history(document)
        return document

    def _save_history(self, document: DesktopDocument) -> None:
        versions = document.report.get("versions", {})
        if not isinstance(versions, dict):
            versions = {}
        self._history.save(
            input_text=document.source_text or document.lean_code,
            status=document.status,
            output=document.report,
            versions={str(key): str(value) for key, value in versions.items()},
        )

    @staticmethod
    def _semantic_text(response: ConvertResponse) -> str:
        ir = response.ir
        variables: list[str] = []
        for variable in ir.get("variables", []):
            if isinstance(variable, dict):
                name = variable.get("source_name") or variable.get("name") or "?"
                variable_type = (
                    variable.get("type")
                    or variable.get("binder_type")
                    or variable.get("inferred_type")
                    or "?"
                )
                variables.append(f"{name} : {variable_type}")
        assumptions = [
            DesktopController._compact(item) for item in ir.get("assumptions", [])
        ]
        conclusion = DesktopController._compact(ir.get("conclusion", "（无）"))
        return "\n".join(
            [
                "变量:",
                *(variables or ["（无）"]),
                "",
                "假设:",
                *(assumptions or ["（无）"]),
                "",
                "结论:",
                conclusion,
            ]
        )

    @staticmethod
    def _compact(value: object) -> str:
        if isinstance(value, dict):
            span = value.get("source_span")
            if isinstance(span, dict) and span.get("text"):
                return str(span["text"])
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _verification_text(response: VerifyResponse) -> str:
        if response.status == "VERIFIED" and response.locked_environment:
            return "✓ Lean Kernel 验证通过"
        if not response.diagnostics:
            return "Lean Kernel 验证失败\n建议修复：检查锁定工具链与 Lean 原始输出。"
        sections: list[str] = ["Lean Kernel 验证失败"]
        for diagnostic in response.diagnostics:
            sections.extend(
                [
                    f"文件：{diagnostic.get('file') or 'Generated.lean'}",
                    f"行：{diagnostic.get('line') or '-'}",
                    f"列：{diagnostic.get('column') or '-'}",
                    f"错误类型：{diagnostic.get('code') or 'LEAN_ERROR'}",
                    f"原始错误：{diagnostic.get('raw_message') or diagnostic.get('message') or ''}",
                    "建议修复：根据诊断检查受控输入，不得改变数学命题。",
                ]
            )
        return "\n".join(sections)
