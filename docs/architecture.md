# 架构

主流水线为：中文原文 → 可追踪规范化 → 受控解析 → IR/类型校验 → Lean 渲染 → 禁止项扫描
→ 锁定环境编译 → 结构化诊断 → 最多三次安全修复 → 统一结果。

normalization 只处理符号、术语和来源映射；parser 只构造语义树；ir 定义可序列化模型和类型
规则；lean 只读取 IR 并返回代码及证明策略；verification 执行 Lake、诊断、安全扫描和
statement 检查；pipeline 负责状态机。LLM 与 retrieval 不是基础流程依赖。

状态包括 normalization_failed、parse_failed、ambiguous、ir_invalid、generated、
verification_failed、verified。只有锁定 Lake 返回 0、没有超时/未完成目标/禁止 token，
且 statement 哈希未变化时才进入 verified。每个失败阶段保留此前得到的原文、规范化文本、
术语映射、IR、代码和诊断。

