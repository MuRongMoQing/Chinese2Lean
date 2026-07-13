import re

SECTION_ALIASES = {
    "定理名称": "name",
    "变量": "variables",
    "假设": "assumptions",
    "结论": "conclusion",
    "证明": "proof",
}


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {value: [] for value in SECTION_ALIASES.values()}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = line.lstrip("#").strip().rstrip(":")
        if heading in SECTION_ALIASES:
            current = SECTION_ALIASES[heading]
            continue
        match = re.match(r"^(定理名称|变量|假设|结论|证明)\s*:\s*(.+)$", line)
        if match:
            current = SECTION_ALIASES[match.group(1)]
            sections[current].append(match.group(2).rstrip("."))
        elif current:
            sections[current].append(re.sub(r"^\d+[.、]\s*", "", line).rstrip("."))
    return sections
