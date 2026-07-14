from chinese2lean.ir.models import Expr
from chinese2lean.lean.type_mapper import render_type

_OPERATORS = {"!=": "≠", "<=": "≤", ">=": "≥"}
_PRECEDENCE = {
    "↔": 1,
    "→": 2,
    "∨": 3,
    "∧": 4,
    "=": 5,
    "!=": 5,
    "<": 5,
    "<=": 5,
    ">": 5,
    ">=": 5,
    "∈": 5,
    "⊆": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "^": 8,
}


def render_expr(expr: Expr, parent_precedence: int = 0) -> str:
    if expr.kind in {"identifier", "literal"}:
        return str(expr.value)
    if expr.kind == "application":
        return " ".join([str(expr.value), *(f"({render_expr(arg)})" for arg in expr.args)])
    if expr.kind == "unary":
        rendered = render_expr(expr.args[0])
        if expr.args[0].kind == "binary":
            rendered = f"({rendered})"
        result = f"{expr.operator}{rendered}"
        if expr.operator == "-" and parent_precedence >= _PRECEDENCE["^"]:
            return f"({result})"
        return result
    if expr.kind == "quantifier" and expr.operator and expr.binder_type:
        symbols = {"forall": "∀", "exists": "∃"}
        symbol = symbols.get(expr.operator)
        if symbol is None:
            raise ValueError(f"未知量词：{expr.operator}")
        result = (
            f"{symbol} {expr.value} : {render_type(expr.binder_type)}, {render_expr(expr.args[0])}"
        )
        return f"({result})" if parent_precedence else result
    if expr.kind == "binary" and expr.operator:
        precedence = _PRECEDENCE[expr.operator]
        left = render_expr(expr.args[0], precedence)
        right = render_expr(expr.args[1], precedence + 1)
        result = f"{left} {_OPERATORS.get(expr.operator, expr.operator)} {right}"
        return f"({result})" if precedence < parent_precedence else result
    raise ValueError(f"无法渲染表达式 kind={expr.kind}")
