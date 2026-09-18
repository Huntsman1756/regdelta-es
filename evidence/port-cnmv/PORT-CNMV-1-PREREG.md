# PORT-CNMV-1 — Isolated CNMV SourceProfile probe (DEV-only)

Status: PREREGISTERED. This document opens the CNMV portability probe
and authorizes work only under the §5 surface. It does not authorize
any HOLDOUT access, any core change, any merge of
`hardening/public-release`, or any second-source production feature.

## 1. Gate question

Can a second `SourceProfile` — built exclusively from CNMV-published
vocabulary/data and consuming the same BOE `DiarioDoc` node-stream
contract — drive the **unmodified** core over the four PORT-CNMV-0R
DEV targets, without touching any core taxonomy, adjudication policy,
proof rule, or semantic module?

The profile may supply only lexemes, compiled patterns, vocabulary
mappings, and identifier syntax (PORT-1 contract: eight data facets,
zero callbacks). Kinds, meanings, decisions, ambiguity and abstention
remain core-owned. If the DEV corpus can only be handled by giving the
profile (or a boundary adapter) a factual decision, the gate fails by
construction.

## 2. Base, isolation and opening rules

```text
BASE                cdd2079 (main HEAD; PORT-CNMV-0R = READY)
BRANCH/WORKTREE     port-cnmv-1 — exclusively from cdd2079
RUNTIME BASE        src/regdelta @ cdd2079 (tree sha recorded per run)
```

- `hardening/public-release` MUST NOT be merged, cherry-picked or
  rebased into this gate. Its runtime deltas are not part of the
  scientific base. Integration and re-equivalence may only happen
  after this probe is frozen, or under PORT-CNMV-2's own prereg.
- Semantic opening is authorized for
  `evidence/port-cnmv/split-v2/dev/**` only (862 artifacts).
- Forbidden everywhere in this gate: `split-v2/holdout/**`,
  `evidence/port-cnmv/holdout/**` (v1, SUPERSEDED_PREOPEN), and every
  other `*/holdout/*` in the repository — no reads, greps, globs,
  manifest traversal, tests, or tooling that resolves into them.
  SEAL files are integrity anchors, not an opening.
- `BOE-A-2020-14107` is auxiliary-only (already inside the semantic
  seen-set): usable for parser sanity checks and harness debugging,
  never counted in DEV metrics.
- `evidence/port-cnmv/dev/**` (v1 split) is not opened either: only
  the split-v2 DEV set is the corpus of this gate.
- No network access. All bytes come from `split-v2/dev` replayed via
  `FetchResult(via=EVIDENCE_IMPORT)` through the manifest, exactly as
  prior gate evaluators do.

DEV targets (frozen, PORT-CNMV-0R):

```text
DEV = BOE-A-2008-16091, BOE-A-2008-20895,
      BOE-A-2010-13162, BOE-A-1994-28725
HOLDOUT (never opened here) = BOE-A-2013-6804, BOE-A-2013-6805,
      BOE-A-2011-10830, BOE-A-2017-5084
DEP sets: evidence/port-cnmv/split-v2/dependency-sets.json
```

## 3. Frozen oracle and equivalence discipline

- The core `src/regdelta` tree at `cdd2079` is the oracle. Every run
  records `runtime_head`, `src_tree_sha256`, evaluator sha256 and
  manifest sha256 in the run envelope (same envelope convention as
  G1/G2).
- Because the base is unmodified, no equivalence replay against BdE
  evidence is required inside this gate; a single guarded regression
  check (§8) proves the BdE path was not disturbed.
- Historical gate results remain immutable (AGENTS.md). Nothing in
  this gate may edit, reinterpret or replace frozen evidence.

## 4. Hard freeze — `CORE_EXTENSION_REQUIRED` tripwire

Immutable for the whole gate — every file under `src/regdelta/`
**except** new files created under `src/regdelta/profiles/` (§5),
including and not limited to:

```text
profile.py  document.py  operations.py  ownership.py  binding.py
history.py  applicability.py  applicability_parser.py  annexmap.py
diffing.py  query.py  state.py  db.py  evidence_import.py  util.py
http.py  rawstore.py  watcher.py  cli.py  config.py
sources/**  profiles/__init__.py  profiles/bde.py
```

Frozen equally: `LOCATOR_KINDS`, `OP_KINDS`, all emitted status/kind
spellings, the B1–B6 binding policies, the O1–O3 ownership policies,
and every adjudication/abstention rule anywhere in the core.

**Tripwire:** if handling a CNMV construct would require a new
`LocatorKind`, `OperationKind`, status value, context policy, binding
rule, schema field or any other core semantic change, the gate
terminates immediately as `CORE_EXTENSION_REQUIRED` with the need
journaled. It is never fixed inside this gate.

Mechanical enforcement already exists: `validate_profile()` rejects
profiles referencing kinds outside the core registry; a profile that
needs a new kind cannot even register.

## 5. Permitted surface

- NEW `src/regdelta/profiles/cnmv.py` — the CNMV `SourceProfile`
  (data only; validated by `validate_profile` at registration).
- NEW boundary module(s) under `src/regdelta/profiles/` **only if**
  genuinely needed (e.g. `cnmv_boundary.py`): bytes→contract glue
  with no factual decisions. Each boundary module must carry a
  header comment stating why profile data alone was insufficient.
- NEW probe scripts under `scripts/port-cnmv/` (runner, independent
  evaluator, capture/manifest helpers if needed).
- NEW tests under `tests/port-cnmv/` exercising profile loading and
  evaluator mechanics on synthetic fixtures only — no DEV/HOLDOUT
  bytes, no repo evidence paths.
- NEW gate outputs under `evidence/port-cnmv/port-cnmv-1/**`.
- Edits to existing files: NONE outside the new paths above, except
  this prereg's own status/report annotations and the gate journal.

CNMV Circulares are published in the BOE; the existing
`sources/boe_*` document pipeline must keep producing `DiarioDoc`.
No new document parser is authorized.

## 6. Profile loading rule

`profiles/__init__.py` stays untouched — importing
`regdelta.profiles` must still register exactly the BdE profile, and
default (single-profile) resolution must stay unchanged.

The probe runner must instead, in-process:

```text
import regdelta.profiles.cnmv      # explicit, not via the manifest
use_profile("cnmv-circular")       # explicit selection (2 registered)
```

This proves portability without turning the experiment into a
production multi-profile feature. Source-registry rows,
`capture_rules`, `media_types`, `imagen_parser` and
`metadata/relation_mapping` for the CNMV capture layout are supplied
by the profile's `SourceDescriptors` (F8) — that is what makes
`import_manifest`-style replay resolvable without core changes.

## 7. Falsification loop and failure taxonomy

First DEV run uses the minimal viable profile. Every incompatibility
is journaled **before** being fixed:

```text
journal entry:
  symptom                    (what failed, where it stopped)
  minimal_reproduction       (artifact name + sha256 + locator/span)
  classification             PROFILE_DATA_MISSING
                             | BOUNDARY_ADAPTER_MISSING
                             | CORE_EXTENSION_REQUIRED
  fix                        profile-data delta | boundary delta | none
  rerun                      run id re-verifying the fix
```

Only the first two classes authorize changes. `CORE_EXTENSION_REQUIRED`
ends the gate. Per-BOE-ID, per-year, per-Circular or per-target
exceptions/branches are forbidden in profile data, boundary code,
runner and evaluator — any appearance is a gate violation.

The journal lives at
`evidence/port-cnmv/port-cnmv-1/journal.jsonl` and is part of the
frozen evidence of this gate.

## 8. Evaluator contract — independent audit

`scripts/port-cnmv/evaluate_cnmv.py` re-derives, from raw DEV bytes,
the claims the runtime emits. Same independence basis as the G1/G2
evaluators: it may use the core document parser (`boe_diario` →
`DiarioDoc` node stream) and shared lexical primitives; it must
**not**:

- import `regdelta.profiles.*` (any profile), call
  `active_profile()`/`use_profile()`, or read the profile registry;
- import or reuse any pattern, lexeme table or vocabulary defined in
  `profiles/cnmv.py`, `profiles/bde.py`, or the probe runner;
- use runtime-emitted artifacts as oracle — they enter only as the
  claims under test.

```text
EVALUATOR IMPORT FIREWALL

The independent evaluator may import only:
- Python stdlib;
- the canonical document/node data types;
- the BOE raw parser needed to obtain the canonical node stream;
- explicitly enumerated pure utilities that are proven
  profile-independent.

It MUST NOT import, directly or transitively:
- regdelta.profiles.*
- profile registry / active_profile / use_profile
- profile-backed PEP 562 compatibility aliases
- runtime operation/binding/ownership/history helpers whose
  behavior depends on active_profile()
- profile regexes, vocabularies or mappings.

Before evaluator freeze, an import/dependency audit records the
complete transitive project-module dependency set.

Any dependency on profile-owned data:
  EVALUATOR_INDEPENDENCE_BROKEN
  -> gate cannot proceed to PORT-CNMV-2.
```

Minimum independently re-derived claim classes (same decomposition as
the BdE gates so results stay comparable):

```text
O1 OPERATION_TARGETS_INSTRUMENT   ownership/attribution re-derived
                                  from the modifier document
O2 OPERATION_DECLARES_LOCATOR     locator_key composed from the
                                  clause's own lexical scope
BINDING                          before/after binding, chain
                                  predecessor, resolution, verb,
                                  discovery and date claims
                                  (G1 audit shape)
```

Every runtime emission is either CONFIRMED or lands in
`failures.jsonl` with a root-cause class (extend the G2 class set
with `CNMV_EVALUATOR_MODEL_ERROR` and `UNCLASSIFIED`; a failure is
never silently dropped). Evaluator disagreements are adjudicated in
the report; an unconfirmable runtime claim counts as not proven.

Guarded BdE regression check: `import regdelta.profiles` still
registers exactly one profile and the top-level operational tests
that do not require gate evidence still pass — proving the probe did
not disturb the BdE path. No gate-suite replay is required at this
stage.

The evaluator is FROZEN (sha256 recorded in the final run envelope)
before any PORT-CNMV-2 preregistration is written.

## 9. Anti-silence and DEV close criteria

- Operation accounting = 100%: every operative candidate clause is
  either emitted as an operation or explicitly accounted as
  non-operative with its accounting class.
- Zero false facts: no emitted operation/binding/ownership/locator
  claim that the independent evaluator marks false.
- No silent pass: each DEV target must produce at least one
  evaluator-confirmed semantic claim **or** a classified abstention
  with an explicit journal reason. An unexplained zero-emission
  target invalidates the run rather than passing it.
- No preset binding quota. The observed DEV volume is recorded, and
  the positive-evidence rule for PORT-CNMV-2 (e.g. minimum confirmed
  claims per target, chain expectations) is frozen in this gate's
  final report before CNMV-2 is preregistered.

## 10. Outputs

```text
evidence/port-cnmv/port-cnmv-1/
  journal.jsonl                 incompatibilities (§7)
  runs/NNN-<slug>/              run.json metrics.json
                                operations.jsonl attribution.jsonl
                                bindings.jsonl audit.jsonl
                                failures.jsonl report.md
  REPORT.md                     verdict, DEV observed volume,
                                frozen positive-evidence rule for
                                PORT-CNMV-2, abstention register
```

## 11. Terminal states

```text
PORT-CNMV-1 =
    PROFILE_DEV_PASS          profile data/boundary suffice; evaluator
                              confirms DEV; §9 all green
  | PROFILE_LIMIT             profile operates but some CNMV constructs
                              admit only documented abstention (each
                              registered with cause and span)
  | CORE_EXTENSION_REQUIRED   any §4 tripwire hit — recorded, not fixed
  | ISOLATION_BROKEN          any forbidden access detected — gate
                              voided, incident journaled
```

Only `PROFILE_DEV_PASS` authorizes freezing
runner+profile+evaluator and preregistering PORT-CNMV-2 (the
HOLDOUT evaluation). `PROFILE_LIMIT` preregisters a narrower CNMV-2
scope or a redesign; `CORE_EXTENSION_REQUIRED` routes the need to a
future core gate; `ISOLATION_BROKEN` voids all derived results.

## 12. Explicit non-authorizations

- No HOLDOUT access of any kind, on any gate.
- No network fetches; all bytes from `split-v2/dev` replay only.
- No edits to `profiles/__init__.py` or `profiles/bde.py`; no
  production multi-profile feature, CLI flag, or config surface.
- No merge/rebase of `hardening/public-release` or any other branch
  into this gate's base.
- No edits to frozen evaluators (`evaluate_g1.py`, `evaluate_g2.py`,
  `evaluate_dev.py`, sealed runners) — the CNMV evaluator is new code
  and may share only the lexical-primitive role they already share.
- No claims about HOLDOUT performance from DEV results; PORT-CNMV-1
  measures whether the profile *can drive* the core, not coverage.
