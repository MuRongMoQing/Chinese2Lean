from pathlib import Path

import pytest

from chinese2lean.parser.statement_parser import ExpressionParser
from chinese2lean.pipeline.converter import Converter

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("name", "variables", "assumptions", "conclusion", "tactic"),
    [
        ("自然数加法交换律", "n 是自然数, m 是自然数", "", "n + m = m + n", "omega"),
        ("正数相加仍为正", "x 是实数, y 是实数", "x > 0\ny > 0", "x + y > 0", "linarith"),
        ("一次不等式", "x 是实数", "x > 2", "2 * x + 1 > 5", "linarith"),
        ("平方非负", "x 是实数", "", "x ^ 2 >= 0", "positivity"),
        ("合取命题", "x 是实数", "x > 0\nx < 2", "x > 0 且 x < 2", "aesop"),
        ("反证简单例", "x 是实数", "x > 0\n¬ (x > 0)", "x = 0", "linarith"),
    ],
)
def test_supported_domain_cases_generate_structured_lean(
    name: str, variables: str, assumptions: str, conclusion: str, tactic: str
) -> None:
    assumption_section = "\n".join(
        f"h{i + 1}：{line}" for i, line in enumerate(assumptions.splitlines())
    )
    source = f"""# 定理名称
{name}
# 变量
{variables}
# 假设
{assumption_section}
# 结论
{conclusion}
"""
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "generated", result.warnings
    assert f"  {tactic}\n" in result.lean_code


def test_expression_precedence_keeps_multiplication_inside_addition() -> None:
    expression = ExpressionParser().parse("x + 2 * y > 3")
    assert expression.operator == ">"
    assert expression.args[0].operator == "+"
    assert expression.args[0].args[1].operator == "*"


def test_natural_sentence_quantifier_form_is_supported() -> None:
    result = Converter.default(ROOT).convert_text(
        "对于任意实数 x，如果 x > 0，那么 x + 1 > 0。", verify=False
    )
    assert result.status.value == "generated"
    assert "(x : ℝ)" in result.lean_code


def test_missing_variable_type_is_rejected() -> None:
    source = """# 定理名称
缺类型
# 变量
x
# 结论
x > 0
"""
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "parse_failed"


def test_ambiguous_free_text_is_reported() -> None:
    result = Converter.default(ROOT).convert_text("某个数显然比较大。", verify=False)
    assert result.status.value in {"parse_failed", "ambiguous"}
    assert result.ir.ambiguities
