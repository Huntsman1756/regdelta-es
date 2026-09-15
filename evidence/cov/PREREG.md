# COV — Representation-Binding Coverage Preregistration

Gate: `COV-1 — Coverage preregistration & OSS mechanism falsification`
Base: `757eb8e131995b20116512f52e28f060330e3aa7`

Historical states, immutable:

```text
G0-G.2 = FAIL   (73 FALSE_FACT — evidence/g0g/**)
G1.2   = FAIL   (4 FALSE_FACT, 0 FALSE_BINDING — evidence/g1/g1.2/**)
G2.0   = STOP   (CORRIGENDUM_CHAIN eligible = 0 — evidence/g2/**)
G2.0b  = PASS   (event-centric discovery; 4 targets sealed)
G2.2   = PASS   (sealed one-shot evaluation — evidence/g2/g2.2/**)
```

No historical verdict is edited, reinterpreted or replaced.

## 1. Question

> ¿Puede RegDelta aumentar el número de positive
> representation-binding assertions demostrables desde evidencia
> oficial, manteniendo exactamente los gates de precisión de G2 y sin
> obtener la mejora mediante mayor abstención en otros estratos?

Priority:

```text
FALSE_* = 0  >  positive assertion growth  >  aggregate rates
```

This gate does NOT ask "improve coverage" in the abstract. It asks for
more *proven* assertions on the stratum that carries operational
weight, purchased only with better evidence use — never with relaxed
precision or shifted abstention.

## 2. Baseline (COV-0, frozen at 12ca25a)

Debt ownership over the frozen G2.2 artifacts:

```text
sealed   604 journal entries   representation-binding-evidence 566 (93.7%)
dev      807 journal entries   representation-binding-evidence 773 (95.8%)
```

All other problems (version-chains, amendment-actions,
evidence-capture) together own < 7% of journaled debt. The dominant
debt is binding claims never made or never provable — not false
claims. The gate therefore measures assertion growth, not error
reduction.

## 3. Regime strata (mechanical, frozen)

Each evaluated instrument is classified from the official diario
`<metadatos>` of its own captured XML (metadata read — not semantic
opening):

```text
HISTORICAL_PREDECESSOR   vigencia_agotada = S OR estatus_derogacion = S
CURRENT_OPERATIONAL      otherwise
```

Frozen classification of the 20 adjudicated targets:

| target | circular | vigencia_agotada | estatus_derogacion | stratum | split |
|---|---|---|---|---|---|
| BOE-A-2004-21845 | 4/2004 | S | S (2018-01-01) | HISTORICAL_PREDECESSOR | sealed |
| BOE-A-2008-9915 | 3/2008 | N | N | CURRENT_OPERATIONAL | sealed |
| BOE-A-2016-5203 | 5/2016 | N | N | CURRENT_OPERATIONAL | sealed |
| BOE-A-2019-15683 | 3/2019 | N | N | CURRENT_OPERATIONAL | sealed |
| BOE-A-2005-4749 | 2/2005 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2010-12488 | 4/2010 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2010-15521 | 6/2010 | S | S (2020-10-15) | HISTORICAL_PREDECESSOR | dev |
| BOE-A-2010-1824 | 1/2010 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2011-2378 | 1/2011 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2012-3169 | 2/2012 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2012-9058 | 5/2012 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2013-5720 | 1/2013 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2013-7467 | 2/2013 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2014-1183 | 2/2014 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2016-1238 | 2/2016 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2016-4356 | 4/2016 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2017-14334 | 4/2017 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2019-17286 | 4/2019 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2021-19805 | 4/2021 | N | N | CURRENT_OPERATIONAL | dev |
| BOE-A-2021-21220 | 5/2021 | N | N | CURRENT_OPERATIONAL | dev |

Stratum assignment for future targets uses the same rule against
their captured official metadatos at seal time.

## 4. Two tracks — never pooled

**Coverage operativo** (`CURRENT_OPERATIONAL`) is the KPI of this
gate. Instrumentos/regímenes relevantes para normativa vigente.

**Historical portability** (`HISTORICAL_PREDECESSOR`) serves historical
reconstruction and the future grammar-profile abstraction. Its metrics
are reported in full but never enter the operational denominator, and
its improvement is never required for the operational claim — nor may
it regress (§9).

Rationale, from §3 + COV-0: the sealed split's debt is 85%
concentrated in the single historical target (Circular 4/2004: 516 of
604 entries); the DEV split's debt is 99.6% operational (Circular
4/2017 alone: 458). A pooled denominator would let either stratum
silently dominate the other.

## 5. Frozen metrics (replace previous aggregates)

Unit definitions:

```text
leaf operation        runtime-parsed leaf amendment operation
assertion             one (modification_relation, side) pair,
                      side ∈ {before, after}
positive assertion    assertion whose evaluator verdict is
                      BINDING_CORRECT (re-derived, never the
                      runtime's own claim)
```

Metrics:

```text
leaf_operation_accounting      integrity invariant per
                               (target, modifier):
                               parsed_leaf_ops == Σ O1 dispositions.
                               Reported as accounted/total; not a
                               coverage rate. Required: full
                               accounting.

subject_locator_proof_rate     TARGET_PROVEN ops with ≥1 PROVEN
                               locator declaration / TARGET_PROVEN
                               ops  (O2 ledger over O1 survivors)

relation_emission_rate         emitted modification_relations /
                               TARGET_PROVEN leaf ops
                               (may exceed 1: multi-locator ops)

positive_binding_assertions    count of BINDING_CORRECT over
                               relation × side

representation_binding_coverage  positive_binding_assertions /
                               (2 × emitted relations)

chain_proof_coverage           CHAIN_PROVEN hops / declared chain
                               hops (the metric formerly reported
                               as chain_reconstruction)

FALSE_FACT                     contradicted factual claim
FALSE_BINDING                  contradicted binding claim
FALSE_SUBJECT_ATTRIBUTION      relation emitted for an operation
                               whose O1 is unproven/false
FALSE_LOCATOR_DECLARATION      emitted locator not in the
                               evaluator-derived expected set
```

## 6. Frozen baseline (from `evidence/g2/g2.2/**`)

| split | stratum | leaf | TP | locator-proven ops | rels | pos. assertions | rep_binding_cov | chain |
|---|---|---|---|---|---|---|---|---|
| sealed | CURRENT_OPERATIONAL | 46 | 40 | 35 | 42 | 9 (3+6) | 9/84 = 0.107 | 0/6 |
| sealed | HISTORICAL_PREDECESSOR | 438 | 253 | 165 | 244 | 63 (11+52) | 63/488 = 0.129 | 3/39 |
| dev | CURRENT_OPERATIONAL | 1266 | 481 | 445 | 519 | 354 (182+172) | 354/1038 = 0.341 | 11/63 |
| dev | HISTORICAL_PREDECESSOR | 16 | 1 | 1 | 1 | 0 (0+0) | 0/2 | 0/0 |

The DEV equivalence split is the exact-comparison surface: identical
corpus, identical evaluator contract, so every delta is attributable.
The sealed baseline calibrates expectations but is not a same-corpus
comparator for a future holdout.

## 7. OSS record carried into this gate (verbatim)

```text
words-to-data @ ccc44e0:
  project verdict            = PATTERN
  redesignation pairing      = PORT_CANDIDATE_PENDING_EXPERIMENT
  (LLM amendment pipeline    = negative result, non-reproducible)

indigo @ 652e58f:
  project verdict            = PATTERN
  same-date ordering         = PATTERN_CANDIDATE_PENDING_EXPERIMENT
```

No retroactive promotion: one promising mechanism does not make a
project `PORT`. Per `oss-recon/RUBRIC.md` rule 2, this preregistration
is the only door through which either mechanism can enter — and only
after its frozen experiment passes. Batch 2 (`leos`,
`legaldocml-akn`, `akn-pt`) is deferred to the jurisdiction-profile /
portability gate before CNMV; its recon question is orthogonal to
coverage.

## 8. Frozen experiments (G3-stage: no runtime changes)

Both experiments run over already-adjudicated frozen DEV artifacts
(`evidence/g2/g2.2/dev-equivalence/**`, `evidence/g2/dev/**`).
Implementations live under `scripts/cov/`; results under
`evidence/cov/exp-*/`. `git diff base..HEAD -- src/regdelta` must be
empty at COV-1 close.

### EXP-B1 — redesignation-aware pairing

Candidate mechanism (observed in words-to-data `src/diff/mod.rs` +
`src/link.rs`, algorithm only — not its pipeline, USLM model or
assumptions): consult demonstrated redesignation/continuity edges
*before* positional pairing when matching subjects across versions.

Hypothesis: on adjudicated renumbering cases ("pasa a ser
apartado/letra X", enumerator renumberings, anejo↔norma moves),
redesignation-first pairing improves `chain_proof_coverage` /
positive binding without introducing any `FALSE_*`.

Case set: enumerated mechanically from the frozen artifacts
(operations + audit/lifecycle/reconciliation ledgers) into
`evidence/cov/exp-b1/cases.json` *before* the pairing rule runs.

```text
PASS  continuity preserved for every adjudicated renumbering case;
      zero false delete+add merges; zero pairings the proven O1/O2
      ledger did not prove
FAIL  any false continuity (two distinct subjects merged) or any
      lost continuity the adjudicated ledger proves

verdict space:  PORT | REJECT
```

`PORT` authorizes porting the *pairing rule* during COV-2 — nothing
else of the project enters.

### EXP-L1 — same-date lifecycle ordering

Candidate rule (observed in indigo `Amendment.order_further`): order
same-date amendments by (amendment date, amending work date, subtype,
natural-sorted number).

Replay against already-adjudicated same-date hop cases from the
frozen G2.1 DEV chain ledger (modifier pairs on one target sharing
`publication_date`).

```text
PASS  the rule reproduces the adjudicated ordering for every case,
      or flags a case as genuinely ambiguous (no source-declared
      order) instead of silently reordering it
FAIL  the rule contradicts an adjudicated case, or imposes an order
      the source never declared

verdict space:  PATTERN_CONFIRMED | REJECT
```

`PATTERN_CONFIRMED` is not adoption of indigo — it licenses the
ordering rule as a deterministic prior to be re-proven per case.

## 9. Gate conditions — all three simultaneous

```text
1. FALSE_FACT = FALSE_BINDING = FALSE_SUBJECT_ATTRIBUTION =
   FALSE_LOCATOR_DECLARATION = 0   (every evaluated target)

2. NO VOLUME REGRESSION on non-target strata vs the frozen §6
   baseline: on the DEV equivalence re-run, for each stratum not
   declared improvement-target —
     relations emitted          ≥ baseline
     positive_binding_assertions ≥ baseline
     locator-proven ops          ≥ baseline
   and leaf_operation_accounting still holds globally. Improvement
   may not be purchased by increased abstention anywhere.

3. MINIMUM IMPROVEMENT on the target stratum
   (CURRENT_OPERATIONAL, DEV equivalence — exact same-corpus
   comparison), with target-stratum anti-abstention floors — the
   improvement may only come from converting existing/unproven
   claims into proven bindings, never from shrinking the factual
   surface:

     positive_binding_assertions ≥ 443   (= ceil(354 × 1.25); ≥ +89
                                          assertions, ≥ +25%,
                                          ≥13% of the 684 currently
                                          unclaimed CURR slots)
     relations_emitted           ≥ 519
     locator_proven_ops          ≥ 445
     leaf_operation_accounting   = 100%
```

Statistical floor (frozen before runtime): a capability may not claim
validated precision below the preregistered n. For a Wilson 95% upper
bound ≤ 5% with zero observed errors, n ≈ 73 independent positive
assertions. Consequence for the sealed stage:

```text
sealed positive_binding_assertions ≥ 73   required for the
precision-validated claim ceiling; below that the run is reported
honestly but the claim drops to "measured, n < 73 — precision not
validated at 95%/5%"
```

Assertions are counted at `relation × side`; the two sides of one
relation are correlated evidence. The n-floor therefore additionally
requires ≥ 37 distinct relations contributing — reported alongside.

## 10. Sequence

```text
COV-1  this prereg + EXP-B1 + EXP-L1 + stratum denominators
       (NO runtime changes; empty src diff)     <- THIS GATE
COV-2  DEV coverage hardening on representation-binding evidence;
       dev-equivalence re-run vs §6 baseline; anti-hardcoding guard;
       freeze runtime + evaluator
COV-3  fresh sealed adversarial holdout (§11), one-shot
```

An experiment's `REJECT` does not stop the gate — it removes one
mechanism from the COV-2 toolbox. `PORT`/`PATTERN_CONFIRMED` outcomes
enter COV-2 scope only via this prereg.

## 11. COV-3 holdout — stress design (frozen intent)

Selection is mechanical, metadata-only, over never-seen BdE Circular
targets (`rango` 1390, `departamento` 1020) of the frozen index corpus
+ G2.0b relation graph, excluding the seen-set extended with every
instrument semantically loaded by the G2.2 sealed run.

```text
eligible   declared_modifier_count ≥ 3 (official posteriores bearing
           MODIFICA|DEROGA|SUPRIME|AÑADE|SUSTITUYE over T)
strata     assigned BEFORE selection via §3 metadata rule
rank       within each stratum: declared_modifier_count DESC,
           same_date_modifier_cluster_count DESC   (distinct
           publication dates with ≥2 declared modifiers — the EXP-L1
           stress axis),
           sha256("regdelta-cov-v1"|boe_id) ASC

allocation (75% of holdout power to the operational objective):
  require ≥ 3 fresh CURRENT_OPERATIONAL eligible targets
  select   top 3 CURRENT_OPERATIONAL
  if ≥1 HISTORICAL_PREDECESSOR eligible:
      select top 1 HISTORICAL_PREDECESSOR
  else:
      select top 4th CURRENT_OPERATIONAL

  if CURRENT_OPERATIONAL eligible < 3 → STOP
  (same rule family as G2.0b; no relaxation after identities are
  known)
```

## 12. Anti-hardcoding & invariants

- `new target-specific runtime literals = 0` vs
  `evidence/g2/runtime-literals-baseline.json` (existing guard
  extended into COV-2).
- No operation-level or instrument-specific patches in runtime,
  evaluator, tests or gold.
- Semantic seen-set discipline unchanged; `CAPTURED_STRUCTURALLY !=
  SEMANTICALLY_SEEN`.
- G1 binding claims (B1–B6) and the G2 evaluator contract are
  preserved verbatim; a contradicted `PRESENT`/`ABSENT`/`DELETED`
  lifecycle assertion remains `FALSE_FACT`; `UNKNOWN` remains
  abstention.
- Sealed run stays one-shot: hash/integrity checks before opening;
  after opening, runtime, evaluator, runner, tests, metrics, gold,
  selection and holdout evidence are immutable.

## 13. Claim ceiling

If COV-3 passes with n ≥ 73:

> "On a fresh sealed BdE corpus enriched for amendment density and
> same-date modifier stress, RegDelta emits N positive
> representation-binding assertions proven from official evidence,
> with zero false facts, false bindings, false subject attributions
> and false locator declarations, and no volume regression on
> non-target strata."

Never claimed: complete amendment recall, full legal consolidation,
all BdE circulars covered, historical portability at operational
grade, production completeness.
