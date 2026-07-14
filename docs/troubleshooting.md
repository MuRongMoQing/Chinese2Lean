# 故障排查

- LAKE_NOT_FOUND / WORKSPACE_MISSING：从仓库根目录运行，确认 Elan 已安装及 lakefile.toml 存在。
- Elan 尝试联网：先安装 lean-toolchain 指定版本；验证器会优先使用本地固定 toolchain。
- UNDECLARED_VARIABLE / INVALID_*：补充变量类型，按受控中文模板拆句并明确括号。
- CONFLICTING_VARIABLE_TYPES / MIXED_NUMERIC_TYPES：统一数域，不要依赖偶然 coercion。
- NAT_SUBTRACTION_AMBIGUOUS：确认是否确实需要截断减法，否则改用 Int/Rat/Real。
- DIVISION_SEMANTICS_AMBIGUOUS：明确整除或域除法类型。
- STRUCTURED_FIELD_CONFLICT：删除冲突字段，保留唯一结论。
- VERIFICATION_FAILED：查看 .report.json 的 raw_message、策略和 repair_attempts。
- STATEMENT_CHANGED：修复被安全机制拒绝；不得关闭检查或添加 sorry。
- Mathlib 变更：核对 lean-toolchain、lakefile.toml、lake-manifest.json 和词典 manifest，
  然后重新运行完整 pytest、Ruff、mypy 与 verify-all。

