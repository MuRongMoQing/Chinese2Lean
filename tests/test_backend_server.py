from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from urllib.request import urlopen

import pytest
import uvicorn

from backend import server as backend_server
from backend.app import create_backend_app
from chinese2lean.application.composition import build_product_runtime

ROOT = Path(__file__).parents[1]


def test_run_starts_the_backend_on_the_configured_listener(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = object()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        backend_server,
        "load_product_config",
        lambda path: SimpleNamespace(
            server=SimpleNamespace(host="127.0.0.7", port=8123),
        ),
    )
    monkeypatch.setattr(
        backend_server,
        "create_backend_app",
        lambda *, project_root: application,
    )

    def fake_run(app: object, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(backend_server.uvicorn, "run", fake_run)

    backend_server.run(tmp_path)

    assert captured == {
        "app": application,
        "host": "127.0.0.7",
        "port": 8123,
        "log_level": "info",
        "access_log": True,
    }


def test_backend_serves_health_and_version_over_loopback(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = cast(tuple[str, int], listener.getsockname())[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_backend_app(
                build_product_runtime(
                    ROOT,
                    storage_root=tmp_path / "storage",
                    log_root=tmp_path / "logs",
                )
            ),
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        name="chinese2lean-backend-smoke",
        daemon=True,
    )
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive():
            if time.monotonic() >= deadline:
                raise TimeoutError("后端服务器启动超时。")
            time.sleep(0.01)
        assert server.started

        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/json"
            assert json.load(response) == {"status": "ok", "version": "0.1.0"}
        with urlopen(f"http://127.0.0.1:{port}/api/version", timeout=5) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/json"
            assert json.load(response)["lean_version"] == "4.19.0"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()

    assert not thread.is_alive()
