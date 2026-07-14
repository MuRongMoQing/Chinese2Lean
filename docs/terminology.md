# 术语词典

terminology/manifest.yaml 记录 dictionary_version、schema_version、lean_version 和精确
mathlib_revision。当前词典版本为 0.1.0，schema 为 1。

每个条目应包含 id、version、canonical_zh、aliases、semantic_kind、lean_template 或
lean_symbol、argument_count、precedence、associativity、supported_types、contexts、
examples、counterexamples 和 notes。正例说明规范化/Lean 表示；反例说明无效或歧义上下文。

加载器检测重复 ID、条目内重复别名、跨条目别名冲突、循环别名及不兼容 schema。规范化候选
先按最长词、再按词条优先级、最后按别名字典序排列，因此文件加载顺序不是语义规则。相同
别名属于多个词条时会在加载期作为冲突拒绝，不会随机选择。当前上下文规则明确支持
quantifier_prefix；其余逻辑上下文由结构化解析器确认。“有一个”只有位于明确数域类型前缀
前才解释为存在，普通数量描述不会全局替换。

扩展时新增 YAML 文件并保持 manifest schema，运行：

    chinese2lean terminology check
    chinese2lean terminology lookup "任意"
    pytest tests/test_phase1_contracts.py

版本不兼容时升级 manifest 和迁移文档，不得静默混用。

