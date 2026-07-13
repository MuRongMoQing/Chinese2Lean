# 贡献指南

使用 Python 3.12+。安装 `python -m pip install -e ".[dev,api]"`，提交前运行：

```bash
pytest
ruff check .
mypy src
lake env lean examples/generated/positive_add_one.lean
```

功能开发采用公共 seam 上的红绿测试：先增加一个用户可观察行为的失败测试，再写最小实现。
不要测试私有实现细节。新增语法必须同步文档、术语词典、IR/Lean 示例和歧义行为。任何绕过
证明的构造、削弱结论或添加等价假设的变更都会被拒绝。提交信息应说明一个完整纵向切片。

