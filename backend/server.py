from __future__ import annotations

from pathlib import Path

import uvicorn

from backend.app import PROJECT_ROOT, create_backend_app
from chinese2lean.product.config import load_product_config


def run(project_root: Path = PROJECT_ROOT) -> None:
    """Run the independent HTTP backend using the product listener configuration."""

    root = project_root.resolve()
    config = load_product_config(root / "config" / "config.yaml")
    uvicorn.run(
        create_backend_app(project_root=root),
        host=config.server.host,
        port=config.server.port,
        log_level="info",
        access_log=True,
    )
