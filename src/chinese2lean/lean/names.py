import hashlib
import re

RESERVED = {
    "by",
    "def",
    "else",
    "end",
    "example",
    "if",
    "import",
    "in",
    "let",
    "match",
    "namespace",
    "open",
    "structure",
    "then",
    "theorem",
    "where",
    "with",
}


class NameAllocator:
    def __init__(self) -> None:
        self._used: set[str] = set()

    def allocate(self, source: str, preferred: str | None = None) -> str:
        candidate = preferred or self._transliterate(source)
        if candidate in RESERVED:
            candidate += "_"
        base = candidate
        suffix = 2
        while candidate in self._used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self._used.add(candidate)
        return candidate

    @staticmethod
    def _transliterate(source: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_']", "_", source).strip("_")
        if cleaned and not cleaned[0].isdigit():
            return cleaned
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
        return f"name_{digest}"


def theorem_name(source: str) -> str:
    known = {
        "正数加一仍为正": "positive_add_one",
        "正数相加仍为正": "add_pos_of_pos",
        "自然数加法交换律": "nat_add_comm",
    }
    return known.get(source.strip(), NameAllocator._transliterate(source.strip()))
