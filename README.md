# Chinese2Lean

Chinese2Lean 将受控中文数学命题转换为结构化 IR、确定性 Lean 4 + Mathlib 源码，并由真实
Lean 编译器验证。项目不承诺理解任意自然语言证明；自由散文、隐式变量和高等数学自动证明
不在第一阶段可靠范围内。本项目由 AI 辅助生成并经过自动化测试与 Lean 编译验收。

## 环境与安装

Windows 新设备的可重复引导方式见 [开发环境引导](docs/development_setup.md)。

需要 Python 3.12+、Elan 和仓库锁定的 Lean/Mathlib：

    elan toolchain install leanprover/lean4:v4.19.0
    python -m pip install -e ".[dev,api]"
    lake update
    chinese2lean version

Elan 安装锁定的 Lean；lake update 按 lakefile.toml 与 lake-manifest.json 获取 Mathlib 依赖。

lean-toolchain 固定 Lean 4.19.0，lakefile.toml 固定 Mathlib v4.19.0，
lake-manifest.json 固定精确提交，terminology/manifest.yaml 固定词典 schema 和版本。

## 使用

推荐输入位于 examples/chinese/，包含“定理名称、变量、假设、结论、证明”章节。常用命令：

    chinese2lean normalize examples/chinese/positive_add_one.md
    chinese2lean parse examples/chinese/positive_add_one.md --output theorem.json
    chinese2lean convert examples/chinese/positive_add_one.md --output Result.lean
    chinese2lean verify Result.lean
    chinese2lean verify-all examples/generated
    chinese2lean terminology lookup "任意"

convert 生成 Lean、IR JSON、完整 report JSON 和中文摘要。只有状态 VERIFIED 才表示成功；
GENERATED 仅表示生成过源码。验证必须通过禁止项扫描、命题不变性检查和锁定环境中的
lake env lean，且退出码为 0。

## 支持范围

支持 Nat、Int、Rat、Real，∀、∃、→、∧、¬，等式/不等式，以及 +、-、*、/、^ 和括号。
Nat 减法、Nat/Int 除法、混合数域和不清晰量词会报告歧义，不会静默猜测。20 个真实编译
示例位于 examples/generated/。

详细规则见 docs/controlled_chinese.md、docs/type_system.md、docs/terminology.md、
docs/verification.md、docs/repair.md、docs/testing.md 和 docs/limitations.md。

