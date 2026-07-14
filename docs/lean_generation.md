# Lean 代码生成

渲染器只接受 IR。类型映射为 Nat→ℕ、Int→ℤ、Rat→ℚ、Real→ℝ；变量、假设和 binder 顺序
保持稳定，默认明确 import Mathlib。表达式 renderer 根据 AST 和优先级添加括号，量词使用
binder_type，绝不重新解释中文。

证明策略按形状依次考虑 rfl、exact/合取投影、确定性存在见证、全称引入、simp、norm_num、
ring、linarith、positivity、omega 和 aesop。报告记录 selected_strategy、reason 和
alternatives_tried，不对所有目标使用单一 tactic，也不为测试输入硬编码完整源码。

常用中文定理名映射为可读稳定英文名；保留字添加后缀，重复名称添加稳定编号。只有无法安全
转写且没有登记映射时才使用稳定短哈希兜底。name_mappings 写入 IR 和 report。当前默认
Mathlib，未来可在不改变 IR/statement 的情况下优化最小 import。

report 的 lean_line_mappings 将变量、假设、结论和证明步骤的来源文本位置映射到生成的 Lean 行。

