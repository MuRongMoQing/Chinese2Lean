from pathlib import Path

import pytest

from chinese2lean.pipeline.converter import Converter

ROOT = Path(__file__).parents[1]
CHINESE_EXAMPLES = sorted((ROOT / "examples" / "chinese").glob("*.md"))


def test_success_catalog_contains_twenty_examples() -> None:
    assert len(CHINESE_EXAMPLES) >= 20


def test_generated_artifacts_match_the_deterministic_renderer() -> None:
    converter = Converter.default(ROOT)
    for path in CHINESE_EXAMPLES:
        result = converter.convert_text(path.read_text(encoding="utf-8"), verify=False)
        generated = ROOT / "examples" / "generated" / f"{path.stem}.lean"
        assert result.status.value == "generated", path
        assert generated.read_text(encoding="utf-8").strip() == result.lean_code.strip()


@pytest.mark.parametrize("path", CHINESE_EXAMPLES, ids=lambda path: path.stem)
def test_each_chinese_example_generates_and_really_compiles(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    result = Converter.default(ROOT).convert_text(source, verify=True)
    assert result.status.value == "verified", {
        "path": str(path),
        "warnings": [item.model_dump() for item in result.warnings],
        "diagnostics": [item.model_dump() for item in result.diagnostics],
    }
    assert result.success and result.verified
    assert result.statement_hash
    assert result.lean_code
    assert all(token not in result.lean_code for token in ("sorry", "admit", "axiom", "unsafe"))
