from __future__ import annotations

import hashlib
import re


class StatementChanged(ValueError):
    """Raised when a repair changes the theorem declaration."""


_DECLARATION = re.compile(
    r"\btheorem\s+[^\s]+\s*(?P<statement>.*?)\s*:=\s*by\b",
    flags=re.DOTALL,
)


def _canonical_statement(source: str) -> str:
    match = _DECLARATION.search(source)
    if not match:
        raise ValueError("无法从 Lean 源码中提取 theorem statement")
    return " ".join(match.group("statement").split())


def statement_source_fingerprint(source: str) -> str:
    """Hash the normalized theorem binders, assumptions, and conclusion."""
    canonical = _canonical_statement(source)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ensure_statement_unchanged(before: str, after: str) -> None:
    """Reject a repair that changes any semantic part of the theorem statement."""
    before_hash = statement_source_fingerprint(before)
    after_hash = statement_source_fingerprint(after)
    if before_hash != after_hash:
        raise StatementChanged(
            f"STATEMENT_CHANGED：修复前 {before_hash[:12]}，修复后 {after_hash[:12]}"
        )
