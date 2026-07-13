from chinese2lean.ir.models import TheoremIR
from chinese2lean.lean.expression_renderer import render_expr
from chinese2lean.lean.imports import render_imports
from chinese2lean.lean.proof_renderer import choose_tactic
from chinese2lean.lean.type_mapper import render_type


class LeanRenderer:
    def render(self, ir: TheoremIR) -> str:
        variables = " ".join(
            f"({item.lean_name} : {render_type(item.type_name)})" for item in ir.variables
        )
        assumptions = " ".join(
            f"({item.name} : {render_expr(item.proposition)})" for item in ir.assumptions
        )
        binders = " ".join(part for part in (variables, assumptions) if part)
        declaration = f"theorem {ir.theorem_name}"
        if binders:
            declaration += f" {binders}"
        return (
            f"{render_imports(ir.imports)}\n\n{declaration} : {render_expr(ir.conclusion)} := by\n"
            f"  {choose_tactic(ir)}\n"
        )
