# 测试与验收

测试按规范化、词典、解析、IR/类型、渲染、诊断、安全扫描、命题不变性、CLI 和真实 Lean
端到端分层。回归修复必须先增加能失败的公共行为测试，再实现最小修复。

    pytest
    ruff check .
    mypy src
    lake env lean --version
    chinese2lean verify-all examples/generated

tests/test_e2e_lean.py 读取 examples/chinese/ 中不少于 20 个中文案例，检查生成产物与
确定性 renderer 一致，并对每个案例真实调用锁定环境中的 lake env lean。测试不得
monkeypatch 这些端到端 subprocess。tests/test_failure_cases.py 覆盖不少于 10 个失败或
歧义输入，并断言稳定错误码。

批量结果包含总数、通过数、失败数、每个文件的路径、耗时和诊断。任一文件失败或目录为空，
verify-all 都不会报告成功。
