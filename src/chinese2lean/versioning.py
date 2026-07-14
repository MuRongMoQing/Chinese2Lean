from __future__ import annotations

import json
import tomllib
from pathlib import Path


def read_versions(
    project_root: Path,
    *,
    dictionary_version: str,
    ir_schema_version: int,
) -> dict[str, str]:
    """Read all generator dependency versions from pinned repository files."""
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    toolchain = (project_root / "lean-toolchain").read_text(encoding="utf-8").strip()
    lean_version = toolchain.rsplit(":", maxsplit=1)[-1].removeprefix("v")
    manifest = json.loads((project_root / "lake-manifest.json").read_text(encoding="utf-8"))
    packages = {item["name"]: item for item in manifest["packages"]}
    return {
        "lean_version": lean_version,
        "mathlib_revision": str(packages["mathlib"]["rev"]),
        "dictionary_version": dictionary_version,
        "ir_schema_version": str(ir_schema_version),
        "generator_version": str(pyproject["project"]["version"]),
    }
