from __future__ import annotations

from chinese2lean.ir.models import Expr, TheoremIR, WarningItem

_NUMERIC_TYPES = {"Nat", "Int", "Rat", "Real"}
_RELATIONS = {"=", "!=", "<", "<=", ">", ">="}
_ARITHMETIC = {"+", "-", "*", "/", "^"}
_LOGIC = {"∧", "∨", "→", "↔"}


def validate_types(ir: TheoremIR) -> list[WarningItem]:
    """Infer expression types and return deterministic type diagnostics."""
    issues: list[WarningItem] = []
    source_types: dict[str, set[str]] = {}
    environment: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for variable in ir.variables:
        key = (variable.source_name, variable.type_name)
        if key in seen:
            issues.append(
                WarningItem(
                    code="DUPLICATE_VARIABLE",
                    message=f"变量 {variable.source_name} 被重复声明。",
                    location=variable.source_span,
                )
            )
        seen.add(key)
        source_types.setdefault(variable.source_name, set()).add(variable.type_name)
        environment.setdefault(variable.source_name, variable.type_name)
        environment.setdefault(variable.lean_name, variable.type_name)

    for name, types in source_types.items():
        if len(types) > 1:
            issues.append(
                WarningItem(
                    code="CONFLICTING_VARIABLE_TYPES",
                    message=f"变量 {name} 的类型声明冲突：{', '.join(sorted(types))}。",
                    details={"variable": name, "types": sorted(types)},
                )
            )

    def issue(code: str, message: str, expr: Expr, **details: object) -> None:
        issues.append(
            WarningItem(
                code=code,
                message=message,
                location=expr.source_span,
                details=dict(details),
            )
        )

    def infer(expr: Expr, expected: str | None = None) -> str | None:
        if expr.kind == "identifier":
            actual = environment.get(str(expr.value))
            expr.inferred_type = actual
            return actual
        if expr.kind == "literal":
            expr.inferred_type = expected
            return expected
        if expr.kind == "unary":
            if expr.operator == "¬":
                infer(expr.args[0], "Prop")
                expr.inferred_type = "Prop"
                return "Prop"
            actual = infer(expr.args[0], expected)
            expr.inferred_type = actual
            return actual
        if expr.kind == "quantifier":
            body_environment = dict(environment)
            if expr.value is not None and expr.binder_type:
                environment[str(expr.value)] = expr.binder_type
            infer(expr.args[0], "Prop")
            environment.clear()
            environment.update(body_environment)
            expr.inferred_type = "Prop"
            return "Prop"
        if expr.kind != "binary" or not expr.operator:
            return expr.inferred_type

        operator = expr.operator
        if operator in _LOGIC:
            infer(expr.args[0], "Prop")
            infer(expr.args[1], "Prop")
            expr.inferred_type = "Prop"
            return "Prop"

        if operator == "^":
            left_type = infer(expr.args[0], expected)
            infer(expr.args[1], "Nat")
            expr.inferred_type = left_type
            return left_type

        left_type = infer(expr.args[0], expected)
        right_type = infer(expr.args[1], left_type or expected)
        if left_type is None and right_type:
            left_type = infer(expr.args[0], right_type)
        operand_types = {item for item in (left_type, right_type) if item in _NUMERIC_TYPES}
        if len(operand_types) > 1:
            issue(
                "MIXED_NUMERIC_TYPES",
                f"运算两侧类型不兼容：{', '.join(sorted(operand_types))}；不会自动猜测强制转换。",
                expr,
                types=sorted(operand_types),
            )
        numeric_type = next(iter(operand_types), expected)
        if operator == "-" and numeric_type == "Nat":
            issue(
                "NAT_SUBTRACTION_AMBIGUOUS",
                "自然数减法是截断减法；必须明确原命题是否要求 Nat.sub。",
                expr,
            )
        if operator == "/" and numeric_type in {"Nat", "Int"}:
            issue(
                "DIVISION_SEMANTICS_AMBIGUOUS",
                "自然数或整数除法不是域除法；必须明确商的语义。",
                expr,
            )
        expr.inferred_type = "Prop" if operator in _RELATIONS else numeric_type
        return expr.inferred_type

    for assumption in ir.assumptions:
        infer(assumption.proposition, "Prop")
    infer(ir.conclusion, "Prop")
    return issues
