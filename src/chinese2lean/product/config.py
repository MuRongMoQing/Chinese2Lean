from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _ClosedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicationConfig(_ClosedSection):
    version: str = Field(min_length=1)


class LeanConfig(_ClosedSection):
    version: str = Field(min_length=1)
    toolchain: str = Field(min_length=1)


class MathlibConfig(_ClosedSection):
    revision: str = Field(min_length=1)


class ServerConfig(_ClosedSection):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)


class FrontendConfig(_ClosedSection):
    url: str = Field(pattern=r"^https?://")


class StorageConfig(_ClosedSection):
    path: Path


class ProductConfig(_ClosedSection):
    """Closed, non-mathematical product configuration."""

    application: ApplicationConfig
    lean: LeanConfig
    mathlib: MathlibConfig
    server: ServerConfig
    frontend: FrontendConfig
    storage: StorageConfig


def load_product_config(path: Path) -> ProductConfig:
    """Load and validate the documented product YAML contract."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ProductConfig.model_validate(raw)
