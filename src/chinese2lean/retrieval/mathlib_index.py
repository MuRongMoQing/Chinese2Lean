from pathlib import Path

from pydantic import BaseModel


class MathlibDeclaration(BaseModel):
    full_name: str
    statement: str
    module: str


class MathlibIndex:
    def __init__(self, declarations: list[MathlibDeclaration] | None = None) -> None:
        self.declarations = declarations or self.common()

    @staticmethod
    def common() -> list[MathlibDeclaration]:
        return [
            MathlibDeclaration(
                full_name="add_comm",
                statement="a + b = b + a",
                module="Mathlib.Algebra.Group.Basic",
            ),
            MathlibDeclaration(
                full_name="add_pos",
                statement="0 < a → 0 < b → 0 < a + b",
                module="Mathlib",
            ),
            MathlibDeclaration(full_name="sq_nonneg", statement="0 ≤ a ^ 2", module="Mathlib"),
        ]

    def save(self, path: Path) -> None:
        path.write_text(
            "\n".join(item.model_dump_json() for item in self.declarations) + "\n",
            encoding="utf-8",
        )
