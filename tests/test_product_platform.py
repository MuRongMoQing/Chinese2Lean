from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from chinese2lean.product.config import load_product_config
from chinese2lean.product.logging import LOG_CATEGORIES, configure_product_logging
from chinese2lean.versioning import read_versions

ROOT = Path(__file__).parents[1]


def test_product_config_loads_only_product_runtime_settings() -> None:
    config = load_product_config(ROOT / "config" / "config.yaml")

    assert config.application.version == "0.1.0"
    assert config.lean.version == "4.19.0"
    assert config.lean.toolchain == "leanprover/lean4:v4.19.0"
    assert config.mathlib.revision == "c44e0c8ee63ca166450922a373c7409c5d26b00b"
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8000
    assert config.frontend.url == "http://127.0.0.1:5173"
    assert config.storage.path == Path("storage")
    assert set(config.model_dump()) == {
        "application",
        "lean",
        "mathlib",
        "server",
        "frontend",
        "storage",
    }


def test_product_config_rejects_unknown_or_mathematical_semantic_settings(
    tmp_path: Path,
) -> None:
    raw = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    raw["mathematics"] = {"assume_nat_subtraction": "integer"}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValidationError, match="mathematics"):
        load_product_config(path)


def test_product_config_requires_every_documented_section(tmp_path: Path) -> None:
    raw = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    del raw["lean"]["toolchain"]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValidationError, match="toolchain"):
        load_product_config(path)


def test_unified_version_report_covers_every_product_surface() -> None:
    versions = read_versions(ROOT, dictionary_version="0.1.0", ir_schema_version=1)

    assert versions == {
        "chinese2lean_version": "0.1.0",
        "core_version": "0.1.0",
        "desktop_version": "0.1.0",
        "web_version": "0.1.0",
        "lean_version": "4.19.0",
        "mathlib_revision": "c44e0c8ee63ca166450922a373c7409c5d26b00b",
        "dictionary_version": "0.1.0",
        "ir_schema_version": "1",
        "generator_version": "0.1.0",
    }


def test_product_logging_creates_five_logs_with_levels_and_redaction(tmp_path: Path) -> None:
    loggers = configure_product_logging(tmp_path / "logs", level="DEBUG")

    assert set(loggers) == set(LOG_CATEGORIES) == {
        "startup",
        "environment",
        "lean",
        "api",
        "error",
    }
    for category, logger in loggers.items():
        logger.log(logging.DEBUG, "token=alpha password=bravo safe=visible")
        logger.log(logging.INFO, "info")
        logger.log(logging.WARNING, "warning")
        logger.log(logging.ERROR, "error")
        for handler in logger.handlers:
            handler.flush()
        text = (tmp_path / "logs" / f"{category}.log").read_text(encoding="utf-8")
        assert "DEBUG" in text
        assert "INFO" in text
        assert "WARNING" in text
        assert "ERROR" in text
        assert "alpha" not in text
        assert "bravo" not in text
        assert "token=[REDACTED]" in text
        assert "password=[REDACTED]" in text
        assert "safe=visible" in text


def test_product_logging_rejects_unknown_level(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="日志等级"):
        configure_product_logging(tmp_path, level="TRACE")
