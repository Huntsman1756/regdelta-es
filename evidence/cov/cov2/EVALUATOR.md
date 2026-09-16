# COV-2 evaluator contract

`scripts/cov/evaluate_cov2.py` — frozen before any `src/regdelta`
change for COV-2 (§9). This file is the metric contract referenced by
`COV_EVALUATION_HEAD` / `metric-contract sha256`.

## Independence

- The evaluator never accepts a runtime method string as evidence.
  `binding_proof.before.method == X` is a claim, re-derived below.
- Reconstruction, the G1 binding audit (B1–B6 claim checks) and the
  O1/O2/O3 re-derivation run through the frozen stack
  (`evaluate_g2.evaluate_target`, `evaluate_g1.audit_relation`,
  `evaluate_dev` helpers) — unchanged inputs, unchanged semantics.
- COV-2 adds the coverage ledger, stratum split, ordering/continuity
  re-derivation, the §14 debt census and audit amendments. It does
  not weaken any frozen check.

## Strata

Per target, from its own `<metadatos>` (COV-1 §3 rule):

```text
vigencia_agotada = S OR estatus_derogacion = S
    -> HISTORICAL_PREDECESSOR
otherwise -> CURRENT_OPERATIONAL
```

Current assignment: `BOE-A-2010-15521` is the only
HISTORICAL_PREDECESSOR in the 16-target DEV corpus.

## binding-sides.jsonl (§11)

Canonical COV-2 coverage accounting. One row per
`modification_relation × {before, after}`:

```text
target, stratum, modifier, semantic_relation_signature,
runtime_relation_id, locator_key, side, operation_kind,
runtime_binding_status, runtime_binding_method,
runtime_candidate_count, evaluator_verdict, evaluator evidence,
representation_kind, evidence_scope, abstention_reason,
declared_order_basis, evaluator_predecessor
```

`evaluator_verdict` is the audit-derived side verdict
(`BINDING_CORRECT` counts; `BINDING_FALSE` is a false claim;
`NO_BINDING_CLAIM`/`BINDING_NOT_CHECKABLE` do not count).

## Semantic relation signature (§12, frozen serialization)

```text
sha256("cov2-rel-sig-v1|" + target + "|" + modifier + "|"
       + node_index + "|" + locator_key + "|" + operation_kind
       + "|" + sha256(norm(locator_raw)))
```

`node_index` = the operation's structural position in the frozen
modifier document (from the subject-outcomes ledger). No
`relation_id` participates; binding improvements may change
representation IDs without breaking the baseline join.

## Ordering (ordering.jsonl, §25–27)

Evaluator-side re-derivation per `(target, locator_key)` hop group:

```text
event date (relation publication_date)
-> amending work date (modifier fecha_disposicion)
-> subtype (modifier rango)
-> natural-sorted official number (numero_oficial)
-> document position (op node_index inside the modifier)
```

Unresolvable ties -> `ORDER_AMBIGUOUS`; no chain predecessor may be
claimed from ordering alone. `relation_id` never establishes legal
order — hash order may remain for serialization determinism only.

## Continuity (continuity.jsonl, §28–31)

Per hop: declared predecessor (runtime `binding_proof`), evaluator
predecessor under the ordering basis, and `scope_signature`
compatibility. Same locator string + incompatible proven scope must
not chain (`CHAIN_SCOPE_COLLISION`), never `CHAIN_PREDECESSOR`.

`scope_signature` = `(locator root family, proven enclosing scope)`
where the enclosing scope comes from a bound representation's
`structural_scope`; unproven context degrades to the locator root.

## Audit amendments (audit-amendments.jsonl)

The frozen audit compares a non-chained bound `before` against the
hash-ordered prior hop. When the runtime declares
`binding_proof.before.order_basis`, the evaluator re-derives the
predecessor under the official ordering above and re-adjudicates only
the `chain_predecessor` claim. With the unchanged baseline runtime
zero amendments fire and all canonical artifacts stay byte-identical
to `evidence/g2/dev/runs/001-g21`.

## New binding methods (§41 — closed vocabulary)

```text
UNIQUE_STRUCTURAL_TABLE_TARGET        table region, proven parent
                                      scope, unique structural cell
                                      match (B1/B2)
OPERATION_OWNED_TABLE_CONTENT         table region inside content the
                                      operation itself owns (B3)
REDESIGNATION_PREDECESSOR             before carried through a
                                      source-declared redesignation
                                      edge (§21–24)
SCOPE_QUALIFIED_CHAIN_PREDECESSOR     chain hop admitted only under
                                      compatible ScopeSignature
OFFICIAL_SAME_DATE_PREDECESSOR        chain hop ordered by official
                                      metadata, not hash
```

Verification of each:

- TABLE/TEXT claims: frozen span re-serialization + coverage check
  already re-derives the evidence region; `candidate_count` and the
  enumerated candidate set are checked against the proof.
- Predecessor claims: predecessor relation exists, its recorded
  `after_representation_id` equals the claimed `before`, and — when
  `order_basis` is declared — it matches the evaluator's official-order
  predecessor; a declared scope signature must be compatible.
- `REDESIGNATION_PREDECESSOR` additionally requires the recorded edge
  to be source-declared and parsed independently (§22 guards).

## Debt census (debt-census.json, §14)

Every non-`BINDING_CORRECT` side receives exactly one primary class
from the §14 taxonomy (plus `SIDE_NOT_APPLICABLE` for legitimately
N/A sides — ADD before / DELETE after). Classification is
deterministic from `(runtime status, method, reason)` plus a
table-content existence scan the frozen runtime could not perform.

## Metrics (cov-metrics.json)

Per stratum and per target:

```text
relations_emitted
leaf_operations / target_proven_ops / locator_proven_ops
leaf_operation_accounting (bool: full accounting, no problems)
positive_binding_assertions (before/after split)
unclaimed_sides
FALSE_FACT / FALSE_BINDING / FALSE_SUBJECT_ATTRIBUTION /
FALSE_LOCATOR_DECLARATION
```

Aggregate `metrics.json` keeps the frozen G2 shape for
byte-equivalence; COV-2 metrics live in `cov-metrics.json`.
