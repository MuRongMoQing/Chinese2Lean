# 架构

流水线为 `规范化 → 解析 → IR 校验 → Lean 渲染 → 隔离验证 → 有限修复`。每层只依赖前一层
的稳定数据结构。规范化输出保留原词、标准词、词条 ID 与位置；解析器优先读取 Markdown
章节，有限自然句式只作为次级入口。核心流程完全离线。

状态机为 `parse_failed | ambiguous | generated | verification_failed | verified`。只有 Lean
退出码为 0 且代码通过禁用项扫描，才能进入 `verified`。本地定理检索使用关键词、类型和
结论形状；可选 LLM 位于确定性修复之后，并且候选仍必须通过同一安全扫描和 Lean 编译。

