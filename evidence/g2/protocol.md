# G2 protocol — subject ownership & lifecycle integrity

## Evidence handling

- `evidence/g2/discovery-raw/` holds posterior-instrument diario XMLs
  fetched for eligibility classification only. They are
  CAPTURED_STRUCTURALLY (metadata: `anteriores`/`metadatos`), never
  semantically parsed, and sha256-committed inside `candidates.json`.
- No bytes are written under `evidence/g2/holdout/` while the gate is
  in STOP state.
- Historical artifacts (`evidence/g0g/**`, `evidence/g1/**`) are
  read-only. The G1.2 `VERDICT.json` keeps its original fields.

## Splits

- **DEV**: everything in `semantic-seen-set.json` (58 instruments),
  including the 12 G0-G targets, the 3 opened G1 holdout targets and
  every G1.2 modifier.
- **HOLDOUT**: only targets selected under §12 of the PREREG. Under
  STOP no holdout exists.

## Semantic opening

An instrument becomes semantically seen when its normative body is
parsed by the pipeline or evaluator. Index pages, `posteriores`/
`anteriores` metadata, consolidada probes and eligibility fetches do
not open an instrument.

## Discovery semantics

Mechanical, reproducible, official-metadata only:

1. `semantic-seen-set.json` ← `scripts/g2/build_seen_set.py`.
2. `candidates.json` + `selection.json` ← `scripts/g2/discover_g2.py`.
   Per posterior instrument: repo XML → discovery-raw cache → one
   live fetch persisted for byte-stable reruns.
3. `runtime-literals-baseline.json` ← `scripts/g2/gen_baseline_g2.py`.

## Evaluation semantics (frozen for a future sealed gate)

Per emitted relation the evaluator checks independently:

- `OPERATION_TARGETS_INSTRUMENT` (O1) — false or unproven emission ⇒
  `FALSE_SUBJECT_ATTRIBUTION`.
- `OPERATION_DECLARES_LOCATOR` (O2) — mis-declared/mis-composed
  locator ⇒ `FALSE_FACT` (`RUNTIME_WRONG_LOCATOR`).
- `SUBJECT_EXISTENCE_BEFORE` (O3) — `PROVEN_*` contradicted by
  evidence ⇒ `FALSE_FACT`; `UNKNOWN`/`NOT_APPLICABLE` = abstention.
- `binding_proof` invariants B1–B6 unchanged from G1.
- `locator absent from original target XML` alone is never a
  FALSE_FACT.

## Metrics (reported, no post-hoc thresholds)

Attribution distribution, locator-declaration distribution,
existence_before distribution, lifecycle coverage, binding/chain
distributions, abstentions — all reported honestly.

## Attempts and immutability

A future sealed run is one-shot: hash/integrity verification is
allowed before opening; semantic parsing, runtime execution against
fresh targets, gold scoring or manual inspection opens the holdout.
After opening, runtime, evaluator, runner, tests, metrics, gold,
selection and holdout evidence are immutable. No second evaluation
repairs a failure; any correction needs a new preregistration and a
new unseen holdout.

## Hard gates

```text
FALSE_FACT_COUNT                 = 0
FALSE_BINDING_COUNT              = 0
FALSE_SUBJECT_ATTRIBUTION_COUNT  = 0   (per holdout target)
PROTOCOL_INTEGRITY               = PASS
```

## Current state

```text
G2.0 = STOP at selection (CORRIGENDUM_CHAIN: 0 eligible < 2).
No holdout, no seal, no runtime change. G2.1 not started.
```
