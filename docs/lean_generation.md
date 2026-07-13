# Lean 代码生成

类型映射为 `Nat→ℕ`、`Int→ℤ`、`Rat→ℚ`、`Real→ℝ`。渲染器按表达式优先级添加必要括号，
稳定分配变量和假设名称，并默认导入 `Mathlib`。证明策略根据命题形状从直接定理、`rfl`、
`simp`、`norm_num`、`ring_nf`、`linarith`、`nlinarith`、`positivity`、`omega`、`aesop`
中选择；并不对所有命题盲目使用同一 tactic。

名称映射写入 IR。Lean 保留字会添加后缀，冲突使用稳定编号，无法安全转写的中文名称使用
输入哈希，因此同一输入可重复生成相同名称。

