# PORT — portability architecture preregistration

Status: PREREGISTERED. This document opens the portability
architecture phase. It authorizes structural refactoring under
exact-equivalence discipline. It does not authorize any second
source, any behavioral improvement, or any change to frozen
evidence.

## 1. Gate question

Can all BdE-Circular-specific semantics be isolated behind an
explicit `SourceProfile`, keeping the proven **observable semantics
behaviorally equivalent and the canonical semantic artifacts
byte-identical**, **without transferring factual decisions** from
`binding_proof`/`subject_proof` into the profile? (The core source
itself is of course not byte-identical — code moves.)

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

Equivalence oracle for PORT-2 — two artifact classes, compared
differently. No generic "ignore metadata" normalization: the
volatile set below is an exact whitelist, and every field not on
it compares byte-for-byte.

```text
SEMANTIC_ARTIFACTS          ->  byte-identical
  operations.jsonl
  attribution.jsonl
  subject-outcomes.jsonl
  relations.jsonl
  bindings.jsonl
  binding-sides.jsonl
  lifecycle.jsonl
  continuity.jsonl
  ordering.jsonl
  audit.jsonl
  failures.jsonl
  reconciliation.jsonl
  metrics / cov-metrics canonical payloads
  query / applicability outputs

RUN_ENVELOPE                ->  volatile fields may differ
  volatile whitelist:
    runtime_head
    evaluation_head
    src_tree_sha256
    started_at
    finished_at
    run_id / run path
  all non-volatile envelope fields: identical
  expected post-refactor values of volatile fields are
  explicitly recorded in the PORT-2 report
```

The full test suite must pass unmodified except mechanical import
fixes moved by the refactor itself. Hard gate:

```text
PORT_INTENTIONAL_SEMANTIC_CHANGE_COUNT = 0
```

A single use means the change was not a refactor: `PORT-2 = FAIL`,
`PORT = CORE_COUPLING_EXPOSED`.

## 3. Phases

### PORT-0 — Coupling census (no functional change)

Inventory every BdE-Circular-specific decision currently embedded
in the core: `_CIRCULAR_RE` and target-reference derivation,
state-code families, ordinal grammar, locator kinds
(`norma`/`anejo`/`apartado`/`letra`/`disp`/…), marker patterns and
level-boundary tables, dispositive clause grammar, annex
conventions, issuer/doctype assumptions.

Deliverable: `evidence/port/coupling-census.json` + a reviewable
map. Per coupling item, record at minimum:

```text
symbol / literal / rule
current module
callers
semantic responsibility
BdE-specific evidence
proposed classification:
    PROFILE_MATERIAL
    CORE
    PROFILE_INPUT_CORE_POLICY   (diagnostic only — see below)
why
proof dependency:
    does binding_proof depend on it?
    does subject_proof depend on it?
movement risk:  LOW | MEDIUM | HIGH
fixture coverage
```

`PROFILE_INPUT_CORE_POLICY` is a census-time diagnostic category,
not a third final location. It marks items where vocabulary is
profile material but the enumeration/decision policy is core —
e.g. "enumerate every heading the profile's grammar recognizes and
hand the candidate set to the core": the marker set moves, the
enumerate-then-adjudicate policy does not. PORT-1 must convert
each such item into an explicit interface seam; an item may not
remain in this class at PORT-1 completion.

Items claimed as CORE must justify why they are
source-independent. Zero functional changes; commit as census
only, then STOP for review — the map is the evidence that decides
the PORT-1 interface; it is not designed before the seams are
visible.

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

Frozen rules carried in from the PORT-0 census review:

- **Ownership split**: the profile owns source lexemes, pattern
  data, vocabularies, source identifier syntax, and mappings from
  source forms to core semantic kinds. The core owns the semantic
  kinds/taxonomies and their meaning, canonical emitted spellings,
  enumeration/adjudication policy, and ambiguity/abstention
  policy.
- **Data, not callbacks**: `SourceProfile` is immutable data.
  Parsers/adapters live in the profile *package* (the outer
  composition that converts official bytes into the core's
  node-stream contract), never as functions inside the profile
  object.
- **No profile-injected DDL**: the core owns a source registry fed
  by profile descriptors; the schema does not vary per profile.
- **`canonical_instrument_token`**: supplied by the profile,
  hashed by the core. For BdE it remains byte-for-byte the current
  `boe_id`.
- **Facets, not methods**: the contract should compress the census
  seams into ~5–7 typed data facets (document-model vocabulary,
  locator grammar, operative grammar, identity/reference grammar,
  annex/state grammar, applicability language, source
  descriptors). An interface of callbacks means the census was
  read backwards.

### PORT-2 — Extract BdE profile (hard equivalence gate)

Move the §PORT-0 census items classified as profile material
behind the PORT-1 contract, instantiated as the BdE profile.

PASS criteria (all required):

- Every frozen evidence artifact reproduced byte-identically
  (G0 cohort ledgers, G2 DEV runs, COV-2 `003-final` metrics and
  ledgers).
- Full suite PASS with no expectation changes.
- Profile identity/version may be recorded **only** in the run
  envelope, the profile registry, or diagnostic metadata — never
  inside `binding_proof`, `subject_proof`, representation rows,
  modification_relation rows, `artifact_locator`, or semantic
  evaluator ledgers. It must be possible to know which profile
  produced a run without altering the identity or content of any
  previously emitted fact.
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
