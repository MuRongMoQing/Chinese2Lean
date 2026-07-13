from __future__ import annotations

import re
from dataclasses import dataclass

from chinese2lean.ir.models import (
    Assumption,
    Expr,
    ProofStep,
    SourceSpan,
    TheoremIR,
    VariableDecl,
    WarningItem,
)
from chinese2lean.ir.validation import validate_ir
from chinese2lean.lean.names import NameAllocator, theorem_name
from chinese2lean.parser.controlled_chinese import split_sections

TYPE_NAMES = {
    "实数": "Real",
    "自然数": "Nat",
    "整数": "Int",
    "有理数": "Rat",
    "集合": "Set",
    "Real": "Real",
    "Nat": "Nat",
    "Int": "Int",
    "Rat": "Rat",
}

TOKEN = re.compile(
    r"\s*(?:(\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z0-9_']*)|(<=|>=|!=|→|↔|∧|∨|∈|⊆|[=<>+\-*/^(),¬]))"
)
PRECEDENCE = {
    "↔": 1,
    "→": 2,
    "∨": 3,
    "∧": 4,
    "=": 5,
    "!=": 5,
    "<": 5,
    "<=": 5,
    ">": 5,
    ">=": 5,
    "∈": 5,
    "⊆": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "^": 8,
}


class ParseError(ValueError):
    pass


@dataclass
class _Token:
    value: str
    kind: str


class ExpressionParser:
    def parse(self, text: str, span: SourceSpan | None = None) -> Expr:
        normalized = (
            text.strip()
            .replace("且", "∧")
            .replace("并且", "∧")
            .replace("或者", "∨")
            .replace("不等于", "!=")
            .replace("大于等于", ">=")
            .replace("小于等于", "<=")
            .replace("属于", "∈")
            .replace("包含于", "⊆")
        )
        self.tokens = self._tokenize(normalized)
        self.position = 0
        result = self._expression(0)
        if self.position != len(self.tokens):
            raise ParseError(f"无法解析表达式尾部：{self.tokens[self.position].value}")
        result.source_span = span
        return result

    @staticmethod
    def _tokenize(text: str) -> list[_Token]:
        tokens: list[_Token] = []
        cursor = 0
        while cursor < len(text):
            match = TOKEN.match(text, cursor)
            if not match:
                raise ParseError(f"无法识别的表达式：{text[cursor:]}")
            number, identifier, operator = match.groups()
            if number:
                tokens.append(_Token(number, "number"))
            elif identifier:
                tokens.append(_Token(identifier, "identifier"))
            else:
                tokens.append(_Token(operator, "operator"))
            cursor = match.end()
        return tokens

    def _expression(self, minimum: int) -> Expr:
        if self.position >= len(self.tokens):
            raise ParseError("表达式意外结束")
        token = self.tokens[self.position]
        self.position += 1
        if token.value in {"-", "¬"}:
            left = Expr(kind="unary", operator=token.value, args=[self._expression(9)])
        elif token.value == "(":
            left = self._expression(0)
            self._expect(")")
        elif token.kind == "number":
            value: int | float = float(token.value) if "." in token.value else int(token.value)
            left = Expr(kind="literal", value=value)
        elif token.kind == "identifier":
            if self._peek() == "(":
                self.position += 1
                arguments: list[Expr] = []
                if self._peek() != ")":
                    while True:
                        arguments.append(self._expression(0))
                        if self._peek() != ",":
                            break
                        self.position += 1
                self._expect(")")
                left = Expr(kind="application", value=token.value, args=arguments)
            else:
                left = Expr(kind="identifier", value=token.value)
        else:
            raise ParseError(f"非法表达式起始：{token.value}")
        while self.position < len(self.tokens):
            operator = self.tokens[self.position].value
            precedence = PRECEDENCE.get(operator)
            if precedence is None or precedence < minimum:
                break
            self.position += 1
            next_minimum = precedence if operator in {"^", "→"} else precedence + 1
            right = self._expression(next_minimum)
            left = Expr(kind="binary", operator=operator, args=[left, right])
        return left

    def _peek(self) -> str | None:
        return self.tokens[self.position].value if self.position < len(self.tokens) else None

    def _expect(self, value: str) -> None:
        if self._peek() != value:
            raise ParseError(f"期望 {value}")
        self.position += 1


class StatementParser:
    def __init__(self) -> None:
        self.expressions = ExpressionParser()

    def parse(self, text: str) -> TheoremIR:
        sections = split_sections(text)
        if not sections["name"]:
            return self._parse_natural_sentence(text)
        allocator = NameAllocator()
        source_name = sections["name"][0]
        lean_theorem_name = theorem_name(source_name)
        variables: list[VariableDecl] = []
        mappings: dict[str, str] = {source_name: lean_theorem_name}
        warnings: list[WarningItem] = []
        for index, line in enumerate(sections["variables"]):
            for declaration in re.split(r"[,;]", line):
                match = re.fullmatch(
                    r"\s*([A-Za-z_][A-Za-z0-9_']*)\s*(?:是|:|为)\s*(实数|自然数|整数|有理数|Real|Nat|Int|Rat)\s*",
                    declaration,
                )
                if not match:
                    warnings.append(
                        WarningItem(
                            code="INVALID_VARIABLE_DECLARATION",
                            message=f"无法解析变量声明：{declaration}",
                        )
                    )
                    continue
                source_variable, type_name = match.groups()
                lean_name = allocator.allocate(source_variable, source_variable)
                mappings[source_variable] = lean_name
                variables.append(
                    VariableDecl(
                        source_name=source_variable,
                        lean_name=lean_name,
                        type_name=TYPE_NAMES[type_name],
                        source_span=SourceSpan(sentence_index=index, text=declaration),
                    )
                )
        assumptions: list[Assumption] = []
        for index, line in enumerate(sections["assumptions"]):
            name_match = re.match(r"^(h[A-Za-z0-9_']*)\s*:\s*(.+)$", line)
            name = allocator.allocate(
                f"假设{index + 1}",
                name_match.group(1) if name_match else f"h{index + 1}",
            )
            proposition_text = name_match.group(2) if name_match else line
            try:
                proposition = self.expressions.parse(
                    proposition_text, SourceSpan(sentence_index=index, text=line)
                )
                assumptions.append(Assumption(name=name, proposition=proposition))
            except ParseError as error:
                warnings.append(WarningItem(code="INVALID_ASSUMPTION", message=str(error)))
        if not sections["conclusion"]:
            conclusion = Expr(kind="invalid", value="missing")
            warnings.append(WarningItem(code="MISSING_CONCLUSION", message="缺少结论。"))
        else:
            try:
                conclusion = self.expressions.parse(
                    sections["conclusion"][0],
                    SourceSpan(text=sections["conclusion"][0]),
                )
            except ParseError as error:
                conclusion = Expr(kind="invalid", value=sections["conclusion"][0])
                warnings.append(WarningItem(code="INVALID_CONCLUSION", message=str(error)))
        proof_steps = [
            ProofStep(
                step_id=f"step_{index + 1}",
                source_text=line,
                action="derive" if "所以" in line or "因此" in line else "fact",
            )
            for index, line in enumerate(sections["proof"])
        ]
        ir = TheoremIR(
            theorem_name=lean_theorem_name,
            variables=variables,
            assumptions=assumptions,
            conclusion=conclusion,
            proof_steps=proof_steps,
            warnings=warnings,
            name_mappings=mappings,
        )
        ir.warnings.extend(validate_ir(ir))
        return ir

    def _parse_natural_sentence(self, text: str) -> TheoremIR:
        match = re.search(
            r"对任意(实数|自然数|整数|有理数)\s+([A-Za-z_][A-Za-z0-9_']*)[,，]"
            r"如果\s*(.+?)[,，]那么\s*(.+?)[。.]*$",
            text.strip(),
        )
        if not match:
            invalid = Expr(kind="invalid", value=text)
            warning = WarningItem(code="UNSUPPORTED_SYNTAX", message="输入不符合受控中文语法。")
            return TheoremIR(
                theorem_name="invalid_theorem",
                variables=[],
                assumptions=[],
                conclusion=invalid,
                warnings=[warning],
                ambiguities=[warning],
            )
        type_name, variable_name, assumption_text, conclusion_text = match.groups()
        variable = VariableDecl(
            source_name=variable_name,
            lean_name=variable_name,
            type_name=TYPE_NAMES[type_name],
        )
        return TheoremIR(
            theorem_name="controlled_statement",
            variables=[variable],
            assumptions=[
                Assumption(name="h1", proposition=self.expressions.parse(assumption_text))
            ],
            conclusion=self.expressions.parse(conclusion_text),
            name_mappings={variable_name: variable_name},
        )
