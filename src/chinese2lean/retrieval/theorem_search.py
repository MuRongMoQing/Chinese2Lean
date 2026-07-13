from pydantic import BaseModel

from chinese2lean.retrieval.mathlib_index import MathlibIndex


class TheoremCandidate(BaseModel):
    full_name: str
    statement: str
    module: str
    score: float
    reason: str


class TheoremSearch:
    def __init__(self, index: MathlibIndex | None = None) -> None:
        self.index = index or MathlibIndex()

    def search(
        self, keywords: list[str], allowed: set[str] | None = None
    ) -> list[TheoremCandidate]:
        terms = {term.lower() for term in keywords if term}
        candidates: list[TheoremCandidate] = []
        for declaration in self.index.declarations:
            if allowed is not None and declaration.full_name not in allowed:
                continue
            haystack = f"{declaration.full_name} {declaration.statement}".lower()
            hits = sum(term in haystack for term in terms)
            if hits:
                candidates.append(
                    TheoremCandidate(
                        full_name=declaration.full_name,
                        statement=declaration.statement,
                        module=declaration.module,
                        score=hits / max(len(terms), 1),
                        reason=f"匹配 {hits} 个关键词",
                    )
                )
        return sorted(candidates, key=lambda item: (-item.score, item.full_name))
