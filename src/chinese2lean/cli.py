from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from chinese2lean.ir.serialization import save_json
from chinese2lean.normalization.terminology import Terminology, TerminologyConflict
from chinese2lean.pipeline.converter import Converter
from chinese2lean.verification.runner import ForbiddenLeanConstruct, LeanRunner

app = typer.Typer(help="将受控中文数学文本转换为 Lean 4 + Mathlib。", no_args_is_help=True)
terminology_app = typer.Typer(help="检查和查询版本化术语词典。")
examples_app = typer.Typer(help="列出内置示例。")
app.add_typer(terminology_app, name="terminology")
app.add_typer(examples_app, name="examples")


def _root() -> Path:
    candidate = Path.cwd()
    if (candidate / "terminology").is_dir():
        return candidate
    return Path(__file__).resolve().parents[2]


def _read_source(path: Path, maximum: int = 1_000_000) -> str:
    resolved = path.resolve()
    if not resolved.is_file():
        raise typer.BadParameter(f"输入文件不存在：{path}")
    if resolved.stat().st_size > maximum:
        raise typer.BadParameter("输入文件超过 1 MB 限制。")
    return resolved.read_text(encoding="utf-8")


def _safe_json(value: object, *, indent: int | None = None) -> str:
    """JSON safe for Windows consoles whose legacy encoding cannot represent Lean symbols."""
    return json.dumps(value, ensure_ascii=True, indent=indent)


@app.command()
def convert(
    input_path: Annotated[Path, typer.Argument(help="受控中文 Markdown/文本文件")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    no_verify: Annotated[bool, typer.Option("--no-verify")] = False,
) -> None:
    """转换并生成 Lean、IR JSON、报告和审计记录。"""
    root = _root()
    result = Converter.default(root).convert_text(_read_source(input_path), verify=not no_verify)
    lean_path = (output or input_path.with_suffix(".lean")).resolve()
    lean_path.parent.mkdir(parents=True, exist_ok=True)
    if result.lean_code:
        lean_path.write_text(result.lean_code, encoding="utf-8", newline="\n")
    save_json(result.ir, lean_path.with_suffix(".ir.json"))
    lean_path.with_suffix(".conversion.json").write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    report = [
        f"# 转换报告：{input_path.name}",
        "",
        f"- 状态：`{result.status.value}`",
        f"- Lean 验证：{'成功' if result.verified else '未成功'}",
        f"- 警告数：{len(result.warnings)}",
        f"- 诊断数：{len(result.diagnostics)}",
        "",
    ]
    if result.warnings:
        report.extend(
            ["## 未解决问题", *[f"- `{item.code}`：{item.message}" for item in result.warnings]]
        )
    lean_path.with_suffix(".report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    typer.echo(
        _safe_json(
            {
                "status": result.status.value,
                "verified": result.verified,
                "lean": str(lean_path),
                "ir": str(lean_path.with_suffix(".ir.json")),
            }
        )
    )
    if not result.success:
        raise typer.Exit(code=1)


@app.command("parse")
def parse_command(
    input_path: Annotated[Path, typer.Argument()],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("theorem.json"),
) -> None:
    result = Converter.default(_root()).convert_text(_read_source(input_path), verify=False)
    save_json(result.ir, output.resolve())
    typer.echo(str(output.resolve()))
    if result.status.value in {"parse_failed", "ambiguous"}:
        raise typer.Exit(code=1)


@app.command()
def verify(path: Annotated[Path, typer.Argument(help="待验证的 .lean 文件")]) -> None:
    try:
        result = LeanRunner(_root() / "lean_workspace").verify_file(path)
    except (ForbiddenLeanConstruct, FileNotFoundError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(_safe_json(result.model_dump(), indent=2))
    if not result.success:
        raise typer.Exit(code=1)


@terminology_app.command("check")
def terminology_check() -> None:
    try:
        terminology = Terminology.load(_root() / "terminology")
    except TerminologyConflict as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"词典版本 {terminology.version}：{len(terminology.entries)} 个条目，无冲突。")


@terminology_app.command("lookup")
def terminology_lookup(query: Annotated[str, typer.Argument()]) -> None:
    entries = Terminology.load(_root() / "terminology").lookup(query)
    typer.echo(_safe_json([item.model_dump() for item in entries], indent=2))


@examples_app.command("list")
def examples_list() -> None:
    for path in sorted((_root() / "examples").glob("*.md")):
        typer.echo(path.name)


if __name__ == "__main__":
    app()
