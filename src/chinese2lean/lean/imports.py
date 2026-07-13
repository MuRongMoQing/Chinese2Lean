def render_imports(imports: list[str]) -> str:
    unique = list(dict.fromkeys(imports or ["Mathlib"]))
    return "\n".join(f"import {module}" for module in unique)
