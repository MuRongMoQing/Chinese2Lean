# Lean 验证与修复

验证器以 `subprocess.run(["lake", "env", "lean", path], shell=False)` 调用本地 Lean，
固定超时并捕获标准输出、标准错误、退出码、文件、行列和严重级别。生成文件位于系统临时
目录，进程工作目录固定为项目 Lean 工作区，用户文本不会进入 shell 命令。

修复最多三次，每次保存修复前代码、诊断、修改说明、修复后代码和结果。当前确定性修复
只轮换适合基础代数的受控 tactic。任何 `sorry`、`admit`、`axiom` 或 `unsafe`（注释除外）
都会在启动 Lean 前被拒绝。生成成功不等于验证成功。

