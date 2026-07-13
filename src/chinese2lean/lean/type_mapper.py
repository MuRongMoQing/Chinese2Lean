TYPE_MAP = {"Nat": "ℕ", "Int": "ℤ", "Rat": "ℚ", "Real": "ℝ", "Bool": "Bool"}


def render_type(type_name: str) -> str:
    if type_name.startswith("Set "):
        return f"Set {render_type(type_name[4:])}"
    return TYPE_MAP.get(type_name, type_name)
