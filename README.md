# Chinese2Lean

Chinese2Lean 将**受控中文**数学命题和证明转换成 Lean 4 + Mathlib 代码，并调用本地
Lean 编译器验证结果。它不声称理解任意自然语言证明；解析器只接受文档明确规定的结构化
格式和有限自然句式。解析成功、代码生成成功和 Lean 验证成功是三个不同状态。

## 安装与快速开始

需要 Python 3.12+ 与通过 Elan 安装的 Lean 4：

```bash
python -m pip install -e ".[dev,api]"
lake update
chinese2lean convert examples/positive_add_one.md --output Result.lean
pytest
ruff check .
mypy src
lake env lean examples/generated/positive_add_one.lean
```

项目通过 `lean-toolchain` 固定 Lean，通过 `lakefile.toml` 固定兼容的 Mathlib。推荐输入：

```markdown
# 定理名称
正数加一仍为正
# 变量
x：实数
# 假设
h1：x > 0
# 结论
x + 1 > 0
# 证明
1. 已知 x > 0。
2. 因此 x + 1 > 0。
```

当前可靠支持 ℕ、ℤ、ℚ、ℝ 上的基础算术、比较、简单逻辑与一元函数应用表达式。
集合关系符号已进入表达式层和术语词典，但集合类型声明、显式 `∀/∃` 结论、测度论、
泛函分析、范畴论和高度抽象代数结构仍不属于第一阶段可靠子集。

生成 Lean 文本不代表证明成功：只有 Lean 返回 0 且代码不含逃逸项时才是 `verified`。
禁止 `sorry`、`admit`、额外 `axiom` 和 `unsafe`，因为它们会伪装证明成功。

