from pathlib import Path

from chinese2lean.ir.models import TheoremIR


def to_json(ir: TheoremIR, *, indent: int = 2) -> str:
    return ir.model_dump_json(indent=indent, exclude_none=True)


def from_json(data: str) -> TheoremIR:
    return TheoremIR.model_validate_json(data)


def save_json(ir: TheoremIR, path: Path) -> None:
    path.write_text(to_json(ir) + "\n", encoding="utf-8")
