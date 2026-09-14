# G2 — Subject Ownership & Lifecycle Integrity Preregistration

Gate: `G2.0 — Subject Ownership & Lifecycle Preregistration`
Base: `1f0c1fc62996f4941be00210a261b7da68b53630`

Historical states, immutable:

```text
G0-G.2 = FAIL   (73 FALSE_FACT — evidence/g0g/**)
G1.2   = FAIL   (4 FALSE_FACT, 0 FALSE_BINDING — evidence/g1/g1.2/**)
```

G1.2 remains recorded exactly as:

```text
PROTOCOL_INTEGRITY = PASS
FALSE_BINDING_GATE = PASS
FALSE_FACT_GATE    = FAIL
```

Neither verdict is edited, reinterpreted or replaced.

## 1. Question

> ¿Puede RegDelta atribuir cada operación y cada subject al instrumento
> jurídico correcto y representar honestamente la existencia temporal
> del locator, sin exigir que todos los subjects aparezcan en la
> publicación original del target ni propagar al target disposiciones
> locales de un modificador/corrigendum?

Priority:

```text
correct ownership + honest lifecycle > relation coverage
```

## 2. Motivation

G1 solved the dominant binding problem (`FALSE_BINDING = 0`, B1–B6
clean) but left four `FALSE_FACT` on `target_locator_resolves`
(BOE-A-2012-9058). The G1 evaluator conflated three distinct claims:

- the operation belongs to the target instrument;
- the operation declares that locator;
- the subject already existed in the target's original publication.

`target_locator_resolves: CONTRADICTED` is therefore NOT equated with
"runtime locator parser wrong". Admissible root-cause classes:

```text
A) WRONG_OWNER
B) HISTORICALLY_BORN_SUBJECT
C) CORRIGENDUM_LOCAL_SUBJECT
D) MULTI_TARGET_MISATTRIBUTION
E) LOCATOR_PARSER_FAILURE
F) EVALUATOR_MODEL_FAILURE
```

## 3. Three claims (O1/O2/O3)

`target_locator_resolves` is conceptually removed and replaced by:

- **O1 — `OPERATION_TARGETS_INSTRUMENT`**: does this operation belong
  to the target being reconstructed?
- **O2 — `OPERATION_DECLARES_LOCATOR`**: does the operative clause
  factually/structurally identify that locator? (True even if absent
  from the original publication.)
- **O3 — `SUBJECT_EXISTENCE_BEFORE`** ∈ `{PROVEN_PRESENT,
  PROVEN_ABSENT, UNKNOWN, NOT_APPLICABLE}`. `UNKNOWN` is abstention,
  never a FALSE_FACT.

## 4. Re-adjudication of the four G1.2 cases

`evidence/g2/root-cause/g1-four-cases.json` — frozen before any
runtime change. Fields per case: `old_relation_id`, `target`,
`modifier`, `locator_key`, `operation_kind`, `old_g1_verdict`,
`operation_owner`, `owner_evidence`, `operation_declares_locator`,
`locator_evidence`, `subject_existence_before`, `lifecycle_evidence`,
`new_root_cause`. Outcome vocabulary (§25):

```text
RUNTIME_WRONG_TARGET_ATTRIBUTION | RUNTIME_WRONG_LOCATOR |
VALID_CHAIN_BORN_LOCATOR | G1_EVALUATOR_MODEL_ERROR | OTHER
```

Result: 2 × RUNTIME_WRONG_TARGET_ATTRIBUTION (corrigendum-local
subjects of Circular 2/2019 pushed onto 5/2012 via the downstream
CORRIGE relation) + 2 × RUNTIME_WRONG_LOCATOR (anejo-scoped clauses
of Norma tercera mis-composed under a stale `norma:11` context).

## 5. Corrigendum rule

```text
corrigendum owner = instrument identified by the official
correction relation (anteriores CORRIGE / ELI corrects)
```

A secondary BOE relation (`CORRIGE errores en TARGET`) does not make
each provision of the corrigendum a subject of TARGET. An operation
propagates to a downstream target only when the operative clause
explicitly demonstrates that target. `corrigendum-local provision !=
target subject` absent explicit contrary evidence.

## 6. Multi-target modifiers

Each operation receives independent attribution. Forbidden:

- `section belongs to A → every op in document belongs to A`;
- `modifier appears in TARGET.posteriores → every parsed subject
  belongs to TARGET`.

Section-level inheritance only when the heading/preamble identifies
an unambiguous target set; explicit per-operation target prevails.
`candidate count = 0 → NOT_PROVABLE`; `> 1` without narrower scope →
`AMBIGUOUS`. The target passed to `reconstruct()` never breaks ties.

## 7. TargetAttribution (closed taxonomy)

```text
TARGET_PROVEN | FOREIGN_TARGET | MODIFIER_LOCAL |
AMBIGUOUS | NOT_PROVABLE
```

```json
{"status": "TARGET_PROVEN", "method": "...",
 "candidate_instruments": [], "chosen_instrument": "...",
 "section_evidence": null, "clause_evidence": null,
 "corrigendum_owner": null}
```

Only `TARGET_PROVEN` authorizes a `modification_relation` against the
target. Other states emit no target relation; they may persist as
anomaly/diagnostic records plus `instrument_relations`.

Attribution methods (closed):

```text
EXPLICIT_CLAUSE_TARGET | EXPLICIT_SECTION_TARGET |
UNIQUE_SECTION_INHERITANCE | CORRIGENDUM_CORRECTED_INSTRUMENT |
CORRIGENDUM_EXPLICIT_DOWNSTREAM_TARGET
```

Never sufficient as proof: `TARGET_FROM_POSTERIORES_ONLY`,
`TITLE_MENTIONS_TARGET`, `DEFAULT_CURRENT_TARGET`.

## 8. SubjectLifecycle (closed taxonomy)

Temporal state per `(target instrument, locator_key)`:

```text
PRESENT | ABSENT | DELETED | UNKNOWN
```

Initial state at original-publication load: `PRESENT` if structurally
proven; `ABSENT` only if provably absent AND the textual source is
exhaustive for that locator kind; else `UNKNOWN`. Never
`not found in XML == ABSENT` universally.

Transitions (minimum set):

```text
ADD        UNKNOWN/ABSENT -> PRESENT   (subject identity proven)
DELETE     PRESENT -> DELETED
           UNKNOWN -> DELETED as declared operation state only;
                      prior existence remains UNKNOWN
SUBSTITUTE subject identity proven -> PRESENT
             (representation may stay unbound)
MODIFY     PRESENT -> PRESENT ; UNKNOWN -> UNKNOWN
```

Subject existence and representation existence are distinct states:
`representation UNKNOWN` does not imply `subject UNKNOWN` when an
official operation proves the locator exists. A chain-born locator
(`ADD locator X` correctly attributed) makes a later operation's
`SUBJECT_EXISTENCE_BEFORE(X) = PROVEN_PRESENT` even though X was
absent from the original publication — the proof must say so.

## 9. SubjectProof (concept, frozen)

Separate from `binding_proof`; answers: (1) why does this operation
belong to this target? (2) why is this locator the subject? (3) what
is known of its existence immediately before the operation?

```json
{"version": "g2-subject-v1",
 "target_attribution":  {"status": "TARGET_PROVEN",
                         "method": "EXPLICIT_SECTION_TARGET",
                         "candidate_instruments": [],
                         "chosen_instrument": "..."},
 "locator_declaration": {"status": "PROVEN",
                         "source_span": [],
                         "method": "EXPLICIT_CLAUSE_LOCATOR"},
 "existence_before":    {"status": "PRESENT|ABSENT|DELETED|UNKNOWN|NOT_APPLICABLE",
                         "method": "...",
                         "predecessor_relation_id": null}}
```

G2.0 changes no schema. G2.1 prefers
`modification_relations.subject_proof` (canonical JSON); a schema
change runs only after showing the concept cannot be expressed
auditably with existing columns.

## 10. Emission rule

A target-level `modification_relation` persists iff:

```text
target_attribution.status == TARGET_PROVEN
AND locator_declaration.status == PROVEN
```

`existence_before == PRESENT` is NOT required — an official
declaration materializes honestly with `existence_before = UNKNOWN`.
For `FOREIGN_TARGET | MODIFIER_LOCAL | AMBIGUOUS | NOT_PROVABLE`: no
target relation; diagnostics `OPERATION_TARGET_NOT_THIS_INSTRUMENT` /
`OPERATION_TARGET_AMBIGUOUS` / `OPERATION_TARGET_NOT_PROVABLE`;
instrument-level facts stay in `instrument_relations`.

## 11. Semantic seen-set

`evidence/g2/semantic-seen-set.json` (script:
`scripts/g2/build_seen_set.py`), mechanical: the 47-instrument G1
set + the 3 former G1 holdout targets + every instrument loaded by
the G1.2 sealed evaluator/runtime (gold declared modifiers, relation/
failure/audit artifact ids). 58 instruments.
`CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN` unchanged.

## 12. Fresh holdout — stress variable and universe

G2 selects on **subject-ownership risk**, not amendment density, over
never-seen targets of the frozen G0-G.0 index corpus
(`evidence/g0g/candidates.json`, index sha
`5ec993cd…cec36`):

- **CORRIGENDUM_CHAIN**: T has a posterior corrigendum M whose own
  `anteriores` prove M officially corrects ANOTHER instrument while T
  appears in M's relations (downstream).
- **MULTI_TARGET_MODIFIER**: T has a non-correction posterior modifier
  M whose `anteriores` identify ≥ 2 distinct modified instruments.

Derivation is metadata-only (`posteriores`/`anteriores`/`metadatos`);
no operation parsing for selection. Posterior-instrument diario XMLs
absent from the frozen repo are fetched into
`evidence/g2/discovery-raw/` and hashed in `candidates.json` —
metadata fetches for eligibility are CAPTURED_STRUCTURALLY, not
semantic opening. Script: `scripts/g2/discover_g2.py`.

Selection (§28): per group `risk_event_count DESC`,
`declared_modifier_count DESC`,
`sha256("regdelta-g2-v1"|boe_id) ASC`; top 2 of
`CORRIGENDUM_CHAIN` + top 2 of `MULTI_TARGET_MODIFIER`. Dual
membership assigns to the higher-risk group (tie → hash). Any group
with < 2 eligible → `STOP G2.0`; no relaxation after identities are
known.

## 13. G2.0 outcome: STOP on selection

```text
CORRIGENDUM_CHAIN    eligible = 0   -> STOP
                     (3 corrigenda exist on unseen candidates —
                     BOE-A-2022-6051, BOE-A-2016-5532,
                     BOE-A-2016-4282 — but each one's anteriores
                     prove it corrects ONLY its own target; no
                     downstream-registration chain exists)
MULTI_TARGET_MODIFIER eligible = 4
                     BOE-A-2016-5203, BOE-A-2019-15683,
                     BOE-A-2010-18686, BOE-A-2022-1718
```

Per §28 the gate stops: **no fresh holdout is formed, nothing is
sealed, G2.1 does not start.** The frozen index corpus contains no
unseen target carrying a corrigendum-chain relation. Per §29, only
after this recorded STOP may an amendment preregister a corpus
extension (e.g. a broader index or a corrected-instrument-side
discovery direction); that is a separate preregistration, not a
relaxation of this one.

## 14. Deferred deliverables (only on a non-STOP rerun)

Defined now so any future amendment executes them verbatim:

- **Capture** (content-agnostic): target XML, modifier XMLs,
  corrigenda XMLs, doc/txt/PDF, enumerable images, consolidada probes,
  ELI `corrects` metadata → `holdout/manifest.json` + `holdout/raw/**`.
- **Ownership gold** `gold/instrument_ownership.json`: strictly
  instrumental mechanical facts (corrigendum corrects X; modifier
  declares target set; target posteriores; reverse anteriores). No
  manual per-operation labels — that adjudication belongs to the
  sealed evaluator.
- **SEAL** `holdout/SEAL` commits: targets, selection sha,
  semantic-seen-set sha, manifest sha, aggregate sha, capture-script
  sha, ownership-gold sha, base HEAD. Immutable after sealing.

## 15. Future evaluator contract (frozen)

Per relation, verify independently: target attribution, locator
declaration, subject lifecycle before, before/after binding,
resolution, chain. `FALSE_SUBJECT_ATTRIBUTION_COUNT = 0` joins
`FALSE_FACT_COUNT = 0` and `FALSE_BINDING_COUNT = 0` per holdout
target: a target-level relation emitted for an operation/subject
whose target membership is unproven or false. Lifecycle has no
coverage threshold, but a contradicted `PRESENT`/`ABSENT`/`DELETED`
assertion is a FALSE_FACT; `UNKNOWN` is abstention. Forbidden:
`locator absent from original target XML → FALSE_FACT` — the original
publication is state at t0, not the permanent subject universe.

## 16. Regressions and sequence

`evidence/g2/dev/g1-four-false-facts.json` + the 73-case G0 corpus
are the DEV regressions; after re-adjudication the future hard
requirements are `G0_OLD_FALSE_FACT_REPRODUCTION = 0` and
`G1_FALSE_FACT_REPRODUCTION = 0`.

```text
G2.0  discovery + re-adjudication + fresh selection + seal
      (NO runtime changes)            <- THIS GATE: STOP at selection
G2.1  fix ownership/lifecycle on all seen targets; G0 73-case +
      G1 4-case regressions; freeze runtime + evaluator
G2.2  fresh sealed one-shot evaluation
```

Claim ceiling if a future G2.2 passes: "Subject ownership, locator
declaration and structural binding integrity are supported on a fresh
sealed BdE corpus enriched for corrigendum-chain and multi-target
amendment risk, with measured lifecycle coverage and fail-closed
abstention." Never claimed: full legal consolidation, complete
amendment recall, all BdE circulars covered, production complete.

## 17. Hard gates and verdict contract

```text
G0/G1 historical FAILs preserved
4 G1 cases re-adjudicated under O1/O2/O3
ownership vs lifecycle claims frozen
TargetAttribution / SubjectLifecycle / SubjectProof frozen
semantic seen-set reproducible
fresh ownership-risk candidates selected mechanically
4 fresh targets available + holdout sealed + ownership gold frozen
hard gates frozen; anti-hardcoding green; full suite green
git diff base..HEAD -- src/regdelta = empty
```

`VERDICT.json` contract correction (learned from G1.2, whose
`runtime_head` recorded the evaluation head): future verdicts carry
three distinct fields — `runtime_head`, `evaluation_head`,
`src_tree_sha256`. The G1.2 artifact itself is NOT edited.

## 18. Anti-hardcoding

`new target-specific runtime literals = 0` vs
`evidence/g2/runtime-literals-baseline.json` (guard:
`tests/g2/test_no_new_target_specific_code.py`). No operation-level
or instrument-specific patches may be added to runtime, evaluator,
tests or gold.

## 19. G2.0 status

```text
G2.0 = STOP   (CORRIGENDUM_CHAIN eligible = 0 < 2 in the frozen
               corpus — §12/§13; MULTI group fully evaluated: 4
               eligible, ranked, unsealed)
```

The recorded STOP is the gate outcome. Any continuation requires a
new preregistration (corpus extension or revised stress design) and a
new unseen holdout.
