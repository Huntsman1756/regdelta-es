# PORT-CNMV-0R — Semantic-isolation split remediation

Preregistered amendment to PORT-CNMV-0. The v1 split was
target-level; the unit of blindness must be the set of documents
`reconstruct(T)` will open semantically. `PORT-CNMV-0` remains PASS
as a discovery/corpus gate; its split is `SUPERSEDED_PREOPEN` (no
semantic opening of DEV occurred, so recovery is clean).

```text
BASE
  b5838c1

RUNTIME CHANGES
  0

SEMANTIC OPENING
  forbidden

For every eligible target T define:

  DEP(T) =
      T
      UNION every declared modifier document required by
            reconstruct(T)
      UNION any corrigendum/corrected-instrument document that the
            frozen ownership algorithm would need to inspect

DEP(T) must be derived ONLY from:
  <metadatos>, <analisis>/<referencias>, manifests,
  existing metadata graph. Never from <texto>.

T1 conflicts T2  iff  DEP(T1) ∩ DEP(T2) != ∅

1. Compute connected components of the conflict graph.

2. Any component touching BOE-A-2020-14107 or the prior semantic
   seen-set is excluded from the blind pool (DEV-supporting only,
   never HOLDOUT).

3. Rank remaining components by:
     best_member_stress_rank ASC
     sha256("regdelta-port-cnmv-component-v1|" +
            "|".join(sorted(component_targets))) ASC

4. component rank odd  -> DEV_POOL
   component rank even -> HOLDOUT_POOL

5. Within each pool select the four targets with the best original
   frozen target stress rank.

6. If either side has <4 targets: STOP = INSUFFICIENT_ISOLATED_CORPUS

HARD GATES
  selected DEV targets = 4
  selected HOLDOUT targets = 4
  UNION DEP(DEV) ∩ UNION DEP(HOLDOUT) = ∅
  UNION DEP(HOLDOUT) ∩ SEMANTIC_SEEN_SET = ∅

CHECK
  for every selected target:
      reconstruct_dependency_plan(target)
          == captured semantic dependency set
  (plan operates on metadata only)

OUTPUT
  evidence/port-cnmv/split-v2/
    selection.json
    dependency-sets.json
    conflict-components.json
    dev/manifest.json  (+ raw/)
    holdout/manifest.json (+ raw/)
    holdout/SEAL

  evidence/port-cnmv/holdout/SEAL (v1) stays immutable,
  documented SUPERSEDED_PREOPEN.

TERMINAL
  READY_FOR_ISOLATED_CNMV_PROFILE_PROBE
  |
  INSUFFICIENT_ISOLATED_CORPUS
  |
  ACQUISITION_BLOCKED
```

## Dependency-set semantics (verified against runtime)

`reconstruct(T)` opens, per `history.py`:

- T: diario XML, doc HTML, PDF, annex images.
- each posterior referencia (MODIFICATION or CORRECTION): diario XML,
  and lazily its doc HTML + PDF + images through the same
  `_target_annex_map` path used for the target (modifier annex maps).
- `ownership.resolve_corrected_instrument` reads the corrigendum's
  own doc — already inside DEP via the posterior referencia; no
  additional document is fetched.

So `DEP(T) = {T} ∪ {posterior referencias (modification +
correction)}` over BOE-A ids, and every member needs the full
artifact trio (XML + doc HTML + PDF) plus annex images derived from
its doc HTML.

## Execution record (sealed @ 21543e1)

```text
dependency graph
  56 eligible targets -> DEP sets over posteriores only
  conflict edges: DEP(T1) ∩ DEP(T2) != ∅
  connected components: 12
    - one giant component: 41 targets (multi-target modifier
      chains merge most of the corpus — the v1 alternating
      split was structurally unsound for this graph)
    - 11 remaining components: 4-member + 10 singletons
  seen-excluded components: 0
    (BOE-A-2020-14107 is not eligible — 0 declared modifiers —
     so it never enters the graph; exclusion rule applied vacuously)

component split (frozen rule)
  odd component rank  -> DEV_POOL
  even component rank -> HOLDOUT_POOL
  DEV     = BOE-A-2008-16091, BOE-A-2008-20895,
            BOE-A-2010-13162, BOE-A-1994-28725
  HOLDOUT = BOE-A-2013-6804, BOE-A-2013-6805,
            BOE-A-2011-10830, BOE-A-2017-5084

hard gates (all true)
  dev_targets_eq_4            = true
  holdout_targets_eq_4        = true
  dev_holdout_dep_disjoint    = true   (∪DEP(DEV) ∩ ∪DEP(HOLD) = ∅)
  holdout_dep_seen_disjoint   = true   (∪DEP(HOLD) ∩ seen = ∅)
  dependency_plan_eq_captured = true   (metadata plan == manifest)

capture
  dev     862 artifacts, 0 fetch errors
  holdout 761 artifacts, 0 fetch errors, 116.6 MB aggregate
  per DEP member: diario XML + doc HTML + dias PDF + annex images
  (v1 bytes reused where already captured; sha256 recorded)

SEAL v2
  evidence/port-cnmv/split-v2/holdout/SEAL
  manifest_sha256 7a0ecf78...
  aggregate_sha256 4a9d1caf...
  capture_script_sha256 = committed split_isolation.py @ 21543e1
  sealed_at_head = 21543e1

notes
  - recomputed frozen stress rank asserted == selection.json rank
    (self-checking against drift)
  - former v1 holdout members 2008-20895 / 1994-28725 are now DEV
    (their component ranked odd); former v1 dev 2009-133 /
    2008-19438 landed inside the same giant component but outside
    the top-4 — never semantically opened either way
  - the cross-side contamination flagged at verdict time
    (BOE-A-2018-17708 modifies 2008-20895) is resolved: both now
    sit inside the same DEV-side component

TERMINAL = READY_FOR_ISOLATED_CNMV_PROFILE_PROBE
```

`PORT-CNMV-1` remains gated on explicit authorization; its freeze
list is `profile.py` + all core semantic modules — any need to touch
them is `CORE_EXTENSION_REQUIRED`, not a DEV fix.
