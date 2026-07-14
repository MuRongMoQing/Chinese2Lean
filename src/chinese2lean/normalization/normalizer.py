import re
from dataclasses import dataclass

from chinese2lean.normalization.terminology import Terminology


@dataclass(frozen=True)
class TerminologyMapping:
    source: str
    canonical: str
    term_id: str
    start: int
    end: int

    @property
    def original(self) -> str:
        return self.source


@dataclass(frozen=True)
class NormalizationResult:
    source_text: str
    normalized_text: str

    @property
    def text(self) -> str:
        return self.normalized_text

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
            return NormalizationResult(source_text=source, normalized_text=text, mappings=[])
        ordered_aliases = sorted(
            aliases,
            key=lambda alias: (-len(alias), -aliases[alias].precedence, alias),
        )
        pattern = re.compile("|".join(re.escape(alias) for alias in ordered_aliases))
        mappings: list[TerminologyMapping] = []

        def replace(match: re.Match[str]) -> str:
            original = match.group(0)
            entry = aliases[original]
            canonical_offset = entry.canonical_zh.find(original)
            canonical_start = match.start() - canonical_offset
            if canonical_offset >= 0 and canonical_start >= 0:
                if (
                    text[canonical_start : canonical_start + len(entry.canonical_zh)]
                    == entry.canonical_zh
                ):
                    return original
            if "quantifier_prefix" in entry.contexts:
                following = text[match.end() :].lstrip()
                type_prefix = r"(?:实数|自然数|整数|有理数|Real|Nat|Int|Rat)\b"
                if not re.match(type_prefix, following):
                    return original
            mappings.append(
                TerminologyMapping(
                    source=original,
                    canonical=entry.canonical_zh,
                    term_id=entry.id,
                    start=match.start(),
                    end=match.end(),
                )
            )
            return entry.canonical_zh

        return NormalizationResult(
            source_text=source, normalized_text=pattern.sub(replace, text), mappings=mappings
        )
