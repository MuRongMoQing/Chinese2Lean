# Chinese2Lean 桌面应用

桌面界面通过仅绑定 `127.0.0.1` 的本地 API 服务复用 Chinese2Lean Core，不在 GUI 中实现数学解析或证明逻辑。

从仓库根目录启动：

```powershell
& .\.venv\Scripts\python.exe -m desktop
```

## 首次启动初始化

桌面程序会先检查用户可写目录中的运行环境。尚未就绪时，程序显示“Chinese2Lean 初始化”界面，并依次执行：

1. 检查系统环境；
2. 准备运行环境；
3. 配置 Lean；
4. 配置 Mathlib；
5. 验证编译环境；
6. 初始化完成。

界面提供进度、日志、错误提示、重试、取消和恢复。初始化工作在后台线程执行；只有锁定的 Lean 和 Mathlib 环境真实验证成功后，才会启动本地 API 并进入主窗口。运行状态、环境、历史和日志写入当前用户的应用数据目录，不写入程序安装目录。

环境版本只读取仓库中的 `lean-toolchain`、`lakefile.toml` 和 `lake-manifest.json`。初始化器不会安装 `latest`、`stable`、`beta` 或 `nightly` 工具链，也不会执行用户输入或未知脚本。若系统没有可复用的 Elan，必须由后续打包阶段提供经过固定 SHA256 校验的 Elan 安装资产；缺少该资产时会明确报错，不会降级到未锁定环境。

打包阶段提供资产时，入口只读取固定的 `runtime/elan-bootstrap.json` 清单及同目录平台安装器；清单必须声明 schema 版本、目标平台、固定文件名和 SHA256，路径越界、平台不符或哈希不符都会被拒绝。

## 主窗口

主窗口支持中文 Markdown/文本输入、文件打开、示例加载、语义与 IR 查看、Lean 代码复制和保存、真实 Lean Kernel 验证、三类结果导出及历史查看。IR 树可以展开或折叠；Lean 视图为只读，防止验证结果与原中文命题或 IR 脱离。导出包含 `.lean`、`.ir.json` 和 `.report.json`。

## 当前交付边界

本阶段实现的是源码运行时的首次启动初始化和桌面生命周期门控。阶段 9 的独立可执行文件、内置 Python runtime、Elan 安装资产以及 Windows/Linux/macOS 打包尚未交付，因此当前不能宣称普通用户无需 Python 或 Elan 即可直接运行，也不能宣称 `Chinese2Lean.exe` 已经生成。
