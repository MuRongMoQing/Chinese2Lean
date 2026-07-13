from pathlib import Path

from chinese2lean.ir.serialization import from_json, to_json
from chinese2lean.lean.names import NameAllocator
from chinese2lean.normalization.normalizer import Normalizer
from chinese2lean.normalization.terminology import Terminology
from chinese2lean.pipeline.converter import Converter

ROOT = Path(__file__).parents[1]


def test_normalization_is_traceable_and_uses_longest_alias() -> None:
    result = Normalizer(Terminology.load(ROOT / "terminology")).normalize("任意实数 x 不小于 0。")
    assert result.text == "对任意实数 x >= 0."
    assert {(item.original, item.term_id) for item in result.mappings} >= {
        ("任意", "logic.forall"),
        ("不小于", "inequality.ge"),
    }


def test_name_allocator_handles_reserved_words_and_collisions() -> None:
    allocator = NameAllocator()
    assert allocator.allocate("定理", "theorem") == "theorem_"
    assert allocator.allocate("定理", "theorem") == "theorem__2"
    assert allocator.allocate("中文名称").startswith("name_")


def test_positive_add_one_converts_through_public_pipeline() -> None:
    source = """定理名称：正数加一仍为正
变量：x 是实数
假设：x > 0
结论：x + 1 > 0
证明：因为 x > 0，所以 x + 1 > 0。
"""
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "generated"
    assert "theorem positive_add_one (x : ℝ) (h1 : x > 0) : x + 1 > 0 := by" in result.lean_code
    assert result.lean_code.endswith("  linarith\n")
    restored = from_json(to_json(result.ir))
    assert restored == result.ir
    assert result.ir.name_mappings["正数加一仍为正"] == "positive_add_one"


def test_undeclared_variable_is_not_guessed() -> None:
    source = """# 定理名称
坏例子
# 变量
x：实数
# 结论
y > 0
"""
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "parse_failed"
    assert any(item.code == "UNDECLARED_VARIABLE" for item in result.warnings)
