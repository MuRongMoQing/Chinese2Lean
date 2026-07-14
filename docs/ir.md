# 中间表示

TheoremIR 的 schema_version 当前为 1。主要字段是 theorem_name、variables、assumptions、
conclusion、proof_steps、imports、warnings、ambiguities 和 name_mappings。

SourceSpan 保存句子序号、起止位置和原文；VariableDecl 保存来源名、Lean 名、明确类型和
binder_kind；Expr 用 kind、operator、value、args 表示完整树，并保存 inferred_type、
binder_type 和来源位置；Assumption 与 ProofStep 保留命题和证明来源。IR 不包含 Lean 文本
模板，也不调用 Lean。

IR 可由 model_dump_json 序列化，并由 TheoremIR.model_validate_json 反序列化。未声明变量、
非法名称、冲突类型或无效表达式会阻止渲染。量词、关系、逻辑和算术均是结构节点，不把整段
表达式保存为未经解析的字符串。

