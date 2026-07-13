# Chinese2Lean 第一阶段设计

Chinese2Lean 是一个确定性优先的受控中文编译流水线。输入依次经过可追踪规范化、
结构化/受控句式解析、Pydantic IR、Lean 渲染、隔离编译和有限修复。核心流水线不依赖
远程模型；LLM 只保留为可选、显式启用且位于确定性修复之后的扩展点。

关键边界是 `Normalizer`、`StatementParser`、`TheoremIR`、`LeanRenderer`、
`LeanRunner` 和 `Converter`。解析成功、生成成功、验证成功是彼此独立的状态。
未声明变量、缺失类型和无法唯一解释的词不会被猜测，而是进入 `warnings`/`ambiguities`。

验证器仅以参数数组调用 `lake env lean`，在临时目录写入固定文件名，限制输入大小和超时，
并在启动 Lean 前拒绝 `sorry`、`admit`、`axiom`、`unsafe` 等逃逸构造。

