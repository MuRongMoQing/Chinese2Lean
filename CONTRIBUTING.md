# 贡献指南

使用 Python 3.12+，安装开发环境：

    python -m pip install -e ".[dev,api]"
    lake update

开发采用公共接口上的红—绿测试。每个语法功能必须同步修改术语词典、解析/IR 测试、Lean
渲染测试和中文文档；每个缺陷修复必须有回归测试。端到端测试不得模拟 Lean 成功。

提交前运行：

    pytest
    ruff check .
    mypy src
    chinese2lean verify-all examples/generated
    lake env lean examples/generated/positive_add_one.lean

禁止提交 sorry、admit、新 axiom、unsafe 逃逸、被削弱的结论或新增等价假设。修复代码必须
保持 statement 哈希，最多尝试三次。新增词条须有稳定 ID、上下文、正例、反例及版本兼容性。
提交应是一个可独立验证的纵向切片。

