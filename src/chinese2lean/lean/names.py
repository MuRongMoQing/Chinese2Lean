import hashlib
import re

RESERVED = {
    "by",
    "def",
    "else",
    "end",
    "example",
    "if",
    "import",
    "in",
    "let",
    "match",
    "namespace",
    "open",
    "structure",
    "then",
    "theorem",
    "where",
    "with",
}


class NameAllocator:
    def __init__(self) -> None:
        self._used: set[str] = set()

    def allocate(self, source: str, preferred: str | None = None) -> str:
        candidate = preferred or self._transliterate(source)
        if candidate in RESERVED:
            candidate += "_"
        base = candidate
        suffix = 2
        while candidate in self._used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self._used.add(candidate)
        return candidate

    @staticmethod
    def _transliterate(source: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_']", "_", source).strip("_")
        if cleaned and not cleaned[0].isdigit():
            return cleaned
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
        return f"name_{digest}"


def theorem_name(source: str) -> str:
    known = {
        "正数加一仍为正": "positive_add_one",
        "正数相加仍为正": "add_pos_of_pos",
        "自然数加法交换律": "nat_add_comm",
        "实数平方非负": "square_nonnegative",
        "实数自反等式": "real_reflexive",
        "实数加法交换律": "real_add_comm",
        "实数加法结合律": "real_add_assoc",
        "实数零加法": "real_zero_add",
        "实数乘法交换律": "real_mul_comm",
        "自然数具体计算": "nat_concrete_calculation",
        "一次不等式": "linear_inequality",
        "线性假设推导": "linear_deduction",
        "合取消去": "conjunction_elimination",
        "合取构造": "conjunction_introduction",
        "正性蕴含": "positive_implication",
        "正数不是非正数": "positive_not_nonpositive",
        "存在相等见证": "exists_equal",
        "全称自反等式": "forall_reflexive",
        "整数正数后继仍正": "int_positive_successor",
        "有理数除以一": "rat_div_one",
    }
    return known.get(source.strip(), NameAllocator._transliterate(source.strip()))
