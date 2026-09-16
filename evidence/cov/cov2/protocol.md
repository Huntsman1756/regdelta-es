# COV-2 protocol — DEV representation-binding hardening

Executes `PREREG.md` in this directory. The COV gate protocol
(`evidence/cov/protocol.md`) and the G2 evaluator contract carry over
unchanged; this file records only COV-2 additions.

## Evidence handling

- `evidence/cov/cov3/holdout/` is sealed at COV-2A. Hash/integrity
  checks are not an opening; no semantic reads of its content by
  source, test or evaluation code until COV-3.
- `evidence/cov/cov3/discovery-raw/` holds eligibility fetches
  (metadata-only reads: `metadatos`, `posteriores`, `anteriores`).
  These bytes are `CAPTURED_STRUCTURALLY`, never `SEMANTICALLY_SEEN`.
- `evidence/cov/cov2/runs/` are DEV-equivalence re-runs over exactly
  the frozen G2.2 evidence (`evidence/g2/dev/manifest.json`). Zero
  network; zero new evidence acquisition for DEV coverage.
- Historical artifacts remain read-only inputs.

## Strata

Same mechanical rule as COV-1 §3: `HISTORICAL_PREDECESSOR` iff the
target's own captured `<metadatos>` show `vigencia_agotada = S` or
`estatus_derogacion = S`; otherwise `CURRENT_OPERATIONAL`. The frozen
20-target classification is in `evidence/cov/PREREG.md` §3.

## Ledgers

- `binding-sides.jsonl` is canonical for coverage accounting:
  one row per emitted `modification_relation × {before, after}`,
  carrying the frozen semantic relation signature, runtime binding
  status/method/candidate count and the independent evaluator verdict.
- `continuity.jsonl` journals every redesignation edge considered
  (admissible, refused, ambiguous) — EXP-B1 reporting, §51.
- `ordering.jsonl` journals every same-date group decision
  (resolved, ambiguous, scope collision) — EXP-L1 reporting, §52.
- `coverage-delta.jsonl` records every binding side whose outcome
  changed vs `runs/000-baseline` (§44); `fixes.jsonl` is the
  append-only generic-fix log (§45).

## Semantic relation signature (frozen, §12)

```text
signature = sha256 of canonical JSON:
  target | modifier | operation_kind | locator_key |
  normalized operative clause (ev._norm of locator_raw)
```

`relation_id` is never the baseline join key: representation changes
re-hash it. The signature is stable under representation churn because
it names the legal operation, not its artifacts.

## Experiments → workstreams

EXP-B1 (`PORT`) licenses workstream C (redesignation-aware pairing)
as a mechanism only. EXP-L1 (`PATTERN_CONFIRMED`) licenses workstream
D (official same-date ordering) as a deterministic prior re-proven
per case. No project code or pipeline enters.

## Hard gates (COV-2 close)

```text
FALSE_*                                   = 0  (every evaluated target)
CURR positive_binding_assertions         >= 443
CURR relations_emitted                   >= 519
CURR locator_proven_ops                  >= 445
leaf_operation_accounting                = 100%
HIST non-regression floors (COV-1 §9.2)  satisfied
B1-B6 failures                           = 0
PROTOCOL_INTEGRITY                       = PASS
COV-3 holdout                            sealed, unopened
```

## Current state

```text
COV-2A = IN_PROGRESS   (prereg committed; COV-3 selection pending)
```
