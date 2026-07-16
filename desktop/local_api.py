from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn

from chinese2lean.api.app import create_app
from chinese2lean.application import ProductRuntime
from chinese2lean.application.models import ConvertResponse, VerifyResponse


class LocalApiServer:
    """Loopback-only embedded FastAPI server used by the desktop application."""

    def __init__(self, runtime: ProductRuntime, *, startup_timeout: float = 10.0) -> None:
        self._runtime = runtime
        self._startup_timeout = startup_timeout
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._port: int | None = None

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise RuntimeError("本地 API 服务尚未启动。")
        return f"http://127.0.0.1:{self._port}"

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("本地 API 服务已经启动。")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        address = cast(tuple[str, int], listener.getsockname())
        self._port = address[1]
        self._socket = listener
        config = uvicorn.Config(
            create_app(self._runtime),
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            kwargs={"sockets": [listener]},
            name="chinese2lean-local-api",
            daemon=True,
        )
        self._thread.start()
        deadline = time.monotonic() + self._startup_timeout
        while not self._server.started and self._thread.is_alive():
            if time.monotonic() >= deadline:
                self.stop()
                raise TimeoutError("本地 API 服务启动超时。")
            time.sleep(0.01)
        if not self._server.started:
            self.stop()
            raise RuntimeError("本地 API 服务启动失败。")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._socket is not None:
            self._socket.close()
        self._server = None
        self._thread = None
        self._socket = None
        self._port = None


class LocalApiClient:
    """Small standard-library HTTP client for the four local product routes."""

    records_conversion_history = True

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 130.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def convert(self, text: str, *, verify: bool = True) -> ConvertResponse:
        payload = self._request("/api/convert", {"text": text, "verify": verify})
        return ConvertResponse.model_validate(payload)

    def verify(self, lean_code: str) -> VerifyResponse:
        payload = self._request("/api/verify", {"lean_code": lean_code})
        return VerifyResponse.model_validate(payload)

    def _request(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        request = Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            raw_error = error.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw_error).get("detail", raw_error)
            except json.JSONDecodeError:
                detail = raw_error
            raise ValueError(f"本地 API 请求失败：{detail}") from error
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("本地 API 返回了无效 JSON 对象。")
        return decoded
