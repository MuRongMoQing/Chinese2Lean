# Chinese2Lean Web 前端

本目录提供阶段 6 的 Vue 3 + TypeScript 本地 Web 界面。前端只负责采集输入、调用产品后端并展示结果，不包含中文数学解析、Lean 生成或验证逻辑。

## 本地启动

先在项目根目录启动后端：

```powershell
& .\.venv\Scripts\python.exe -m backend
```

再在本目录启动开发服务器：

```powershell
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。开发服务器将 `/api/*` 请求转发到 `http://127.0.0.1:8000`；主机和端口与项目受控配置保持一致。

## 界面范围

- 首页说明产品用途、使用步骤、当前版本和受控中文数学范围；
- 编辑器接受 Markdown 或受控中文数学文本，支持内置示例和 `.md`、`.txt` 文件；
- 结果区分别展示解析、IR、Lean、验证和日志；
- 历史区展示本机单用户的输入、时间、状态和输出；
- 结果可下载为 `.lean`、`.ir.json` 和 `.report.json`。

文件上传与历史数据由后端按安全边界处理。浏览器端的扩展名检查只是即时反馈，不能替代后端校验。

## 检查

```powershell
npm test
npm run typecheck
npm run build
```

依赖在 `package.json` 和 `package-lock.json` 中使用精确版本锁定。生产部署、鉴权、多用户隔离和公网暴露不属于本阶段范围。
