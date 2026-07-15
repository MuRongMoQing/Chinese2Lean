from pathlib import Path

from chinese2lean.normalization.terminology import Terminology

ROOT = Path(__file__).parents[1]


def test_terminology_manifest_pins_dictionary_and_lean_versions() -> None:
    terminology = Terminology.load(ROOT / "terminology")
    assert terminology.manifest.dictionary_version == "0.1.0"
    assert terminology.manifest.schema_version == 1
    assert terminology.manifest.lean_version == "4.19.0"
    assert terminology.manifest.mathlib_revision == "c44e0c8ee63ca166450922a373c7409c5d26b00b"


def test_rich_term_schema_and_duplicate_id_detection() -> None:
    from chinese2lean.normalization.terminology import TerminologyConflict

    terminology = Terminology.load(ROOT / "terminology")
    exists = terminology.lookup("存在")[0]
    assert exists.version == 1
    assert exists.argument_count == 2
    assert exists.associativity == "none"
    assert exists.contexts == ["quantifier_prefix"]
    assert exists.counterexamples

    duplicate = exists.model_copy(update={"canonical_zh": "另一个存在"})
    try:
        Terminology([exists, duplicate])
    except TerminologyConflict as error:
        assert "重复术语 ID" in str(error)
    else:
        raise AssertionError("重复术语 ID 必须被拒绝")


def test_normalization_is_traceable_and_context_sensitive() -> None:
    from chinese2lean.normalization.normalizer import Normalizer

    normalizer = Normalizer(Terminology.load(ROOT / "terminology"))
    result = normalizer.normalize("有一个实数 x，不大于 1。")
    assert result.source_text == "有一个实数 x，不大于 1。"
    assert result.normalized_text == "存在实数 x,<= 1."
    assert result.text == result.normalized_text
    assert [(item.source, item.canonical, item.term_id) for item in result.mappings] == [
        ("有一个", "存在", "logic.exists"),
        ("不大于", "<=", "inequality.le"),
    ]

    non_quantifier = normalizer.normalize("集合 A 有一个元素。")
    assert "有一个" in non_quantifier.normalized_text


def test_ir_schema_version_is_stable_and_round_trips() -> None:
    from chinese2lean.ir.models import Expr, TheoremIR
    from chinese2lean.ir.serialization import from_json, to_json

    ir = TheoremIR(
        theorem_name="schema_contract",
        variables=[],
        assumptions=[],
        conclusion=Expr(kind="literal", value=1),
    )
    assert ir.schema_version == 1
    assert from_json(to_json(ir)) == ir


def test_type_ambiguities_stop_generation_with_stable_codes() -> None:
    from chinese2lean.pipeline.converter import Converter

    cases = [
        (
            """# 定理名称
自然数减法
# 变量
n：自然数
# 结论
n - 1 <= n
""",
            "NAT_SUBTRACTION_AMBIGUOUS",
            "ambiguous",
        ),
        (
            """# 定理名称
整数除法
# 变量
z：整数
# 结论
z / 2 = z
""",
            "DIVISION_SEMANTICS_AMBIGUOUS",
            "ambiguous",
        ),
        (
            """# 定理名称
混合类型
# 变量
n：自然数, x：实数
# 结论
n < x
""",
            "MIXED_NUMERIC_TYPES",
            "ambiguous",
        ),
        (
            """# 定理名称
冲突声明
# 变量
x：自然数, x：整数
# 结论
x = x
""",
            "CONFLICTING_VARIABLE_TYPES",
            "ir_invalid",
        ),
    ]
    for source, code, status in cases:
        result = Converter.default(ROOT).convert_text(source, verify=False)
        assert result.status.value == status
        assert code in {item.code for item in [*result.warnings, *result.ir.ambiguities]}


def test_numeric_literals_inherit_the_declared_number_type() -> None:
    from chinese2lean.pipeline.converter import Converter

    source = """# 定理名称
实数零
# 变量
x：实数
# 结论
x + 0 = x
"""
    result = Converter.default(ROOT).convert_text(source, verify=False)
    literal = result.ir.conclusion.args[0].args[1]
    assert literal.value == 0
    assert literal.inferred_type == "Real"


def test_conversion_success_requires_locked_real_lean_verification() -> None:
    from chinese2lean.pipeline.converter import Converter

    source = """定理名称：正数加一仍为正
变量：x 是实数
假设：hx：x > 0
结论：x + 1 > 0
证明：因为 x > 0，所以 x + 1 > 0。
"""
    converter = Converter.default(ROOT)
    generated = converter.convert_text(source, verify=False)
    assert generated.status.value == "generated"
    assert not generated.success
    assert generated.source_text == source
    assert generated.normalized_text
    assert generated.name_mappings["正数加一仍为正"] == "positive_add_one"
    assert generated.selected_strategy is not None
    assert generated.selected_strategy.selected_strategy == "linarith"
    assert generated.statement_hash
    assert generated.lean_line_mappings
    mapping_kinds = {item.source_kind for item in generated.lean_line_mappings}
    assert {"variable", "assumption", "conclusion"} <= mapping_kinds

    verified = converter.convert_text(source, verify=True)
    assert verified.status.value == "verified", verified.diagnostics
    assert verified.success and verified.verified
    assert verified.versions == {
        "chinese2lean_version": "0.1.0",
        "core_version": "0.1.0",
        "desktop_version": "0.1.0",
        "web_version": "0.1.0",
        "lean_version": "4.19.0",
        "mathlib_revision": "c44e0c8ee63ca166450922a373c7409c5d26b00b",
        "dictionary_version": "0.1.0",
        "ir_schema_version": "1",
        "generator_version": "0.1.0",
    }


def test_circular_aliases_are_rejected_explicitly() -> None:
    from chinese2lean.normalization.terminology import (
        TermEntry,
        TerminologyConflict,
    )

    first = TermEntry(
        id="cycle.first",
        canonical_zh="甲",
        aliases=["乙"],
        semantic_kind="test",
        lean_template="A",
    )
    second = TermEntry(
        id="cycle.second",
        canonical_zh="乙",
        aliases=["甲"],
        semantic_kind="test",
        lean_template="B",
    )
    try:
        Terminology([first, second])
    except TerminologyConflict as error:
        assert "循环别名" in str(error)
    else:
        raise AssertionError("循环别名必须被拒绝")
