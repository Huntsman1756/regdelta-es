# COV-3-PROSPECTIVE — preregistration (protocol only)

Status: PREREGISTERED — no gate is open. This document preregisters
the *protocol* for a prospective sealed holdout. It authorizes no
code change, no evaluation run, and no corpus capture. It exists so
that when qualifying material appears, its use is already governed.

## 1. Purpose

COV-2 closed `PASS` on the frozen DEV corpus (354 → 468 CURR
positive bindings, `COV_RUNTIME_HEAD = ebbfdde`). The retrospective
COV-3 selection executed `STOP`: every eligible
CURRENT_OPERATIONAL target had already been semantically consumed
by prior gates. The gain is therefore validated on development
evidence only; **external generalization is not claimed**.

This protocol provides the deferred validation path: a holdout
whose members are *temporally posterior* to the runtime freeze —
material that could not have influenced any tuning decision,
because it did not exist when the runtime was frozen.

## 2. Frozen references

```text
COV_RUNTIME_HEAD   ebbfdde3eb513de05a57d86d004d23ca71e91f59
                   committed 2026-09-16T07:34:17+02:00
RESULT_HEAD        e9f1cc3cf4cc0ac7cede600f58ffab1c8d62e105
                   (v0.3-alpha) — evidence/tests anchors
EVALUATOR          scripts/cov/evaluate_cov2.py @ RESULT_HEAD,
                   sha256 recorded in cov2/EVALUATOR.md
SEALED COV-2 RUN   evidence/cov/cov2/runs/003-final
SEEN-SET           evidence/cov/semantic-seen-set.json @ RESULT_HEAD
T_FREEZE           2026-09-16T07:34:17+02:00
                   (commit timestamp of COV_RUNTIME_HEAD)
```

## 3. Trigger — future observable facts

The holdout materializes only when an observable publication event
after `T_FREEZE` produces a qualifying target. Candidate triggers,
checked against the BdE daily-journal index using **metadata only**
(no semantic reading of new content):

1. A new BdE Circular published after `T_FREEZE` that subsequently
   accumulates declared modifications; or
2. A modification published after `T_FREEZE` to an existing
   instrument, where the modified instrument then satisfies the
   eligibility rule below.

An instrument's presence in `semantic-seen-set.json` does not
exclude it from this holdout for criterion 2: the *modification
event* is new evidence posterior to the freeze. The seen-set
constrains reuse of already-opened *content*, not future events.

## 4. Eligibility rule (unchanged from COV-3)

Identical to the executed COV-3 selection rule, evaluated on
metadata at observation time:

```text
family          = BdE Circular (normative, Banco de España issuer)
strata          = CURRENT_OPERATIONAL | HISTORICAL_PREDECESSOR
                  (same derivation as cov3 selection.json)
eligible        = declared_modifier_count >= 3
                  AND declared modifiers resolvable to BOE ids
```

Same-date modifier clusters and ranking keys are recorded exactly
as `scripts/cov/select_cov3.py` computes them.

## 5. Materialization quorum

The holdout materializes when **≥ 3 eligible CURRENT_OPERATIONAL
targets** have accumulated — the same quorum the retrospective
selection required. Each entry is recorded in
`holdout-manifest.json` (to be created at materialization) with:

- boe_id, titulo, stratum, declared_modifier_count, rank_key
- observation date and the trigger event that admitted it
- source metadata hash (sha256 of the diario XML)

HISTORICAL_PREDECESSOR entries may be captured alongside but do not
count toward the quorum and are evaluated only as the
non-regression stratum.

## 6. Immutability on entry

From the moment an instrument enters `holdout-manifest.json`:

- `COV_RUNTIME_HEAD` is immutable for its evaluation — no runtime
  change, including changes committed *before* materialization but
  after `ebbfdde`, applies.
- `evaluate_cov2.py` is immutable for its evaluation.
- The captured material must not influence any tuning, grammar, or
  profile decision — it is evaluation evidence only.
- Capture follows the sealed-capture policy already used for
  COV-3 discovery (`discovery-raw/` + manifest + hashes); semantic
  content stays sealed until §7 is satisfied.

## 7. Pre-open equivalence requirement

Before any holdout evaluation executes, the sealed runner must
reproduce the frozen baseline: `evaluate_cov2.py` @ RESULT_HEAD
replaying the DEV manifest must regenerate `003-final` metrics
byte-comparably (dev_equivalence semantics as defined in
`cov2/EVALUATOR.md`). If the environment cannot reproduce the
baseline, the holdout stays sealed — the evaluation environment,
not the runtime, is what must be fixed.

## 8. What this validates

- **PASS evidence**: holdout bindings audited by the frozen
  evaluator with `FALSE_* = 0` and binding rates consistent with
  the DEV-hardened runtime → supports (does not prove) that the
  COV-2 mechanisms generalize temporally.
- **Failure handling**: any `FALSE_* > 0`, or a binding collapse
  traceable to grammar assumptions, is a defect report against the
  frozen runtime — it does not reopen DEV tuning; fixes enter only
  through a new preregistered gate.

## 9. Explicit non-authorizations

- This is not COV-4 and opens no development gate.
- No runtime or evaluator modification is authorized by this
  document.
- No new issuer, document family, or jurisdiction is admitted
  here — expanding beyond BdE Circulares requires a separate
  preregistration (portability work may eventually motivate one).
- Discovering that the quorum never materializes is a legitimate
  terminal state: the claim "COV-2 gain is DEV-validated only"
  simply remains standing.

## 10. Relationship to prior gates

- COV-2 verdict (`d66a7ac` artifacts): unchanged — `PASS` on DEV,
  `NOT_READY_FOR_COV_3` under the retrospective rule.
- This protocol changes the COV-3 lineage from "unmaterializable"
  to "deferred-prospective": the readiness state becomes
  `READY_FOR_COV_3_PREOPEN` only when §5 quorum and §7 equivalence
  are both satisfied and recorded.
- Historical gate results remain immutable per AGENTS.md.
