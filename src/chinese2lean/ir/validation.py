import re

from chinese2lean.ir.models import Expr, SourceSpan, TheoremIR, WarningItem

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_']*$")


def _identifiers(expr: Expr) -> set[str]:
    found = {str(expr.value)} if expr.kind == "identifier" else set()
    for arg in expr.args:
        found.update(_identifiers(arg))
    return found


def _undeclared_warnings(
    expr: Expr, declared: set[str], location: SourceSpan | None
) -> list[WarningItem]:
    return [
        WarningItem(
            code="UNDECLARED_VARIABLE",
            message=f"变量 {identifier} 在命题中出现，但没有声明类型。",
            location=location,
        )
        for identifier in sorted(_identifiers(expr) - declared)
        if identifier and not identifier[0].isupper()
    ]


def validate_ir(ir: TheoremIR) -> list[WarningItem]:
    warnings: list[WarningItem] = []
    declared = {item.lean_name for item in ir.variables}
    for assumption in ir.assumptions:
        warnings.extend(
            _undeclared_warnings(assumption.proposition, declared, assumption.source_span)
        )
    warnings.extend(_undeclared_warnings(ir.conclusion, declared, ir.conclusion.source_span))
    for variable in ir.variables:
        if not _IDENTIFIER.fullmatch(variable.lean_name):
            warnings.append(
                WarningItem(
                    code="INVALID_LEAN_NAME", message=f"非法 Lean 名称：{variable.lean_name}"
                )
            )
    return warnings
