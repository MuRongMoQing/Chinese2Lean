from typing import Protocol

from chinese2lean.pipeline.result import ConversionResult
from chinese2lean.verification.runner import LeanRunResult


class ConverterPort(Protocol):
    """Boundary through which the application layer invokes the core converter."""

    def convert_text(self, source: str, *, verify: bool = False) -> ConversionResult: ...


class VerifierPort(Protocol):
    """Boundary through which the application layer invokes Lean verification."""

    def verify_code(self, source: str) -> LeanRunResult: ...


class VersionProvider(Protocol):
    """Supply the unified, pinned product version report."""

    def get_versions(self) -> dict[str, str]: ...
