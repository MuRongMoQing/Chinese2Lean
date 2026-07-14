# Windows 开发环境引导

`scripts/bootstrap-dev.ps1` 用于在 Windows PowerShell 中克隆或恢复 Chinese2Lean 开发环境。它会验证 Git 状态、创建独立虚拟环境、安装 Python 开发依赖、读取仓库锁定的 Lean 工具链、获取 Mathlib 缓存，并运行完整验收。

## 适用范围

该脚本不是能处理所有项目和所有操作系统的“万能克隆器”。它适用于满足以下条件的 Windows 设备：

- Windows PowerShell 5.1 或 PowerShell 7；
- Git、Python 3.12+、Elan、Lake、curl 和 tar 已加入 `PATH`；
- 仓库使用 `pyproject.toml`、`lean-toolchain` 和 Lake；
- 可以访问 GitHub、Python 包索引和 Mathlib 缓存服务。

Linux 和 macOS 的虚拟环境路径、工具安装方式及 shell 语法不同，应另写 Bash 或跨平台 PowerShell 7 包装层，而不是直接复制 Windows 路径逻辑。

## 在新设备使用

先把脚本下载到临时目录，再运行：

```powershell
$script = Join-Path $env:TEMP 'bootstrap-Chinese2Lean.ps1'
Invoke-WebRequest `
  'https://raw.githubusercontent.com/MuRongMoQing/Chinese2Lean/feat/dev-environment-bootstrap/scripts/bootstrap-dev.ps1' `
  -OutFile $script

powershell -NoProfile -ExecutionPolicy Bypass -File $script `
  -Repository 'https://github.com/MuRongMoQing/Chinese2Lean.git' `
  -Target 'D:\Code\Chinese2Lean' `
  -Branch 'feat/dev-environment-bootstrap'
```

分支合并到 `main` 后，可省略 `-Branch`，并把下载地址中的分支名改为 `main`。

脚本可重复运行。已有且干净的 clone、`.venv` 和 Mathlib 缓存会被复用；远端、分支、可选提交前缀或工作区状态不符合要求时会停止，而不会重置用户改动。

## 常用参数

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `Repository` | Chinese2Lean 的 HTTPS 地址 | 要克隆的远端仓库 |
| `Target` | 当前目录下的 `Chinese2Lean` | 本机目标目录，可使用任意盘符 |
| `Branch` | `main` | 要克隆和验证的分支 |
| `ExpectedCommit` | 空 | 可选 HEAD 前缀校验，适合固定快照 |
| `PythonCommand` | `python` | Python 启动命令或完整路径 |
| `PythonExtras` | `dev,api` | 传给 editable install 的 extras |
| `SmokeLeanFile` | 正数加一示例 | 完整测试前的 Lean 冒烟文件 |
| `CacheAttempts` | `3` | Mathlib 缓存最大尝试次数 |
| `SkipMathlibCache` | 关闭 | 非 Mathlib 项目可显式跳过缓存阶段 |
| `SkipValidation` | 关闭 | 只初始化环境；仍执行 Lean 冒烟编译和差异保护，不宣称完整验收通过 |
| `RepositoryOnly` | 关闭 | 只克隆或安全快进 Git 分支，不安装环境或执行项目验收 |
| `SelfTest` | 关闭 | 不联网检查脚本的本地基础行为 |

例如固定到某个已知提交：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-dev.ps1 `
  -Target 'E:\Projects\Chinese2Lean' `
  -Branch main `
  -ExpectedCommit '3d44e4f'
```

`ExpectedCommit` 只做校验，不会执行破坏性 reset。若要使用其他提交，应选择包含该提交的分支；当前脚本不支持 detached HEAD 或直接克隆 tag。

## 改造成其他项目的脚本

对于结构相近的 Python + Lean 项目，通常只需调整：

1. `Repository`、`Branch` 和目标目录；
2. `PythonExtras`；
3. `SmokeLeanFile`；
4. 脚本末尾的项目专用 pytest、Ruff、mypy 和批量 Lean 命令；
5. 非 Mathlib 项目使用 `SkipMathlibCache`，或替换缓存阶段。

若项目没有 Python、没有 Lake、使用容器或需要数据库/外部服务，就不应只改几个参数；应保留 Git 安全检查和可重入原则，重新实现对应的环境阶段。

## 安全与验收

- 脚本不保存凭据；GitHub 认证由 Git Credential Manager、SSH 或 GitHub CLI 单独管理。
- 仅在 Git 明确报告 ownership 问题时添加目标仓库的精确 `safe.directory`，不使用通配符。
- 不复制其他工作区的 `.venv`、`.lake` 或缓存。
- 不使用 `git reset --hard`、`git clean` 或覆盖已有改动。
- 只有 pytest、Ruff、mypy、Lean 冒烟、批量 Lean 验证、版本报告和 `git diff --exit-code` 全部通过，才显示引导完成。

离线检查脚本本身：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-dev.ps1 -SelfTest
```
