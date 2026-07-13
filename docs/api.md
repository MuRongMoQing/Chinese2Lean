# HTTP API

安装 `.[api]` 后运行 `uvicorn chinese2lean.api.app:app`。端点包括 `POST /parse`、
`POST /convert`、`POST /verify`、`GET /terminology/search?q=任意` 和 `GET /health`。
文本请求上限为 1,000,000 字符。`/convert` 返回状态、Lean 代码、是否已验证、IR、诊断、
警告与术语映射。HTTP 成功仅表示请求被处理，应检查响应中的 `status` 和 `verified`。

