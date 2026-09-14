# G1 — Structural Binding Integrity Preregistration

Gate: `G1.0 — Structural Binding Integrity Preregistration`
Base: `5d119e86b5490885d571e0affdd40d80c3dd2ae5`

G0-G.2 remains permanently:

```text
PROTOCOL_INTEGRITY = PASS
FALSE_FACT_GATE    = FAIL
G0-G.2             = FAIL   (73 FALSE_FACT: 68 on BOE-A-2013-5720,
                              5 on BOE-A-2016-1238)
```

`evidence/g0g/g0g2/**` is immutable historical record. It is never
edited, reinterpreted, deleted or replaced.

## 1. Question

> ¿Puede RegDelta garantizar bindings estructurales factualmente
> correctos sobre normas con múltiples modificaciones encadenadas,
> degradando a PARTIAL/UNRESOLVED cuando el span no pueda probarse de
> forma única?

Priority: **precision / factual integrity > binding coverage**.
An absent binding is acceptable. An incorrect binding is not.

## 2. Scope

G1 corrects: target locator resolution, before/after representation
binding, version-chain continuity, structural span selection.

Out of scope: CNMV, EUR-Lex, consultations, frontend, MCP, alerts,
LLM, OCR, new product features.

The 73 G0-G.2 FALSE_FACTs are the initial failure corpus
(`evidence/g1/dev/g0-false-binding-corpus.json`, classified per case in
`evidence/g1/root-cause/`).

## 3. Corpus roles

- **G1 DEV** = the 12 already-seen G0-G targets (8 GENERALIZATION_DEV +
  4 former SEALED_HOLDOUT). The former holdout carries the failures
  that motivate G1. No fresh instrument may enter DEV.
- **G1 SEALED_HOLDOUT** = 4 fresh unseen targets (2 TEXT + 2 VISUAL),
  selected for amendment density (see §6).

## 4. Semantic seen-set

`evidence/g1/semantic-seen-set.json` is derived mechanically from run
artifacts and manifests (script: `scripts/g1/build_seen_set.py`):

- pre-G0 seen-set (evidence/**, tests/fixtures/**);
- the 12 G0-G targets;
- every modifier instrument whose body was loaded by
  history/applicability/evaluator during G0-G.1 or G0-G.2 (gold
  declared modifiers + modifier ids appearing in run artifacts).

`CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN`: bytes used only for
eligibility, posteriores metadata, representation-profile
classification, hashing or capture do not exclude an instrument.

## 5. Fresh holdout universe

Same frozen BdE index captured in G0-G.0
(`evidence/g0g/raw/bde_circulares_indice_cronologico.html`; a different
index may only be captured upon objective impossibility).

Candidates = G0 ELIGIBLE candidates − semantic-seen-set, requiring
**>= 2 explicit modifying instruments** in `<posteriores>` (corrections
without modification operations do not count).

## 6. Holdout selection (stress test)

Two groups: TEXT, VISUAL. Within each, order by:

1. `declared_modifying_instrument_count` DESC
2. explicit anejo/anexo references in `<posteriores>` DESC
3. `sha256("regdelta-g1-v1|" + boe_id)` ASC

Top 2 per group → SEALED_HOLDOUT. CONSOLIDATED/NON_CONSOLIDATED is
descriptive metadata only. Fewer than 2 eligible in a group → STOP.

### G1.0 outcome: STOP on selection

The frozen index yields **3** candidates with >= 2 modifying
instruments after seen-set exclusion:

| group | candidates |
|---|---|
| TEXT | BOE-A-2014-1183 (4 mods), BOE-A-2010-15521 (2 mods) |
| VISUAL | BOE-A-2012-9058 (6 mods) — only 1 |

VISUAL cannot field 2 fresh amendment-dense unseen targets →
`evidence/g1/selection.json` records `STOP`. No criterion was relaxed
after inspecting identities. Holdout capture/SEAL is deferred until a
G1.0b decision resolves the pool (options: refreshed BdE index under
the objective-impossibility clause, or amended selection design in a
new preregistration).

## 7. Truth verdict vs root cause (separated fields)

Every discrepancy carries two independent fields:

- `truth_verdict` ∈ {PASS, FALSE_FACT}
- `root_cause_class` ∈ {SOURCE_LIMITATION, ACQUISITION_FAILURE,
  OPERATION_PARSER_FAILURE, LOCATOR_RESOLUTION_FAILURE,
  REPRESENTATION_BINDING_FAILURE, CHAIN_FAILURE, SCHEMA_FAILURE,
  QUERY_EVALUATION_FAILURE}

The stage where the evaluator detects an error does not determine its
cause. (G0-G.2 conflated these: 7 of its 73 FALSE_FACTs were
`verb_check_on_metadata_text` — an evaluator-scope artifact, root cause
QUERY_EVALUATION_FAILURE, while the emitted claim itself was true.)

## 8. Binding invariants (frozen)

- **B1 Unique-or-unbound.** A textual/table locator may produce a
  representation only if the resolver obtains a unique structural
  identification. `candidate_count == 1` → bind; `0` → unbound;
  `>1` → unbound. First/closest-candidate selection is forbidden.
- **B2 Exact structural scope.** The representation must lie inside
  the document scope declared by the operation; a locator match in
  another norma/anejo/sección of the same document is invalid.
- **B3 Modifier-side scope.** An `after_representation` must come from
  the concrete operation's replacement/content span or an official
  structure unequivocally linked to it — never a global lookup of the
  same locator inside the modifier.
- **B4 Chain predecessor.** When an immediately-prior proven
  representation exists for the same subject,
  `next.before == previous.after`, unless explicit evidence justifies
  discontinuity. The before may not be arbitrarily re-resolved against
  an earlier version.
- **B5 Ambiguity degrades.** Duplicated, renumbered or repeated
  headings forbid RESOLVED unless uniqueness is proven; prefer
  PARTIAL/UNRESOLVED.
- **B6 Resolution follows verified binding.** RESOLVED cannot depend
  on a representation the verifier deems ambiguous or incorrect.

## 9. binding_proof

Preregistered concept (schema decision deferred to G1.1): every binding
must be able to demonstrate: locator requested, document/snapshot,
structural scope, candidate count, chosen candidate, node/span locator,
binding method, predecessor relation/representation when chained.
First preference: enrich `binding_evidence`; new schema only if the
existing model cannot express the proof auditably.

## 10. Root-cause findings over the 73 G0 FALSE_FACTs

`evidence/g1/root-cause/summary.json` (per case: `cases.jsonl`):

| mechanism | count |
|---|---|
| after:span in modifier doc, op-content link unproven (B3) | 44 |
| before:span in modifier doc — before-image outside target (B4) | 38 |
| locator absent under claimed key (B1) | 12 |
| locator only present renumbered (roman↔arabic) (B1/B5) | 7 |
| verb check run on posteriores metadata text (evaluator scope) | 7 |
| global-vs-local span lookup (B2) | 5 |
| locator partially resolves | 1 |

Root-cause classes: REPRESENTATION_BINDING_FAILURE 61,
LOCATOR_RESOLUTION_FAILURE 16, QUERY_EVALUATION_FAILURE 7 (cases may
carry several).

Dominant pattern: 54/73 relations were synthesized from posteriores
metadata text (`relation_raw_is_metadata`); their bindings point into
the modifier document's declaration region, not the target's
structural spans.

## 11. Mandatory regression corpus

`evidence/g1/dev/g0-false-binding-corpus.json` freezes all 73 cases.
G1.1 hard requirement:

```text
for every old FALSE_FACT the corrected runtime must either
  A) emit the fact correctly, or
  B) abstain / leave it unbound
never C) emit the old incorrect claim
→ OLD_FALSE_FACT_REPRODUCTION_COUNT = 0
```

## 12. Coverage guard

No post-hoc thresholds. Every coverage regression vs the G0-G.2
runtime must be explained by AMBIGUOUS_BINDING_ABSTENTION or another
factual reason; the report must show how much recall was sacrificed
for precision.

## 13. Evaluator preregistration (G1.2 contract sketch)

Per relation: modifier relation, operation kind, target locator,
before/after binding, resolution, chain predecessor where applicable.
Textual/table bindings compare persisted representation ↔ exact
claimed official structural span; visual bindings compare artifact/page
↔ official artifact locator/hash. Explicit outcomes:
BINDING_CORRECT / BINDING_FALSE / BINDING_NOT_CHECKABLE /
NO_BINDING_CLAIM. NOT_CHECKABLE may not hide a mechanically checkable
claim.

## 14. Hard gates (frozen)

Per holdout target: `FALSE_FACT_COUNT = 0`, `FALSE_BINDING_COUNT = 0`;
plus `PROTOCOL_INTEGRITY = PASS`. No post-hoc thresholds on RESOLVED
rate, binding rate, locator resolution or applicability — they are
reported, not gated.

## 15. Claim if G1 passes (updated by G1.0b)

> Structural binding integrity is supported on the complete available
> fresh amendment-dense BdE holdout selected under the preregistered
> eligibility rule, including both textual and visual targets, with
> measured coverage and fail-closed abstention.

Not: fully general / complete legal recall / production-complete /
100% regulatory coverage.

## 16. Sequence

```text
G1.0  preregistration: root-cause corpus, fresh selection, fresh seal,
      invariants, metrics, evaluator contract — NO runtime fixes
G1.1  redesign/fix on the 12 already-seen targets; 73-case regression
      corpus; generic fixes only; freeze runtime + evaluator
G1.2  open fresh G1 holdout once; no post-open changes; audit 100%
```

## 17. Anti-hardcoding

`evidence/g1/runtime-literals-baseline.json` frozen at base HEAD;
`tests/g1/test_no_new_target_specific_code.py` asserts
new target-specific runtime literals = ∅.

## 18. G1.0 status

```text
seen-set             DONE (47 instruments, mechanical)
root-cause corpus    DONE (73/73 classified)
binding invariants   FROZEN
taxonomies           FROZEN
fresh selection      STOP — VISUAL pool has 1 candidate < 2 required
holdout capture      NOT PERFORMED (no selection)
runtime changes      ZERO (git diff base..HEAD src/regdelta empty)
```

G1.0 cannot be declared PASS without the sealed holdout; the gate is
blocked at §6 pending a decision on the holdout pool.
