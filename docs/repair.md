# 安全修复

自动修复位于首次真实 Lean 编译之后，最多执行三次。它只接受结构化诊断类别：缺少 Mathlib
环境时可补充显式 import，证明策略不适用时按固定顺序尝试小范围 tactic 替换。当前不自动
修改 coercion 或 theorem statement，也不会重新解释中文、增加假设或削弱结论。

每次尝试记录序号、诊断类别、前后代码、修改摘要、前后 statement SHA-256 和验证结果。
修复前后会提取变量、binder、假设和结论组成的 Lean 声明规范形；只有 proof body、import
及无语义格式可以变化。哈希不一致时立即返回 STATEMENT_CHANGED。

生成和修复代码都会经过 token 级禁止项扫描。sorry、admit、axiom、unsafe 作为
Lean token 时被拒绝；注释、字符串和较长标识符中的相同字符不会误报。by_contra 与
classical 本身不禁止，但不得借此引入等价公理。
