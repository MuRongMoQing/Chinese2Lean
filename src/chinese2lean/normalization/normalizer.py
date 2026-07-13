import re
from dataclasses import dataclass

from chinese2lean.normalization.terminology import Terminology


@dataclass(frozen=True)
class TerminologyMapping:
    original: str
    canonical: str
    term_id: str
    start: int
    end: int


@dataclass(frozen=True)
class NormalizationResult:
    text: str
    mappings: list[TerminologyMapping]


_SYMBOLS = {
    "，": ",",
    "：": ":",
    "；": ";",
    "（": "(",
    "）": ")",
    "。": ".",
    "≥": ">=",
    "≤": "<=",
    "≠": "!=",
    "＋": "+",
    "－": "-",
    "×": "*",
    "÷": "/",
}


class Normalizer:
    def __init__(self, terminology: Terminology) -> None:
        self.terminology = terminology

    def normalize(self, source: str) -> NormalizationResult:
        text = "".join(_SYMBOLS.get(char, char) for char in source).replace("\r\n", "\n")
        aliases = {
            alias: entry
            for alias, entry in self.terminology.aliases.items()
            if alias != entry.canonical_zh
        }
        if not aliases:
            return NormalizationResult(text=text, mappings=[])
        pattern = re.compile(
            "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
        )
        mappings: list[TerminologyMapping] = []

        def replace(match: re.Match[str]) -> str:
            original = match.group(0)
            entry = aliases[original]
            mappings.append(
                TerminologyMapping(
                    original=original,
                    canonical=entry.canonical_zh,
                    term_id=entry.id,
                    start=match.start(),
                    end=match.end(),
                )
            )
            return entry.canonical_zh

        return NormalizationResult(text=pattern.sub(replace, text), mappings=mappings)
