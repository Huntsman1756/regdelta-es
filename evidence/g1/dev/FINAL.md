# G1.1 — Structural Binder Redesign & DEV Hardening — FINAL

State: `READY_FOR_ONE_SHOT_G1_2`. DEV hard gates pass with the frozen
runtime + evaluator: `FALSE_FACT = 0`, `FALSE_BINDING = 0`,
`73-CASE REPRODUCTIONS = 0` over the 12 semantically-seen DEV targets
(219 relations audited, 100 % coverage). G1.0 remains without a verdict;
the sealed fresh holdout decides generalization in G1.2.

## Heads

- G1.0b amended base: `d47f48a758f9496cfbb40a8ca5b830026eda3021`
- Baseline commit (evaluator + manifest + baseline, before any runtime
  change): `fc7302dd08dd93685a46252a079196d1f47be298`
- Phase-B binder commit: `cbef5a88e2a50399a6f839f26d54297ffdd29317`
- Final freeze HEAD: see this commit.

## Runs

| run | slug | role |
|---|---|---|
| 000 | baseline | pipeline over 12 DEV, unchanged runtime |
| 001 | binder-v1 | first live evaluation of the proof-or-abstain binder |
| 002 | scope-chain | subject-scope proof + proof-aware chain audit |
| 003 | audit-fixes | clause-source, ordinal coverage, chain verification |
| 004 | scope-owner | per-segment scope, qualifier suffixes, content ownership |
| 005 | final-audit | verb vocabulary alignment + disposition coverage |
| 006 | final | unnumbered disposición headings — final state |

`git diff -- src/regdelta` was empty before the baseline run.

## Aggregate: baseline → final

| metric | 000-baseline | 006-final |
|---|---|---|
| declared_modifier_recall | 39/39 (1.0) | 39/39 (1.0) |
| operation_parsing_rate | 219/219 (1.0) | 219/219 (1.0) |
| subject_locator_resolution | 178/219 (0.81) | 192/219 (0.88) |
| representation_binding | 156/219 (0.71) | 67/219 (0.31) |
| chain_reconstruction | 12/19 (0.63) | 3/19 (0.16) |
| applicability_extraction | 10/11 (0.91) | 11/11 (1.0) |
| query_execution | 60/60 (1.0) | 60/60 (1.0) |
| **false_positive_facts** | **138** | **0** |
| **false_binding_count** | **77** | **0** |
| source_limitations | 0 | 0 |
| **old_false_fact_reproduction** | **72** | **0** |

`representation_binding` and `chain_reconstruction` intentionally drop:
the binder now abstains (`NOT_FOUND`/`AMBIGUOUS`/`NOT_PROVABLE`) where the
old pipeline persisted first-hit or stale-chain bindings — the 138/77
false claims came from exactly those paths.

## 73-case regression corpus (final)

| outcome | count |
|---|---|
| ABSTAINED | 57 |
| ALREADY_CORRECT_G0_EVALUATOR_ERROR | 16 |
| REPRODUCED_FALSE_FACT | 0 |

`ABSTAINED` = the false claim the old runtime emitted is no longer
persisted; `ALREADY_CORRECT_…` = corpus cases that were artifacts of the
G0 evaluator's own blind spots, not runtime false facts. Full per-case
records: `runs/006-final/corpus-73.json`.

## Generic fixes applied

Runtime (`src/regdelta`):

1. **Structural binder layer** (`binding.py`): candidate enumeration per
   locator, scope hierarchy, invariants B1–B6, proof-or-abstain statuses
   (`BOUND`/`AMBIGUOUS`/`NOT_FOUND`/`NOT_PROVABLE`/`NOT_APPLICABLE`), and
   `binding_proof` persisted on `modification_relations` (db migration).
2. **Subject-state chain** (`history.py`): PRESENT/DELETED/UNKNOWN
   states; a SUBSTITUTE whose `after` cannot be proven poisons the chain
   to UNKNOWN — stale representations are never resurrected; `ADD`
   before and `DELETE` after are `NOT_APPLICABLE` before any scope gate.
3. **Content-link taxonomy** (`operations.py`): after-side content must
   come from an explicit pointer — `INLINE_QUOTED`,
   `EXPLICIT_FOLLOWING_CONTENT`, `EXPLICIT_ANNEX_REFERENCE`, declared
   literals — never a modifier-global first hit.
4. **Per-subject verb scoping**: the governing verb is the nearest one
   governing the mention's own sub-clause; trailing `que se incluye` /
   `quedan redactados` pointers no longer flip SUBSTITUTE→ADD.
5. **Subject-scope proof**: per-segment clause scoping; operations on
   unmodelled sub-elements (módulo, dimensión, nota, párrafo, columna,
   celda, numeral) and qualifier suffixes (`norma 64 ter`,
   `apartado 2.e`) abstain instead of binding the parent.
6. **Content ownership**: following content binds only to the subject
   whose sub-clause governs the pointer; quote masking preserves
   offsets.
7. **Unnumbered disposición headings** (`applicability_parser`):
   `Disposición final. Entrada en vigor.` (no ordinal word) now yields a
   `…u` span; same-type unnumbered collisions get a deterministic suffix.
8. **Anomaly dedup** by deterministic id in the build report.

Evaluator (`scripts/g1/evaluate_g1.py`):

1. `locator_raw` is the operative clause; `relation_raw` is metadata —
   verb checks run against the clause, not posterior text.
2. Verb checks use the runtime's `_OP_KINDS` vocabulary with
   accent-preserving matching and nearest-preceding-verb scoping.
3. Subjects not named in the clause → `NOT_CHECKABLE`, never a guessed
   verdict.
4. Chain predecessors are verified through persisted `binding_proof`
   (`predecessor_relation_id`/`_representation_id`), not re-guessed by
   date; `ADD` skips the chain-predecessor claim.
5. Ordinal/morphological locator variants (`decimocuarta` ↔
   `décima cuarta` ↔ `14`, roman forms) in resolution and coverage.
6. Head vs sub-locator distinction (`disp:transitoria.primera` is a head
   locator); whole-subject replacement spans need not repeat the
   heading.
7. Visual-code locators and ancestor-substituted subjects are honestly
   `NOT_CHECKABLE` (no mechanical path to the claim).

## Parser-version bumps

- `operations.PARSER_VERSION`: v2 → v3
- `history.PARSER_VERSION`: v2 → v3
- `binding.PARSER_VERSION`: g1-v1 (new)
- `applicability_parser.PARSER_VERSION`: g0d-v2 → g0d-v3

## Remaining known failures (final run)

All recorded; none is a FALSE_FACT or FALSE_BINDING. `failures.jsonl`
carries 386 honest anomaly records plus 1 acquisition gap:

- `BINDING_NOT_PROVABLE` ×219, `UNBOUND_SUBJECT` ×113,
  `BINDING_NOT_FOUND` ×20, `CHAIN_DISCONTINUITY` ×9,
  `AMBIGUOUS_BINDING` ×2, `ANCHOR_MISMATCH` ×6, `OUT_OF_TARGET_OPS` ×14:
  clauses whose operative scope is finer than the locator model
  (module/dimension/note/paragraph-level), annex anchors outside
  established code families, or chain states legitimately UNKNOWN. Each
  carries `binding_proof`, resolution notes and source evidence.
- `ACQUISITION_FAILURE`/`FETCH_ERROR` ×1: modifier `BOE-A-2021-21666`
  (declared modifier of `BOE-A-2019-17286`) was never captured in dev
  evidence; downloading mid-gate is forbidden. Same gap recorded in
  G0-G.1.

Known reported-metric limitations (not gated): `representation_binding`
67/219 and `chain_reconstruction` 3/19 reflect honest abstention on
sub-locator-granularity clauses and UNKNOWN-poisoned chains — they bound
the coverage claim G1.2 may support, not the integrity verdict.

## Protocol integrity

- Fresh G1 holdout (`BOE-A-2010-15521`, `BOE-A-2012-9058`,
  `BOE-A-2014-1183`) untouched: `tests/g1/test_g1_holdout_sealed.py`
  passes; no content was read or parsed during G1.1.
- G0-G.2 remains permanently sealed `FAIL` (73 FALSE_FACT).
- Anti-hardcoding guard passes: `tests/g1/test_no_new_target_specific_code.py`.
- Regression suite: **272 passed** at freeze.
- DEV manifest, corpus and evaluator contract unchanged since the
  baseline commit except for the audit-logic corrections recorded above.
