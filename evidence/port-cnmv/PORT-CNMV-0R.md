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
