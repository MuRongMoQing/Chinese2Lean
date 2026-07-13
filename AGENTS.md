# Chinese2Lean Agent Instructions

## Project purpose

Chinese2Lean converts controlled Chinese mathematical statements and proofs into verified Lean 4 + Mathlib source files.

## Non-negotiable rules

1. A conversion is successful only when the generated Lean file compiles.
2. Never use `sorry`, `admit`, new axioms, or unsafe proof bypasses.
3. Never change the mathematical statement merely to make a proof compile.
4. Preserve a trace from source Chinese text to normalized text, IR, Lean code, and diagnostics.
5. Prefer deterministic parsers and repair rules before using an LLM.
6. Keep Lean and Mathlib versions pinned.
7. Every supported Chinese phrase must be documented in the terminology dictionary.
8. Every new syntax feature requires tests and documentation.
9. Ambiguity must be reported rather than silently guessed.
10. Run all relevant checks before considering a task complete.

## Required checks

```bash
pytest
ruff check .
mypy src
lake env lean examples/generated/positive_add_one.lean
```

## Architecture boundaries

* `normalization` normalizes words and symbols but does not construct Lean code.
* `parser` produces semantic structures but does not run Lean.
* `ir` contains model definitions independent of rendering.
* `lean` renders IR into Lean source.
* `verification` invokes Lean and parses diagnostics.
* `pipeline` coordinates stages.
* `llm` is optional and must not be required for basic deterministic tests.

## Lean generation rules

* Prefer explicit, readable theorem statements.
* Use stable Mathlib names verified against the pinned dependency.
* Use the narrowest reasonable imports where practical.
* Generated examples must not contain placeholders.
* Preserve theorem statement hashes across repair iterations.
* Record all repair attempts.

## Documentation rules

All user-facing documentation must be available in Chinese.

For each supported Chinese mathematical term, document:

* canonical Chinese phrase;
* aliases;
* semantic category;
* Lean representation;
* valid contexts;
* invalid or ambiguous contexts;
* at least one example.

## Testing policy

Every bug fix requires a regression test.

Tests should separately cover:

* normalization;
* parsing;
* IR construction;
* rendering;
* Lean compilation;
* diagnostic parsing;
* forbidden-token detection;
* statement-preservation checks.
