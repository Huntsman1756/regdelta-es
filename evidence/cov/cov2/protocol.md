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
                                          (see COV-3_SELECTION below)
```

## COV-3 selection outcome (COV-2A, decided)

The frozen COV-1 §11 rule was executed unchanged
(scripts/cov/select_cov3.py over the COV-2-extended seen-set):

```text
COV-3_SELECTION = STOP
reason          = CURRENT_OPERATIONAL eligible 0 < 3
holdout_status  = UNMATERIALIZABLE
selection_rule  = executed unchanged
```

Universe 76 (index corpus + G2.0b graph); 51 semantically seen;
25 fresh candidates; 1 eligible (HIST, 6 declared modifiers).
Every BdE Circular with declared_modifier_count >= 3 in the frozen
universe was already consumed by G2.2/COV-1 — the dense-modifier
circular corpus is exhausted.

Decision (owner, this thread): COV-2 proceeds DEV-only. The STOP
does not invalidate the coverage hypothesis; there is no holdout to
tune on, so the seal-before-runtime clause is vacuous. No amendment
to the COV-3 selection rule. The terminal report distinguishes:

```text
COV-2_DEV        = PASS | FAIL
COV-3_READINESS  = NOT_READY_FOR_COV_3
```

Fresh-corpus validation is deferred to a separate preregistration —
preferably a prospective-temporal holdout (the next qualifying BdE
Circular becomes genuinely future evidence against the COV-2-frozen
runtime).

## COV-2B baseline freeze

`scripts/cov/evaluate_cov2.py` frozen before any `src/regdelta`
change (§9). Contract documented in `EVALUATOR.md`. Baseline run
`runs/000-baseline` embeds `run_id = 001-g21` (the run id is part of
canonical artifact content).

```text
runtime_head            6bda96f46be0983c5ac236c0dc00b96d6a4806d3
src_tree_sha256         6dd38af07b0b9d5db80a90b2a073f818817319f3
evaluator_sha256        43cc3d965cfe79c9a4fc6f64d1a9c252f93a55dbb71e17bcc957ed34458a43b4
g2_runner_sha256        33d36d6d5488683651012f4dbc241618f50cbbe73bd623445c6e84e7ec1494bc
g2_evaluator_sha256     721bf06e27f88654af2b07049c15e2e299605f2d0b62a51251f0b916118da46f
g1_evaluator_sha256     255ec0f608edff948f6ce5b2fb036d5159d4a49c5dba2d7823b0ef0e62ff3a6e
g0g_evaluator_sha256    99ff575e6968cbd879866a9f9aa9e5db5ec8db97e79080be72a39f969af93dc8
manifest_sha256         af78fcac1e110e964d98a5900d9f79670768513aad75be75438a3d3c6c5f906e
targets_sha256          8b9b8ce10eb5d20bdd64685155e01ed7ff6ffbeef102f6711d9f368d85fee40c
gold_sha256             c64cf34eae90df1e0bfb3e1a7047fdd32eaf0d338898757b7d3f86d6ff8dc933
dev_equivalence         true (byte-identical canonical artifacts vs
                        evidence/g2/dev/runs/001-g21)
audit_amendments        0
```

Baseline CURRENT_OPERATIONAL DEV (§13 reproduced exactly):

```text
positive_binding_assertions 354 (before 182 / after 172)
relations_emitted           519
locator_proven_ops          445
leaf_operation_accounting   100%
FALSE_*                     0/0/0/0
unclaimed_sides             684 -> census debt-census.json
```

## Current state

```text
COV-2A = DONE   (prereg committed 3c82d8f; COV-3 selection STOP
                 recorded at 918a38e; holdout UNMATERIALIZABLE)
COV-2B = DONE   (evaluator frozen + exact baseline reproduced;
                 debt census committed)
COV-2C = DONE   (F1 c4bed51 +75: sub-scope before-binding;
                 F2 ebbfdde +39: tolerant marker enumeration and
                 level-aware candidate regions; 429 -> 468 CURR)
COV-2D = DONE   (final run runs/003-final on frozen HEAD ebbfdde;
                 coverage-delta.jsonl, fixes.jsonl, final-metrics.json,
                 FINAL.md, VERDICT.json generated)

COV-2_DEV        = PASS   (468 >= 443; 519 relations; 445
                           locator-proven; leaf accounting 100%;
                           FALSE_* 0/0/0/0; 520/520 audit PASS;
                           0 amendments)
COV-3_READINESS  = NOT_READY_FOR_COV_3
```
