from chinese2lean.ir.models import Expr, TheoremIR


def _contains_operator(expr: Expr, operator: str) -> bool:
    return expr.operator == operator or any(_contains_operator(arg, operator) for arg in expr.args)


def choose_tactic(ir: TheoremIR) -> str:
    for assumption in ir.assumptions:
        if assumption.proposition == ir.conclusion:
            return f"exact {assumption.name}"
    operator = ir.conclusion.operator
    if _contains_operator(ir.conclusion, "^") and operator in {">", ">=", "<", "<=", "="}:
        return "positivity"
    if operator == "=" and any(variable.type_name == "Nat" for variable in ir.variables):
        return "omega"
    if operator == "=" and ir.assumptions:
        return "linarith"
    if operator == "=":
        return "ring"
    if operator in {">", ">=", "<", "<=", "!="}:
        return "linarith"
    if operator in {"∧", "∨", "→"}:
        return "aesop"
    return "simp"
