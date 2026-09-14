# G0-G evaluation protocol (frozen before first DEV run)

Companion to `PREREG.md`. Both documents are committed at the
G0-G.0 seal; deviations discovered later are recorded, not silently
edited.

## Run sequence

```text
G0-G.1  run current pipeline over GENERALIZATION_DEV only
        → log every discrepancy with failure_class (closed taxonomy)
        → generic fixes only (fix-admission rule, PREREG.md)
        → re-run DEV; iterate freely; every iteration logged
G0-G.2  open SEALED_HOLDOUT exactly once
        → same pipeline, current HEAD at that moment
        → metrics + 100 % relation audit
        → verdict PASS/FAIL against this document
        → no post-open iteration
```

## Metric definitions (per target, then aggregate)

```text
declared_modifier_recall =
    |modifiers discovered ∧ reverse-cross-checked|
    / |explicit MODIFICA/CORRECCIÓN entries in the target's
       frozen <posteriores> gold|
    — agreement with explicit BOE relationships;
      NOT complete legal amendment recall.

operation_parsing_rate =
    |relations with valid operation_kind| / |emitted relations|

subject_locator_resolution =
    |relations with bound target_subject| / |emitted relations|

representation_binding =
    |relations whose required representations are bound|
    / |emitted relations|

chain_reconstruction =
    |multi-hop subjects correctly chained| / |multi-hop subjects|

applicability_extraction =
    computed only where the norm declares its own DFU/DT;
    targets without declared applicability are excluded from
    denominator and noted.

query_execution =
    changes / affects / upcoming / as-of / diff execute without
    exception on the target.

false_positive_facts = see Audit.

source_limitations =
    count of SOURCE_LIMITATION-class discrepancies (documented,
    not failures).
```

## Audit

- HOLDOUT: audit 100 % of emitted `modification_relations`
  (RESOLVED, PARTIAL, UNRESOLVED alike). Per relation, check every
  positive claim actually emitted: modifier identity/relation,
  operation_kind, target locator, before-representation binding (if
  present), after-representation binding (if present), resolution
  classification. UNRESOLVED does not fail by being UNRESOLVED; a
  positive claim contradicting the official source does.
- DEV: audit all emitted relations (volumes here make full audit
  feasible; if it were not, size and algorithm must be frozen before
  the first DEV run — recorded as deviation if changed later).
- Register: `evidence/g0g/audit.jsonl` — one line per audited
  relation: `relation_id, target, claims_checked, verdict,
  evidence_quote`.
- Adjudication: doubtful cases → FALSE_FACT (conservative).
- Hard gate: `FALSE_FACT_COUNT = 0` in each holdout target; no
  cross-target averaging.

## Failure taxonomy (closed)

```text
SOURCE_LIMITATION    needed datum not explicitly present in the
                     captured official source (proof required)
ACQUISITION_FAILURE  needed artifact not fetched / not storable
PARSER_FAILURE       datum present in source, not parsed
SCHEMA_FAILURE       parsed datum not persistable in frozen schema
EVALUATION_FAILURE   persisted datum wrongly surfaced by queries
```

Each discrepancy gets exactly one class plus an evidence
locator/quote. A source-present datum missed by RegDelta can never be
SOURCE_LIMITATION.

## Fix log

`evidence/g0g/fixes.jsonl` — per fix:
`failure_class, root_cause, generic_rule, files_changed,
targets_fixed, targets_regressed`. `generic_rule` must be verifiable
without naming the target identity. Mechanical support:
`tests/g0g/test_no_target_specific_code.py`.
