from __future__ import annotations

import re
from typing import Literal, cast

from pydantic import BaseModel


class LeanDiagnostic(BaseModel):
    severity: Literal["error", "warning", "info"]
    file: str | None = None
    line: int | None = None
    column: int | None = None
    code: str | None = None
    message: str


_LOCATION = re.compile(
    r"^(?P<file>.*?):(?P<line>\d+):(?P<column>\d+):\s*"
    r"(?P<severity>error|warning|info):\s*(?P<message>.*)$"
)
_CODES = {
    "unknown tactic": "UNKNOWN_TACTIC",
    "unknown identifier": "UNKNOWN_IDENTIFIER",
    "unknown constant": "UNKNOWN_IDENTIFIER",
    "type mismatch": "TYPE_MISMATCH",
    "failed to synthesize": "SYNTHESIS_FAILED",
    "declaration uses 'sorry'": "FORBIDDEN_CONSTRUCT",
    "unsolved goals": "UNSOLVED_GOALS",
    "unexpected token": "SYNTAX_ERROR",
}


def classify_message(message: str) -> str | None:
    lowered = message.lower()
    return next((code for fragment, code in _CODES.items() if fragment in lowered), None)


def parse_diagnostics(output: str) -> list[LeanDiagnostic]:
    diagnostics: list[LeanDiagnostic] = []
    pending: LeanDiagnostic | None = None
    for line in output.splitlines():
        match = _LOCATION.match(line.strip())
        if match:
            pending = LeanDiagnostic(
                severity=cast(Literal["error", "warning", "info"], match.group("severity")),
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                code=classify_message(match.group("message")),
                message=match.group("message"),
            )
            diagnostics.append(pending)
        elif line.strip() and pending:
            pending.message += "\n" + line.rstrip()
    return diagnostics
