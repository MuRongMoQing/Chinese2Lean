from pydantic import BaseModel, Field

from chinese2lean.ir.models import Expr, TheoremIR


class ProofStrategy(BaseModel):
    selected_strategy: str
    code: str
    reason: str
    alternatives_tried: list[str] = Field(default_factory=list)


def _contains_operator(expr: Expr, operator: str) -> bool:
    return expr.operator == operator or any(_contains_operator(arg, operator) for arg in expr.args)


def _same_expr(left: Expr, right: Expr) -> bool:
    return (
        left.kind == right.kind
        and left.operator == right.operator
        and left.value == right.value
        and len(left.args) == len(right.args)
        and all(_same_expr(a, b) for a, b in zip(left.args, right.args, strict=True))
    )


def _strategy(name: str, code: str, reason: str) -> ProofStrategy:
    return ProofStrategy(selected_strategy=name, code=code, reason=reason)


def choose_strategy(ir: TheoremIR) -> ProofStrategy:
    conclusion = ir.conclusion
    for assumption in ir.assumptions:
        if _same_expr(assumption.proposition, conclusion):
            return _strategy("exact", f"exact {assumption.name}", "结论与已有假设结构完全一致")
        if assumption.proposition.operator == "∧":
            for index, component in enumerate(assumption.proposition.args, start=1):
                if _same_expr(component, conclusion):
                    return _strategy(
                        "exact",
                        f"exact {assumption.name}.{index}",
                        "结论是已有合取假设的直接分量",
                    )

    if conclusion.kind == "quantifier" and conclusion.operator == "exists":
        body = conclusion.args[0]
        if (
            body.operator == "="
            and body.args[0].kind == "identifier"
            and str(body.args[0].value) == str(conclusion.value)
        ):
            witness = body.args[1]
            if witness.kind in {"identifier", "literal"}:
                return _strategy(
                    "exact",
                    f"exact ⟨{witness.value}, rfl⟩",
                    "存在量词的等式给出了确定性见证",
                )
        return _strategy("aesop", "aesop", "存在命题没有可直接提取的简单见证")

    if conclusion.kind == "quantifier" and conclusion.operator == "forall":
        binder = str(conclusion.value)
        body = conclusion.args[0]
        if body.operator == "=" and _same_expr(body.args[0], body.args[1]):
            return _strategy("rfl", f"intro {binder}\n  rfl", "全称命题的主体是自反等式")
        return _strategy("aesop", f"intro {binder}\n  aesop", "先引入全称变量再做逻辑搜索")

    operator = conclusion.operator
    if operator == "→":
        consequent = conclusion.args[1]
        if consequent.operator in {"=", "!=", "<", "<=", ">", ">="}:
            return _strategy("linarith", "intro h\n  linarith", "蕴含主体是线性数值关系")
        return _strategy("aesop", "intro h\n  aesop", "蕴含主体是命题逻辑结构")

    if conclusion.kind == "unary" and conclusion.operator == "¬":
        return _strategy("linarith", "linarith", "否定目标与数值假设可转化为矛盾")

    if operator == "=" and _same_expr(conclusion.args[0], conclusion.args[1]):
        return _strategy("rfl", "rfl", "等式两侧结构完全相同")

    if operator in {"∧", "∨"}:
        return _strategy("aesop", "aesop", "目标属于命题逻辑的构造或拆分")

    if _contains_operator(conclusion, "^") and operator in {">", ">=", "<", "<=", "="}:
        return _strategy("positivity", "positivity", "目标是包含幂的显然正性或非负性")

    number_types = {variable.type_name for variable in ir.variables}
    if number_types & {"Nat", "Int"} and operator in {"=", "!=", "<", "<=", ">", ">="}:
        return _strategy("omega", "omega", "自然数或整数目标属于 Presburger 算术")

    if _contains_operator(conclusion, "/"):
        return _strategy("simp", "simp", "除法目标可由单位元等简化规则处理")

    if operator == "=" and ir.assumptions:
        return _strategy("linarith", "linarith", "等式由线性数值假设推出")
    if operator == "=":
        return _strategy("ring", "ring", "目标是无假设的多项式恒等式")
    if operator in {">", ">=", "<", "<=", "!="}:
        return _strategy("linarith", "linarith", "假设与结论是线性数值关系")
    return _strategy("simp", "simp", "目标可由稳定的基础化简规则处理")


def choose_tactic(ir: TheoremIR) -> str:
    """Compatibility wrapper returning only the rendered tactic body."""
    return choose_strategy(ir).code
