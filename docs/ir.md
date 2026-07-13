# 中间表示

IR 使用 Pydantic 建模，包括来源位置、变量、表达式树、假设、证明步骤、导入、警告、
歧义与名称映射。`Expr` 的 `kind/operator/value/args` 表示语法树，因此优先级信息不会在
规范化时丢失。CLI 的 `parse` 命令输出可编辑 JSON；人工修正后可用 `TheoremIR` 的
Pydantic 校验重新载入。警告包含稳定代码和可选来源位置。

