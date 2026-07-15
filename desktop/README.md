# Chinese2Lean 桌面应用

当前桌面界面通过仅绑定 `127.0.0.1` 的本地 API 服务复用 Chinese2Lean Core，不在 GUI 中实现数学解析或证明逻辑。

从仓库根目录启动：

```powershell
& .\.venv\Scripts\python.exe -m desktop
```

界面支持中文 Markdown/文本输入、文件打开、示例加载、语义与 IR 查看、Lean 代码复制和保存、真实 Lean Kernel 验证、三类结果导出及历史查看。IR 树可以展开或折叠；Lean 视图为只读，防止验证结果与原中文命题或 IR 脱离；VERIFIED 历史保留中文、IR、Lean、命题哈希和诊断的完整追踪；导出包含 `.lean`、`.ir.json` 和 `.report.json`。

本阶段只实现桌面 GUI。第一次启动环境初始化、独立可执行文件和平台打包属于后续开发阶段，当前不得描述为已经完成。
