from pathlib import Path

import pytest

from chinese2lean.lean.proof_renderer import choose_strategy
from chinese2lean.pipeline.converter import Converter

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("name", "variables", "assumptions", "conclusion", "strategy", "proof"),
    [
        ("实数自反", "x 是实数", "", "x = x", "rfl", "rfl"),
        ("正数加一", "x 是实数", "hx：x > 0", "x + 1 > 0", "linarith", "linarith"),
        ("实数加法交换", "x 是实数, y 是实数", "", "x + y = y + x", "ring", "ring"),
        ("自然数加法交换", "n 是自然数, m 是自然数", "", "n + m = m + n", "omega", "omega"),
        ("合取消去", "x 是实数", "h1：x > 0 且 x < 2", "x > 0", "exact", "exact h1.1"),
        ("合取构造", "x 是实数", "h1：x > 0\nh2：x < 2", "x > 0 且 x < 2", "aesop", "aesop"),
        ("正性蕴含", "x 是实数", "", "如果 x > 0, 那么 x + 1 > 0", "linarith", "intro h"),
        ("存在自身", "x 是实数", "", "存在实数 y, y = x", "exact", "exact ⟨x, rfl⟩"),
        ("全称自反", "", "", "对任意自然数 n, n = n", "rfl", "intro n"),
    ],
)
def test_proof_strategy_is_shape_based_and_explainable(
    name: str,
    variables: str,
    assumptions: str,
    conclusion: str,
    strategy: str,
    proof: str,
) -> None:
    source = f"""# 定理名称
{name}
# 变量
{variables}
# 假设
{assumptions}
# 结论
{conclusion}
"""
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "generated", result.warnings
    selected = choose_strategy(result.ir)
    assert selected.selected_strategy == strategy
    assert selected.reason
    assert proof in selected.code
    assert proof in result.lean_code
