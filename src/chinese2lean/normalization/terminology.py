from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TerminologyManifest(BaseModel):
    dictionary_version: str = "1"
    schema_version: int = 1
    lean_version: str = ""
    mathlib_revision: str = ""


class TermEntry(BaseModel):
    id: str
    version: int = 1
    canonical_zh: str
    aliases: list[str] = Field(default_factory=list)
    semantic_kind: str
    lean_template: str
    precedence: int = 0
    examples: list[dict[str, str]] = Field(default_factory=list)
    notes: str = ""
    lean_symbol: str | None = None
    argument_count: int | None = None
    associativity: str = "none"
    supported_types: list[str] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)
    counterexamples: list[dict[str, str]] = Field(default_factory=list)


class TerminologyConflict(ValueError):
    pass


class Terminology:
    def __init__(
        self,
        entries: list[TermEntry],
        version: str = "1",
        manifest: TerminologyManifest | None = None,
    ) -> None:
        self.entries = entries
        self.version = version
        self.manifest = manifest or TerminologyManifest(dictionary_version=version)
        seen_ids: set[str] = set()
        for entry in entries:
            if entry.id in seen_ids:
                raise TerminologyConflict(f"重复术语 ID：{entry.id}")
            seen_ids.add(entry.id)
            if len(entry.aliases) != len(set(entry.aliases)):
                raise TerminologyConflict(f"术语 {entry.id} 包含重复别名")

        canonical_entries = {entry.canonical_zh: entry for entry in entries}
        for entry in entries:
            for alias in entry.aliases:
                target = canonical_entries.get(alias)
                if target and target.id != entry.id and entry.canonical_zh in target.aliases:
                    raise TerminologyConflict(f"循环别名：{entry.id} <-> {target.id}")

        self._aliases: dict[str, TermEntry] = {}
        for entry in entries:
            for alias in [entry.canonical_zh, *entry.aliases]:
                previous = self._aliases.get(alias)
                if previous and previous.id != entry.id:
                    raise TerminologyConflict(f"术语别名冲突：{alias} ({previous.id}, {entry.id})")
                self._aliases[alias] = entry

    @classmethod
    def load(cls, directory: Path) -> Terminology:
        manifest_path = directory / "manifest.yaml"
        manifest_raw: dict[str, Any] = (
            yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if manifest_path.is_file()
            else {}
        )
        manifest = TerminologyManifest.model_validate(manifest_raw)
        entries: list[TermEntry] = []
        schema_versions: set[str] = set()
        for path in sorted(directory.glob("*.yaml")):
            if path.name == "manifest.yaml":
                continue
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            schema_versions.add(str(raw.get("version", "1")))
            entries.extend(TermEntry.model_validate(item) for item in raw.get("entries", []))
        if schema_versions - {str(manifest.schema_version)}:
            raise TerminologyConflict(f"词典 schema 版本不兼容：{sorted(schema_versions)}")
        return cls(entries, manifest.dictionary_version, manifest)

    def lookup(self, text: str) -> list[TermEntry]:
        exact = self._aliases.get(text)
        if exact:
            return [exact]
        return [entry for alias, entry in self._aliases.items() if text in alias or alias in text]

    @property
    def aliases(self) -> dict[str, TermEntry]:
        return dict(self._aliases)
