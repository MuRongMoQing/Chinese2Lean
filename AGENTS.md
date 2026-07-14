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
chinese2lean verify-all examples/generated
chinese2lean version
lake env lean examples/generated/positive_add_one.lean
```

## Architecture boundaries

* `normalization` normalizes words and symbols but does not construct Lean code.
* `parser` produces semantic structures but does not run Lean.
* `ir` contains model definitions independent of rendering.
* `lean` renders IR into Lean source.
* `verification` invokes Lean and parses diagnostics.
* `repair` applies bounded, auditable fixes without changing theorem statements.
* `pipeline` coordinates stages.
* `terminology` owns stable phrases, aliases, contexts, precedence, and versions.
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

## Current implementation baseline

The phase-one reliability work began from commit 1715b9a (`docs: add agent instructions`) and was completed in commit b9163e8 (`feat: strengthen phase-one reliability`). The completed commit is pushed to origin/main.

The existing normalization → parser → ir → lean → verification → pipeline architecture was preserved. Do not replace it with a new minimal project or rewrite it without a demonstrated blocking reason.

The implementation currently provides:

* traceable Chinese normalization and context-sensitive terminology replacement;
* strongly typed, serializable IR with schema version 1;
* Nat, Int, Rat, and Real type validation;
* parsing for universal and existential quantifiers, implication, conjunction, negation, relations, and arithmetic;
* correct operator precedence, exponentiation, parentheses, and unary minus handling;
* deterministic Lean name generation, IR-based rendering, and layered proof strategies;
* real Lean verification in the pinned environment;
* token-aware forbidden-construct scanning;
* theorem-statement hashing and repair invariance checks;
* at most three audited repair attempts, including Mathlib import and tactic replacement;
* structured Lean diagnostics, unified conversion results, and source-to-Lean line mappings;
* normalize, version, verify-all, and terminology CLI commands;
* conflict checks covering structured and natural-language variable names, types, counts, assumptions, and conclusions.

All P1 and hard findings from the phase-one standards/specification review were closed before commit b9163e8.

## Phase-one file record

The phase-one change created 56 files, modified 27 existing files, and deleted no files.

Major additions were:

* docs/repair.md, docs/testing.md, and docs/type_system.md;
* 20 Chinese inputs under examples/chinese/;
* 19 new Lean outputs under examples/generated/;
* src/chinese2lean/ir/type_checking.py;
* src/chinese2lean/verification/batch.py;
* src/chinese2lean/verification/forbidden.py;
* src/chinese2lean/verification/invariance.py;
* src/chinese2lean/versioning.py;
* terminology/manifest.yaml;
* eight focused test modules.

Major modified areas were README.md, CONTRIBUTING.md, the Chinese documentation, parser, normalizer, IR, renderer, pipeline, verification, CLI, terminology/logic.yaml, existing examples, and verification tests.

This record is historical context. Future agents must inspect the current diff rather than assuming these file counts remain current.

## Controlled Chinese support

### Supported

* Structured Markdown input.
* Finite natural sentences with one or two explicitly typed universal variables.
* Universal quantification: ∀.
* Existential quantification: ∃.
* Implication: →.
* Conjunction: ∧.
* Negation: ¬.
* Relations: =, ≠, <, ≤, >, ≥.
* Arithmetic: +, -, *, /, ^, parentheses, and unary minus.
* Structured-field versus natural-body conflict detection.

### Partially supported

* Disjunction: ∨.
* Biconditional: ↔.
* Simple deterministic existential witnesses.
* Preliminary set-relation expressions.

### Unsupported

* Arbitrary natural-language proofs.
* Implicit variables and pronoun resolution.
* Arbitrary higher-mathematics proof generation.
* Complex sets and dependent types.
* General calculus automation.
* Measure theory, category theory, and functional analysis.

Ambiguous inputs must return stable diagnostic codes and must never be silently guessed.

## Types and mathematical scope

* Nat / ℕ supports basic arithmetic. Potentially misunderstood subtraction returns NAT_SUBTRACTION_AMBIGUOUS because Nat subtraction is truncated.
* Int / ℤ supports basic arithmetic. Division must not be treated as field division.
* Rat / ℚ supports field arithmetic and simple division.
* Real / ℝ supports basic algebra, equalities, and linear inequalities.
* Numeric literals inherit their type from their typed expression context.
* Mixed numeric domains return MIXED_NUMERIC_TYPES; do not depend on accidental coercion.
* Nat or Int division ambiguity returns DIVISION_SEMANTICS_AMBIGUOUS.
* Conflicting declarations return CONFLICTING_VARIABLE_TYPES.

All free variables must have explicit types. IR validation failure must stop Lean generation.

## Terminology baseline

The formal terminology dictionary is stored under terminology/.

Current phase-one metadata:

* dictionary version: 0.1.0;
* schema version: 1;
* formal entries: 19.

The dictionary loader detects:

* duplicate IDs;
* duplicate aliases;
* cross-entry alias conflicts;
* circular aliases;
* incompatible versions.

Matching uses longest text, priority, stable ordering, and supported context rules. Users may extend the YAML dictionary, but extensions must pass terminology check and have documentation, positive examples, counterexamples, and tests.

## Verification success contract

Only VERIFIED is successful. GENERATED only means Lean source was produced.

A verified conversion requires all of the following:

1. IR validation succeeds.
2. Lean source is generated.
3. The forbidden-token scan succeeds.
4. The theorem statement is unchanged.
5. lake env lean returns exit code 0.
6. There are no unsolved goals.
7. There is no timeout.
8. The toolchain comes from the pinned environment.

The verifier must use a subprocess argument list, shell=False, a timeout, captured output, validated paths, an input-size limit, a temporary directory, cleanup, and structured diagnostics.

An exit code of 0 from an unlocked system Lake is not a verified success.

## Stable failure and ambiguity behavior

The current pipeline explicitly rejects or reports:

* undeclared variables;
* missing variable types;
* conflicting types for the same variable;
* unknown terminology or invalid expressions;
* incomplete quantifier scope;
* ambiguous bare uses of “有”;
* Nat truncating subtraction;
* unclear Nat or Int division semantics;
* mixed numeric domains;
* multiple structured conclusions;
* conflicts between structured fields and natural-language body text;
* forbidden Lean constructs;
* statement-changing repairs;
* compilation outside the pinned environment.

Tests should assert stable error codes rather than entire diagnostic strings.

## Repair constraints

Automatic repair is limited to three attempts.

Every attempt must record:

* attempt number;
* diagnostic category and diagnostics;
* source before and after;
* change summary;
* statement hash before and after;
* verification result.

Current safe repair rules cover adding an explicit Mathlib import when appropriate and replacing an unsuitable tactic with a deterministic alternative.

The repairer does not automatically rewrite coercions, complex type annotations, arbitrary syntax trees, assumptions, conclusions, or mathematical intent.

## Lean environment and version locks

The phase-one pinned environment is:

* Lean: 4.19.0;
* Lean commit: 6caaee842e94;
* Mathlib revision: c44e0c8ee63ca166450922a373c7409c5d26b00b;
* terminology dictionary: 0.1.0;
* IR schema: 1;
* generator: 0.1.0.

Version sources are:

* lean-toolchain;
* lakefile.toml;
* lake-manifest.json;
* terminology/manifest.yaml;
* pyproject.toml.

Do not silently substitute an arbitrary system Lean version.

On Windows, if Git reports dubious ownership because a sandbox identity created the repository, add only the exact repository path to safe.directory. Do not disable Git ownership checks globally.

## Phase-one validation record

The last complete validation on 2026-07-14 recorded:

~~~text
pytest:
  passed: 99
  failed: 0
  warnings: 1 third-party Starlette/httpx deprecation warning
  duration: 278.43 seconds

ruff:
  result: All checks passed

mypy:
  source files checked: 44
  result: no issues

Lean batch:
  total: 20
  verified: 20
  failed: 0
  diagnostics: 0
  duration: 238.7 seconds
~~~

The suite also contained 12 primary failure or ambiguity cases with stable error codes.

These values are a historical baseline, not permission to skip current checks. Rerun all relevant checks after every change.

## CLI contract

The supported commands include:

~~~bash
chinese2lean normalize input.md
chinese2lean parse input.md
chinese2lean convert input.md
chinese2lean convert input.md --output Result.lean
chinese2lean verify Result.lean
chinese2lean verify-all examples/generated
chinese2lean terminology check
chinese2lean terminology lookup "任意"
chinese2lean version
~~~

When console scripts are not on PATH, use python -m chinese2lean.cli with the same arguments.

convert should preserve or emit:

* Lean source;
* IR JSON;
* conversion report JSON;
* diagnostics;
* terminology mappings;
* name mappings;
* source-to-Lean line mappings;
* version metadata;
* repair history.

## Reproduction commands

~~~bash
python -m pip install -e ".[dev,api]"
elan toolchain install leanprover/lean4:v4.19.0
lake update

python -m pytest
python -m ruff check .
python -m mypy src
lake env lean --version

python -m chinese2lean.cli convert examples/chinese/positive_add.md --output work/positive_add.lean
lake env lean work/positive_add.lean

python -m chinese2lean.cli verify-all examples/generated
python -m chinese2lean.cli terminology check
python -m chinese2lean.cli version
~~~

## Known limitations

* Natural sentences support only documented controlled templates.
* Automatic existential witness selection is limited.
* Set support is preliminary.
* The default import is Mathlib; minimal-import optimization remains future work.
* Proof steps preserve source text but do not interpret arbitrary Chinese proof prose.
* Terminology context handling currently relies mainly on quantifier-prefix rules and parser structure.
* Repair does not synthesize arbitrary coercions or new mathematical proof ideas.

Do not describe these areas as fully supported.

## Next-phase direction

Reasonable next steps, after preserving all phase-one guarantees, are:

* add explicit coercion nodes to IR instead of relying on Lean inference;
* add real end-to-end tests for set types and set quantifiers;
* translate proof steps into finer-grained, auditable proof plans;
* expand deterministic diagnostic repair rules;
* optimize minimal Mathlib imports while preserving statement hashes.

Future plans must not be used to conceal incomplete current requirements.
