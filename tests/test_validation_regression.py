from pathlib import Path

from chinese2lean.pipeline.converter import Converter

ROOT = Path(__file__).parents[1]


def test_undeclared_variable_in_assumption_is_rejected() -> None:
    source = """# 定理名称
假设含未声明变量
# 变量
x：实数
# 假设
y > 0
# 结论
x > 0
"""
    result = Converter.default(ROOT).convert_text(source, verify=False)
    assert result.status.value == "parse_failed"
    assert any(item.code == "UNDECLARED_VARIABLE" for item in result.warnings)
