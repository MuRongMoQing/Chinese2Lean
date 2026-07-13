from chinese2lean.ir.models import Expr

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
        rendered = render_expr(expr.args[0], 9)
        return f"{expr.operator}{rendered}"
    if expr.kind == "binary" and expr.operator:
        precedence = _PRECEDENCE[expr.operator]
        left = render_expr(expr.args[0], precedence)
        right = render_expr(expr.args[1], precedence + 1)
        result = f"{left} {_OPERATORS.get(expr.operator, expr.operator)} {right}"
        return f"({result})" if precedence < parent_precedence else result
    raise ValueError(f"无法渲染表达式 kind={expr.kind}")
