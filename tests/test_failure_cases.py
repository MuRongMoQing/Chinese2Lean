from pathlib import Path

import pytest

from chinese2lean.pipeline.converter import Converter

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("source", "status", "code"),
    [
        (
            "# 定理名称\n未声明变量\n# 变量\nx：实数\n# 结论\ny > 0\n",
            "parse_failed",
            "UNDECLARED_VARIABLE",
        ),
        (
            "# 定理名称\n缺少类型\n# 变量\nx\n# 结论\nx > 0\n",
            "parse_failed",
            "INVALID_VARIABLE_DECLARATION",
        ),
        (
            "# 定理名称\n冲突类型\n# 变量\nx：自然数, x：整数\n# 结论\nx = x\n",
            "ir_invalid",
            "CONFLICTING_VARIABLE_TYPES",
        ),
        (
            "# 定理名称\n未知术语\n# 变量\nx：实数\n# 结论\nx 约等于 0\n",
            "parse_failed",
            "INVALID_CONCLUSION",
        ),
        (
            "# 定理名称\n量词不清\n# 结论\n任意 n, n = n\n",
            "parse_failed",
            "INVALID_CONCLUSION",
        ),
        ("有一个数显然很大。", "parse_failed", "UNSUPPORTED_SYNTAX"),
        (
            "# 定理名称\n自然数减法\n# 变量\nn：自然数\n# 结论\nn - 1 <= n\n",
            "ambiguous",
            "NAT_SUBTRACTION_AMBIGUOUS",
        ),
        (
            "# 定理名称\n混合数域\n# 变量\nn：自然数, x：实数\n# 结论\nn < x\n",
            "ambiguous",
            "MIXED_NUMERIC_TYPES",
        ),
        (
            "# 定理名称\n冲突结论\n# 变量\nx：实数\n# 结论\nx > 0\nx < 0\n",
            "ambiguous",
            "STRUCTURED_FIELD_CONFLICT",
        ),
        (
            "# 定理名称\n整数除法\n# 变量\nz：整数\n# 结论\nz / 2 = z\n",
            "ambiguous",
            "DIVISION_SEMANTICS_AMBIGUOUS",
        ),
    ],
)
def test_failures_and_ambiguities_have_stable_codes(source: str, status: str, code: str) -> None:
    result = Converter.default(ROOT).convert_text(source, verify=False)
    all_issues = [*result.warnings, *result.ir.ambiguities]
    assert result.status.value == status
    assert code in {item.code for item in all_issues}
    assert not result.success


def test_structured_conclusion_conflicting_with_natural_body_is_ambiguous() -> None:
    source = (
        "# 定理名称\n正文冲突\n"
        "# 变量\nx：实数\n"
        "# 假设\nhx：x > 0\n"
        "# 结论\nx + 1 > 0\n"
        "# 证明\n"
        "对任意实数 x，如果 x > 0，那么 x < 0。\n"
    )
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "ambiguous"
    assert "STRUCTURED_BODY_CONFLICT" in {
        item.code for item in [*result.warnings, *result.ir.ambiguities]
    }


def test_structured_body_conflict_includes_variable_types_and_assumptions() -> None:
    source = (
        "# 定理名称\n类型正文冲突\n"
        "# 变量\nx：自然数\n"
        "# 结论\nx = x\n"
        "# 证明\n"
        "对任意实数 x，如果 x > 0，那么 x = x。\n"
    )
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "ambiguous"
    conflict = next(
        item for item in result.ir.ambiguities if item.code == "STRUCTURED_BODY_CONFLICT"
    )
    assert set(conflict.details["fields"]) == {"variables", "assumptions"}
