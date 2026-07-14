# 类型系统

Chinese2Lean 第一阶段要求所有自由变量显式声明为 Nat、Int、Rat 或 Real，对应 Lean
的 ℕ、ℤ、ℚ、ℝ。数字字面量不单独猜类型，而是从所在运算或比较的已声明变量继承
类型；无法获得上下文时应报告歧义。

## 特殊语义

- Nat 减法是截断减法，例如 3 - 5 = 0。出现自然数减法时返回
  NAT_SUBTRACTION_AMBIGUOUS，要求用户确认语义。
- Nat 和 Int 的 / 不是域除法，分别具有整除语义。此时返回
  DIVISION_SEMANTICS_AMBIGUOUS；Rat 与 Real 才按域除法处理。
- 两侧数域不同会返回 MIXED_NUMERIC_TYPES。当前阶段不猜测 coercion；用户必须统一变量
  类型。后续若支持显式转换，转换节点必须进入 IR。
- 同名变量的类型冲突是 CONFLICTING_VARIABLE_TYPES，属于 IR 无效，不能继续生成 Lean。

Expr.inferred_type 保存推断结果；量词节点用 binder_type 保存绑定变量类型。关系和逻辑
表达式的结果类型为 Prop。
