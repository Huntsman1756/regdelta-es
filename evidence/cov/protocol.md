# COV protocol — representation-binding coverage

## Evidence handling

- `evidence/cov/cov0/` is the frozen debt baseline (pure statistics
  over G2.2 artifacts; no runtime, no verdicts).
- `evidence/cov/exp-b1/`, `evidence/cov/exp-l1/` hold experiment case
  sets and results. Case sets are enumerated mechanically from frozen
  adjudicated artifacts and committed before the candidate rule runs.
- Historical artifacts (`evidence/g0g/**`, `evidence/g1/**`,
  `evidence/g2/**`) are read-only inputs. No bytes are written under a
  future `holdout/` before its seal.
- Stratum classification reads only official `<metadatos>`
  (`vigencia_agotada`, `estatus_derogacion`) from already-captured
  diario XMLs — `CAPTURED_STRUCTURALLY`, never semantic opening.

## Splits

- **DEV**: the G2 semantic seen-set (58 instruments) plus every
  instrument semantically loaded by the G2.2 sealed run. DEV
  equivalence re-runs compare exactly against
  `evidence/g2/g2.2/dev-equivalence/**`.
- **HOLDOUT**: only targets selected under §11 of the PREREG.

## Semantic opening

Unchanged: an instrument becomes semantically seen when its normative
body is parsed by pipeline or evaluator. Index pages,
`posteriores`/`anteriores` metadata, metadatos blocks and eligibility
fetches do not open an instrument.

## Experiments (COV-1)

- `scripts/cov/exp_b1.py`, `scripts/cov/exp_l1.py` — read frozen
  artifacts only. `git diff` on `src/regdelta` stays empty through
  COV-1.
- Verdict spaces are closed: EXP-B1 → `PORT | REJECT`;
  EXP-L1 → `PATTERN_CONFIRMED | REJECT`. No third outcome, no
  retroactive project promotion.

## Evaluation semantics (frozen)

Everything from the G2 evaluator contract carries over unchanged:
O1/O2/O3 claims re-derived evaluator-side, binding invariants B1–B6,
`UNKNOWN` = abstention, never a FALSE_FACT. The reported metric set is
the §5 list — previous aggregates may still be printed for continuity
but carry no gate weight.

## Attempts and immutability

A future COV-3 sealed run is one-shot under the same rules as G2.2:
hash/integrity verification before opening; after opening, runtime,
evaluator, runner, tests, metrics, gold, selection and holdout
evidence are immutable. No second evaluation repairs a failure; any
correction needs a new preregistration and a new unseen holdout.

## Hard gates

```text
FALSE_FACT_COUNT                   = 0
FALSE_BINDING_COUNT                = 0
FALSE_SUBJECT_ATTRIBUTION_COUNT    = 0   (per holdout target)
FALSE_LOCATOR_DECLARATION_COUNT    = 0   (per holdout target)
NON_TARGET_STRATUM_VOLUME          ≥ frozen baseline (DEV equivalence)
TARGET_STRATUM_POSITIVE_ASSERTIONS ≥ preregistered minimum
TARGET_STRATUM_VOLUME              ≥ frozen baseline (DEV equivalence:
                                     relations, locator-proven ops,
                                     leaf accounting = 100%)
PROTOCOL_INTEGRITY                 = PASS
```

## Current state

```text
COV-0 = DONE   (debt baseline frozen — evidence/cov/cov0/**)
COV-1 = OPEN   (preregistration; EXP-B1/EXP-L1 pending)
```
