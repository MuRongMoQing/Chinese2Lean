"""Product-layer configuration and observability helpers."""

from chinese2lean.product.config import ProductConfig, load_product_config
from chinese2lean.product.logging import LOG_CATEGORIES, configure_product_logging

__all__ = [
    "LOG_CATEGORIES",
    "ProductConfig",
    "configure_product_logging",
    "load_product_config",
]
