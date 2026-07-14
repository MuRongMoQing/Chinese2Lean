from pathlib import Path

import pytest

from chinese2lean.lean.expression_renderer import render_expr
from chinese2lean.parser.statement_parser import ExpressionParser
from chinese2lean.pipeline.converter import Converter

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x + y * z", "x + y * z"),
        ("(x + y) * z", "(x + y) * z"),
        ("-x^2", "-(x ^ 2)"),
        ("(-x)^2", "(-x) ^ 2"),
        ("x + 1 > 0", "x + 1 > 0"),
        ("x > 0 并且 y > 0", "x > 0 ∧ y > 0"),
        ("如果 x > 0，那么 x + 1 > 0", "x > 0 → x + 1 > 0"),
    ],
)
def test_expression_precedence_and_controlled_logic(source: str, expected: str) -> None:
    assert render_expr(ExpressionParser().parse(source)) == expected


@pytest.mark.parametrize(
    ("source", "kind", "expected_type", "expected"),
    [
        ("存在实数 y, y > 0", "exists", "Real", "∃ y : ℝ, y > 0"),
        ("对任意自然数 n, n = n", "forall", "Nat", "∀ n : ℕ, n = n"),
    ],
)
def test_typed_quantifiers_are_structured_and_renderable(
    source: str, kind: str, expected_type: str, expected: str
) -> None:
    expression = ExpressionParser().parse(source)
    assert expression.kind == "quantifier"
    assert expression.operator == kind
    assert expression.binder_type == expected_type
    assert expression.inferred_type == "Prop"
    assert render_expr(expression) == expected


def test_natural_sentence_supports_two_variables_and_conjunction() -> None:
    result = Converter.default(ROOT).convert_text(
        "对于任意实数 x 和 y，如果 x > 0 并且 y > 0，那么 x + y > 0。",
        verify=False,
    )
    assert result.status.value == "generated", result.warnings
    assert [item.lean_name for item in result.ir.variables] == ["x", "y"]
    assert result.ir.assumptions[0].proposition.operator == "∧"


def test_natural_sentence_type_ambiguity_stops_generation() -> None:
    result = Converter.default(ROOT).convert_text(
        "对于任意自然数 n，如果 n > 0，那么 n - 1 <= n。",
        verify=False,
    )
    assert result.status.value == "ambiguous"
    assert "NAT_SUBTRACTION_AMBIGUOUS" in {item.code for item in result.ir.ambiguities}


def test_every_supported_logic_phrase_is_registered_in_the_dictionary() -> None:
    from chinese2lean.normalization.terminology import Terminology

    terminology = Terminology.load(ROOT / "terminology")
    assert terminology.lookup("和")[0].id == "logic.quantified_variable_join"
    assert terminology.lookup("或者")[0].id == "logic.or"


def test_structured_existential_and_implication_render_from_ir() -> None:
    existential = """# 定理名称
存在自身
# 变量
x：实数
# 结论
存在实数 y, y = x
"""
    implication = """# 定理名称
正性蕴含
# 变量
x：实数
# 结论
如果 x > 0, 那么 x + 1 > 0
"""
    exists_result = Converter.default(ROOT).convert_text(existential, verify=False)
    implies_result = Converter.default(ROOT).convert_text(implication, verify=False)
    assert exists_result.status.value == "generated", exists_result.warnings
    assert ": ∃ y : ℝ, y = x := by" in exists_result.lean_code
    assert implies_result.ir.conclusion.operator == "→"
    assert ": x > 0 → x + 1 > 0 := by" in implies_result.lean_code
