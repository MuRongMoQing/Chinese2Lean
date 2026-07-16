from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

from fastapi.testclient import TestClient

import chinese2lean.application as application
from backend.app import create_backend_app
from chinese2lean.application import ProductRuntime, build_product_runtime, composition
from chinese2lean.application.models import ConvertResponse
from desktop.local_api import LocalApiClient, LocalApiServer

ROOT = Path(__file__).parents[1]
DELIVERY_ROOTS = (
    ROOT / "desktop",
    ROOT / "backend",
    ROOT / "src" / "chinese2lean" / "api",
)
ALLOWED_NON_CONVERSION_IMPORTS = {
    Path("src/chinese2lean/api/app.py"): frozenset(
        {"chinese2lean.normalization.terminology"}
    )
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def _is_module_or_child(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


@contextmanager
def _shared_surfaces(
    temporary_root: Path,
) -> Iterator[tuple[LocalApiClient, LocalApiServer, TestClient, ProductRuntime]]:
    runtime = build_product_runtime(
        ROOT,
        storage_root=temporary_root / "storage",
        log_root=temporary_root / "logs",
    )
    desktop_server = LocalApiServer(runtime)
    try:
        desktop_server.start()
        with TestClient(create_backend_app(runtime)) as web_client:
            yield (
                LocalApiClient(desktop_server.base_url),
                desktop_server,
                web_client,
                runtime,
            )
    finally:
        desktop_server.stop()
        for logger in runtime.loggers.values():
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)


def test_delivery_adapters_use_the_public_shared_application_boundary() -> None:
    assert application.ProductRuntime is composition.ProductRuntime
    assert application.build_product_runtime is composition.build_product_runtime

    private_composition_imports: list[str] = []
    for delivery_root in DELIVERY_ROOTS:
        for path in delivery_root.rglob("*.py"):
            if "chinese2lean.application.composition" in _imported_modules(path):
                private_composition_imports.append(str(path.relative_to(ROOT)))

    assert private_composition_imports == []


def test_delivery_adapters_do_not_import_math_core_internals() -> None:
    forbidden_prefixes = tuple(
        f"chinese2lean.{name}"
        for name in (
            "ir",
            "lean",
            "normalization",
            "parser",
            "pipeline",
            "repair",
            "verification",
        )
    )
    violations: list[str] = []
    for delivery_root in DELIVERY_ROOTS:
        for path in delivery_root.rglob("*.py"):
            relative_path = path.relative_to(ROOT)
            allowed = ALLOWED_NON_CONVERSION_IMPORTS.get(relative_path, frozenset())
            for module in _imported_modules(path):
                if _is_module_or_child(module, forbidden_prefixes) and module not in allowed:
                    violations.append(f"{relative_path}:{module}")

    assert violations == []


def test_desktop_and_web_share_the_complete_verified_core_result(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "chinese" / "positive_add_one.md").read_text(
        encoding="utf-8"
    )

    with _shared_surfaces(tmp_path) as (desktop, _server, web, runtime):
        desktop_result = desktop.convert(source, verify=True)
        web_response = web.post("/api/convert", json={"text": source, "verify": True})
        web_result = ConvertResponse.model_validate(web_response.json())

        assert web_response.status_code == 200
        assert desktop_result.model_dump(mode="json") == web_result.model_dump(mode="json")
        assert web_result.status == "VERIFIED"
        assert web_result.verified is True
        assert web_result.lean.startswith("import Mathlib")
        assert web_result.ir["theorem_name"] == "positive_add_one"
        assert web_result.source_text == source
        assert web_result.normalized_text
        assert web_result.statement_hash
        assert web_result.lean_line_mappings
        assert web_result.versions["lean_version"] == "4.19.0"
        assert web_result.versions["mathlib_revision"] == (
            "c44e0c8ee63ca166450922a373c7409c5d26b00b"
        )

        history = runtime.history.list()
        assert len(history) == 2
        assert all(record.output == web_result.model_dump(mode="json") for record in history)


def test_desktop_and_web_share_stable_ambiguity_without_guessing(tmp_path: Path) -> None:
    source = """# 定理名称
自然数减法
# 变量
n：自然数
# 结论
n - 1 <= n
"""

    with _shared_surfaces(tmp_path) as (desktop, _server, web, _runtime):
        desktop_result = desktop.convert(source, verify=True)
        web_response = web.post("/api/convert", json={"text": source, "verify": True})
        web_result = ConvertResponse.model_validate(web_response.json())

        assert web_response.status_code == 200
        assert desktop_result.model_dump(mode="json") == web_result.model_dump(mode="json")
        assert web_result.status == "AMBIGUOUS"
        assert web_result.verified is False
        assert web_result.lean == ""
        ambiguity_codes = {
            str(item.get("code"))
            for item in web_result.ir.get("ambiguities", [])
            if isinstance(item, dict)
        }
        assert ambiguity_codes == {"NAT_SUBTRACTION_AMBIGUOUS"}


def test_desktop_and_web_share_health_and_locked_versions(tmp_path: Path) -> None:
    with _shared_surfaces(tmp_path) as (_desktop, server, web, _runtime):
        with urlopen(f"{server.base_url}/api/health", timeout=5) as response:
            desktop_health = json.load(response)
        with urlopen(f"{server.base_url}/api/version", timeout=5) as response:
            desktop_version = json.load(response)

        web_health = web.get("/api/health")
        web_version = web.get("/api/version")

        assert web_health.status_code == 200
        assert web_health.json() == desktop_health == {"status": "ok", "version": "0.1.0"}
        assert web_version.status_code == 200
        assert web_version.json() == desktop_version
        assert desktop_version["core_version"] == "0.1.0"
        assert desktop_version["lean_version"] == "4.19.0"
        assert desktop_version["mathlib_revision"] == (
            "c44e0c8ee63ca166450922a373c7409c5d26b00b"
        )
