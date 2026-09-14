# G2.1 DEV Evaluator — Subject Ownership & Lifecycle

Frozen before any `src/regdelta` change in G2.1. Implementation:
`scripts/g2/evaluate_g2.py`. This evaluator is independent of the
runtime: it never accepts `subject_proof`/`binding_proof` contents as
truth — those are claims to be re-derived.

## Truth taxonomy

```text
PASS | FALSE_FACT
```

Binding verdicts (unchanged from G1):

```text
BINDING_CORRECT | BINDING_FALSE | BINDING_NOT_CHECKABLE |
NO_BINDING_CLAIM
```

## The three claims (per emitted modification_relation)

`target_locator_resolves` is replaced by three independent claims:

### O1 — OPERATION_TARGETS_INSTRUMENT

Re-derived evaluator-side from the modifier document alone:

```text
clause node → containing section → section/preamble targets
           → clause-attributive targets → corrigendum corrected
             instrument resolution
```

Expected attribution ∈ the frozen `TargetAttribution` taxonomy. A
relation may only exist when the expected status is `TARGET_PROVEN`.
An emitted relation whose expected attribution is `FOREIGN_TARGET`,
`MODIFIER_LOCAL`, `AMBIGUOUS` or `NOT_PROVABLE` is a

```text
FALSE_SUBJECT_ATTRIBUTION
```

Corrigendum rule: the corrected instrument `C` is resolved by the
preregistered priority (ELI `/corrigendum/` path → `anterior` whose
`palabra` is `CORRECCIÓN de errores` → unique official correction
relation). `target == C` authorizes `CORRIGENDUM_CORRECTED_INSTRUMENT`;
a downstream target requires an explicit clause-level naming
(`CORRIGENDUM_EXPLICIT_DOWNSTREAM_TARGET`). The secondary
`CORRIGE errores en TARGET` metadata relation is never ownership proof.

### O2 — OPERATION_DECLARES_LOCATOR

The evaluator recomposes the expected locator set from the operative
clause plus its lexical scope (active marker ancestors + governing
context setters + section preamble), under root-family exclusivity:

```text
explicit anejo ⟂ inherited norma/disposición
explicit norma ⟂ inherited anejo/disposición
explicit disposición ⟂ inherited norma/anejo
```

Sibling context introduced at one marker depth does not survive into
the next sibling at the same depth; unmarked ordinal-item setters
("Cuatro.", "Cinco.") are siblings of each other. Hierarchical
apartado values (`1.3.2`) are identifiers, not ranges; letter
enumerations (`c), d), e) y f)`) enumerate subjects.

An emitted relation whose recorded `locator_key` is not in the
expected set is a

```text
FALSE_LOCATOR_DECLARATION
```

### O3 — SUBJECT_EXISTENCE_BEFORE

Expected lifecycle immediately before the operation:

```text
ADD                                   → NOT_APPLICABLE
locator resolves in the target's
  original publication or prior
  chain hop bound an after            → PRESENT
prior proven DELETE                   → DELETED
otherwise                             → UNKNOWN
```

`UNKNOWN` is abstention, never a FALSE_FACT. Once the runtime emits
`subject_proof.existence_before`, an asserted `PRESENT|ABSENT|DELETED`
contradicting this derivation is a FALSE_FACT. No coverage threshold.

## Runtime inventory cross-check

For every modifier the evaluator enumerates leaf operations
independently and attributes each; `attribution.jsonl` records the
expected disposition per operation. After the runtime change the
evaluator asserts the hard invariant from the run's own accounting:

```text
parsed_leaf_operations == Σ attribution dispositions
```

## G1 binding claims

All G1 binding claims (`before_binding`, `after_binding`,
`chain_predecessor`, `resolution_consistent`, verb/discovery/date
claims) are preserved verbatim via the G1 audit.

## Root causes

Frozen G2 set — no new categories may be added after the baseline:

```text
RUNTIME_WRONG_TARGET_ATTRIBUTION | RUNTIME_WRONG_LOCATOR |
VALID_CHAIN_BORN_LOCATOR | G1_EVALUATOR_MODEL_ERROR | OTHER
```

plus the G0/G1 classes still used for binding failures.
