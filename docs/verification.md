# Lean 验证与诊断

验证器从 lean-toolchain 定位固定工具链，实际执行参数列表 [lake, env, lean, Generated.lean]，
shell=False。源码写入自动清理的临时目录；进程固定 cwd、超时、输入大小和 .lean 后缀，
捕获 stdout、stderr、退出码、命令、锁定环境标志及毫秒耗时。

诊断保留 file、line、column、severity、message 和 raw_message，并归类
UNKNOWN_IDENTIFIER、UNKNOWN_TACTIC、TYPE_MISMATCH、APPLICATION_TYPE_MISMATCH、
UNSOLVED_GOALS、FAILED_TO_SYNTHESIZE、AMBIGUOUS_TERM、PARSER_ERROR、MISSING_IMPORT、
TIMEOUT、FORBIDDEN_CONSTRUCT、STATEMENT_CHANGED 等稳定代码。

只有 IR 有效、token 扫描通过、statement 未变化、锁定环境返回 0、无超时和未完成目标时
状态才是 verified。generated 不是成功。批量命令 chinese2lean verify-all
examples/generated 会逐文件报告路径、耗时和诊断，任一失败返回非零。

