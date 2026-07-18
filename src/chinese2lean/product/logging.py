from __future__ import annotations

import logging
import re
from pathlib import Path

LOG_CATEGORIES = ("startup", "environment", "lean", "api", "error")
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(token|password|secret|api[_-]?key|authorization)\s*[:=]\s*([^\s,;]+)"
)


def redact_sensitive_values(message: str) -> str:
    """Remove common credential assignments from persisted and displayed logs."""

    return _SENSITIVE_VALUE.sub(r"\1=[REDACTED]", message)


class SensitiveValueFilter(logging.Filter):
    """Redact common credential assignments before writing a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_values(record.getMessage())
        record.args = ()
        return True


def configure_product_logging(
    log_dir: Path,
    *,
    level: str = "INFO",
) -> dict[str, logging.Logger]:
    """Create one isolated UTF-8 file logger per required product category."""

    normalized_level = level.upper()
    if normalized_level not in LOG_LEVELS:
        raise ValueError(f"不支持的日志等级：{level}")

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    loggers: dict[str, logging.Logger] = {}
    for category in LOG_CATEGORIES:
        logger = logging.getLogger(f"chinese2lean.{category}")
        logger.setLevel(normalized_level)
        logger.propagate = False
        for old_handler in logger.handlers[:]:
            old_handler.close()
            logger.removeHandler(old_handler)
        handler = logging.FileHandler(log_dir / f"{category}.log", encoding="utf-8")
        handler.setLevel(normalized_level)
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveValueFilter())
        logger.addHandler(handler)
        loggers[category] = logger
    return loggers
