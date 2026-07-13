from chinese2lean.ir.models import ProofStep


def suggest_tactic(steps: list[ProofStep]) -> str | None:
    text = " ".join(step.source_text for step in steps)
    if any(word in text for word in ("大于", "小于", ">", "<", "不等式")):
        return "linarith"
    if "交换" in text:
        return "simp [add_comm]"
    return None
