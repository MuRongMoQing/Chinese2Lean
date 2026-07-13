# 故障排查

- `LAKE_NOT_FOUND`：确认 Elan 的 bin 目录在 PATH。
- `no default toolchain`：在项目根目录执行 `elan toolchain install`，项目会读取
  `lean-toolchain`。
- `WORKSPACE_MISSING`：从项目根目录运行 CLI，或确保 `lean_workspace/` 存在。
- `UNDECLARED_VARIABLE`：在“变量”章节声明每个标识符及类型。
- `INVALID_*`：对照受控中文文档拆分复杂句子并明确括号。
- `VERIFICATION_FAILED`：查看 `.conversion.json` 中的诊断与修复历史，不要添加 `sorry`。
- Mathlib 更新后失败：运行 `lake update`，核对 Lean/Mathlib 版本，并重新运行全部测试。

