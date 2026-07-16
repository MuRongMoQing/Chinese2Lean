# Chinese2Lean 独立 Web Backend

本目录提供独立 FastAPI 服务入口，并复用 Chinese2Lean 的共享应用服务和数学核心；后端不重新实现中文解析、IR、Lean 生成或验证逻辑。Lean Kernel 仍是数学正确性的唯一可信来源。

在仓库根目录安装 API 依赖后启动：

```powershell
python -m pip install -e ".[dev,api]"
python -m backend
```

监听地址只读取 `config/config.yaml` 的 `server.host` 和 `server.port`。默认地址为 `http://127.0.0.1:8000`。

当前 HTTP API 范围：

- `GET /api/health`：健康检查和应用版本；
- `GET /api/version`：Chinese2Lean、Core、Web、Lean、Mathlib、词典和 IR Schema 版本；
- `POST /api/convert`：把受控中文输入转换为 IR 和 Lean，并可选择执行真实 Lean 验证；
- `POST /api/verify`：使用锁定工具链验证 Lean 源码。
- `GET /api/history` 与 `GET /api/history/{id}`：读取本地单用户的工作会话（转换历史）列表和详情；
- `POST /api/upload`：安全保存有大小限制的 UTF-8 `.md`/`.txt` 中文输入，不执行上传内容；
- `GET /api/history/{id}/download/{kind}`：从历史记录下载 `.lean`、`.ir.json` 或 `.report.json`。

本阶段入口只启动后端，不包含 Web 前端、浏览器自动打开、服务器配置修改、域名/HTTPS 配置或生产部署。当前服务默认绑定回环地址，历史记录按本地单用户语义提供，不是公共多用户 Session，也不包含身份认证和多用户隔离。CORS 只限制配置中的前端来源，不能替代认证。公共部署、反向代理和多用户安全边界属于后续部署阶段，必须由用户确认和配置。
