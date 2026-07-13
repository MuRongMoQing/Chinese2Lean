from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TermEntry(BaseModel):
    id: str
    canonical_zh: str
    aliases: list[str] = Field(default_factory=list)
    semantic_kind: str
    lean_template: str
    precedence: int = 0
    examples: list[dict[str, str]] = Field(default_factory=list)
    notes: str = ""


class TerminologyConflict(ValueError):
    pass


class Terminology:
    def __init__(self, entries: list[TermEntry], version: str = "1") -> None:
        self.entries = entries
        self.version = version
        self._aliases: dict[str, TermEntry] = {}
        for entry in entries:
            for alias in [entry.canonical_zh, *entry.aliases]:
                previous = self._aliases.get(alias)
                if previous and previous.id != entry.id:
                    raise TerminologyConflict(f"术语别名冲突：{alias} ({previous.id}, {entry.id})")
                self._aliases[alias] = entry

    @classmethod
    def load(cls, directory: Path) -> Terminology:
        entries: list[TermEntry] = []
        versions: set[str] = set()
        for path in sorted(directory.glob("*.yaml")):
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            versions.add(str(raw.get("version", "1")))
            entries.extend(TermEntry.model_validate(item) for item in raw.get("entries", []))
        if len(versions) > 1:
            raise TerminologyConflict(f"词典版本不一致：{sorted(versions)}")
        return cls(entries, next(iter(versions), "1"))

    def lookup(self, text: str) -> list[TermEntry]:
        exact = self._aliases.get(text)
        if exact:
            return [exact]
        return [entry for alias, entry in self._aliases.items() if text in alias or alias in text]

    @property
    def aliases(self) -> dict[str, TermEntry]:
        return dict(self._aliases)
