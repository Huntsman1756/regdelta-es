# PORT — portability architecture preregistration

Status: PREREGISTERED. This document opens the portability
architecture phase. It authorizes structural refactoring under
exact-equivalence discipline. It does not authorize any second
source, any behavioral improvement, or any change to frozen
evidence.

## 1. Gate question

Can all BdE-Circular-specific semantics be isolated behind an
explicit `SourceProfile`, keeping the proven core
byte-identical/behaviorally equivalent, **without transferring
factual decisions** from `binding_proof`/`subject_proof` into the
profile?

The profile supplies grammar, vocabulary, and identity inputs. The
fail-closed adjudication of what may be claimed stays in the core.
If making the profile work requires the profile to decide binding
outcomes, the gate has failed by construction.

## 2. Frozen oracles

```text
COV_RUNTIME_HEAD   ebbfdde3eb513de05a57d86d004d23ca71e91f59
RESULT_HEAD        e9f1cc3cf4cc0ac7cede600f58ffab1c8d62e105 (v0.3-alpha)
COV-2 FINAL RUN    evidence/cov/cov2/runs/003-final
FULL SUITE         347 PASS @ v0.3-alpha
```

Equivalence oracle for PORT-2: every G0–G2 and COV-2 evidence
artifact reproducible under the pre-refactor runtime must be
reproduced byte-identically by the post-refactor runtime, and the
full test suite must pass unmodified (except imports moved by the
refactor itself — mechanical import fixes are allowed; assertion
or expectation changes are not, except under the existing
`PORT_INTENTIONAL_SEMANTIC_CHANGE` convention, which is expected
to record zero uses).

## 3. Phases

### PORT-0 — Coupling census (no functional change)

Inventory every BdE-Circular-specific decision currently embedded
in the core: `_CIRCULAR_RE` and target-reference derivation,
state-code families, ordinal grammar, locator kinds
(`norma`/`anejo`/`apartado`/`letra`/`disp`/…), marker patterns and
level-boundary tables, dispositive clause grammar, annex
conventions, issuer/doctype assumptions.

Deliverable: `evidence/port/coupling-census.json` + a reviewable
map classifying each item as (a) profile material or (b) genuinely
core. Items claimed as core must justify why they are
source-independent. Zero functional changes; commit as census only.

### PORT-1 — SourceProfile contract (still no code movement)

Define the minimal profile interface following the Batch-2
pattern (`evidence/oss-recon/projects/akn-pt.md`): locator grammar,
ordinal/citation vocabulary, dispositive clause grammar,
target-reference derivation / identifier scheme, state-code
families, doctype assumptions — plus a verified fixture corpus and
a profile-local validation entry point.

Deliverable: `evidence/port/source-profile-contract.md` —
interface signature, packaging shape, and an explicit statement of
what the profile may NOT decide (anything that binds, resolves
ambiguity, or overrides abstention). Reviewable before PORT-2
begins.

### PORT-2 — Extract BdE profile (hard equivalence gate)

Move the §PORT-0 census items classified as profile material
behind the PORT-1 contract, instantiated as the BdE profile.

PASS criteria (all required):

- Every frozen evidence artifact reproduced byte-identically
  (G0 cohort ledgers, G2 DEV runs, COV-2 `003-final` metrics and
  ledgers).
- Full suite PASS with no expectation changes.
- No `binding_proof`/`subject_proof` field gains a profile-origin
  value that was previously core-computed — provenance fields must
  still attribute proof to the core's evidence path; profile
  provenance is recorded as *profile identity/version*, not as a
  factual claim.
- No `if <source>` branching inside the core; the core resolves
  profile objects through the contract only.
- Parser versions unchanged (pure refactor → `cov-v1`/`v5` stay;
  a version bump would itself be evidence of semantic drift).

FAIL: any fact change, any expectation edit, any profile-decided
binding.

## 4. Explicit non-authorizations

- No CNMV (or any second source) work under this gate. The CNMV
  portability probe is a *separate* preregistration that begins
  only after PORT-2 closes PASS — it is the architecture's
  falsification test, not part of its construction.
- No coverage improvement, no debt-class reduction, no tuning.
  The goal is zero behavioral delta, not more.
- No changes to `evaluate_cov2.py` or any frozen evaluator.
- No claim that portability is achieved on PORT-2 PASS alone:
  PORT-2 proves the BdE semantics *can* be isolated; only the
  CNMV probe tests whether the isolation actually ports.

## 5. Terminal states

```text
PORT-0 = DONE | BLOCKED(item, reason)
PORT-1 = DONE | BLOCKED(contract gap)
PORT-2 = PASS | FAIL
PORT   = PROFILE_EXTRACTION_PROVEN | CORE_COUPLING_EXPOSED
```

`CORE_COUPLING_EXPOSED` is a legitimate terminal state: if the
census or extraction shows that some BdE semantics cannot move
behind a profile without altering facts, that finding is the
gate's result and the core/profile boundary is redrawn to include
it — recorded, not worked around.

## 6. Relationship to other gates

- Does not reopen COV-2, COV-3, or the prospective holdout; their
  frozen artifacts are this gate's oracle.
- Historical gate results remain immutable (AGENTS.md).
- The prospective-holdout runtime reference (`ebbfdde`) is
  unaffected: PORT-2's PASS condition is byte-equivalence, so a
  proven-equivalent refactor does not alter what the holdout
  measures — and if it did, PORT-2 would have already failed.
