from __future__ import annotations

import re

_FORBIDDEN_KEYWORDS = {"sorry", "admit", "axiom", "unsafe"}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")


def find_forbidden_construct(source: str) -> str | None:
    """Return a forbidden Lean keyword outside comments and string literals."""
    index = 0
    block_depth = 0
    in_string = False
    while index < len(source):
        pair = source[index : index + 2]
        if block_depth:
            if pair == "/-":
                block_depth += 1
                index += 2
                continue
            if pair == "-/":
                block_depth -= 1
                index += 2
                continue
            index += 1
            continue
        if in_string:
            if source[index] == "\\":
                index += 2
                continue
            if source[index] == '"':
                in_string = False
            index += 1
            continue
        if pair == "--":
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
            continue
        if pair == "/-":
            block_depth = 1
            index += 2
            continue
        if source[index] == '"':
            in_string = True
            index += 1
            continue
        match = _IDENTIFIER.match(source, index)
        if match:
            token = match.group(0)
            if token in _FORBIDDEN_KEYWORDS:
                return token
            index = match.end()
            continue
        index += 1
    return None
