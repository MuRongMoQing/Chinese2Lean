from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from chinese2lean.application.service import Chinese2LeanService
from chinese2lean.normalization.terminology import Terminology
from chinese2lean.pipeline.converter import Converter
from chinese2lean.product.config import ProductConfig, load_product_config
from chinese2lean.product.logging import configure_product_logging
from chinese2lean.storage import HistoryStore
from chinese2lean.verification.runner import LeanRunner
from chinese2lean.versioning import read_versions


class PinnedVersionProvider:
    """Read the public product version contract from repository lock files."""

    def __init__(self, project_root: Path, *, dictionary_version: str) -> None:
        self._project_root = project_root.resolve()
        self._dictionary_version = dictionary_version

    def get_versions(self) -> dict[str, str]:
        versions = read_versions(
            self._project_root,
            dictionary_version=self._dictionary_version,
            ir_schema_version=1,
        )
        keys = (
            "chinese2lean_version",
            "core_version",
            "desktop_version",
            "web_version",
            "lean_version",
            "mathlib_revision",
            "dictionary_version",
            "ir_schema_version",
        )
        return {key: versions[key] for key in keys}


@dataclass(frozen=True, slots=True)
class ProductRuntime:
    """Default composition shared by desktop and HTTP delivery adapters."""

    config: ProductConfig
    service: Chinese2LeanService
    history: HistoryStore
    loggers: dict[str, logging.Logger]


def build_product_runtime(
    project_root: Path,
    *,
    storage_root: Path | None = None,
    log_root: Path | None = None,
) -> ProductRuntime:
    root = project_root.resolve()
    config = load_product_config(root / "config" / "config.yaml")
    terminology = Terminology.load(root / "terminology")
    resolved_storage = (
        storage_root.resolve()
        if storage_root is not None
        else (root / config.storage.path).resolve()
    )
    resolved_logs = log_root.resolve() if log_root is not None else (root / "logs").resolve()
    loggers = configure_product_logging(resolved_logs)
    history = HistoryStore(
        resolved_storage / "history.sqlite3",
        resolved_storage / "artifacts",
    )
    service = Chinese2LeanService(
        Converter.default(root),
        LeanRunner(root),
        PinnedVersionProvider(root, dictionary_version=terminology.version),
    )
    loggers["startup"].info("Chinese2Lean product runtime initialized")
    return ProductRuntime(config=config, service=service, history=history, loggers=loggers)
