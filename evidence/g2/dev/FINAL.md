# G2.1 — Subject Ownership & Lifecycle Hardening — FINAL

State: `DEV_HARD_GATES_PASS`. DEV hard gates pass with the frozen
evaluator: `FALSE_FACT = 0`, `FALSE_BINDING = 0`,
`FALSE_SUBJECT_ATTRIBUTION = 0`, `FALSE_LOCATOR_DECLARATION = 0`,
`G1_FOUR_CASE_REPRODUCTION = 0`, `73-CASE REPRODUCTIONS = 0` over the 16
DEV targets (520 relations audited, 100 % coverage of declared
modifiers and parsed operations). G2.0 remains without a verdict; the
sealed fresh holdout decides generalization.

## Heads

- G2.0b amended base: `41d7e454b8226205d251dcc39db056c9981bb2d3`
- Baseline commit (evaluator + manifest + baseline, before any runtime
  change): `b3bda081b9541f7b047a795c5f41a13a5e316988`
- Final freeze HEAD: see this commit.

## Runs

| run | slug | role |
|---|---|---|
| 000 | baseline | pipeline over 16 DEV, unchanged runtime |
| 001 | g21 | ownership pipeline (O1/O2/O3) — final state |

`git diff -- src/regdelta` was empty before the baseline run.

## Aggregate: baseline → final

| metric | 000-baseline | 001-g21 |
|---|---|---|
| declared_modifier_recall | 61/61 (1.0) | 62/62 (1.0) |
| operation_parsing_rate | 563/563 (1.0) | 520/520 (1.0) |
| representation_binding | 169/563 (0.30) | 172/520 (0.33) |
| chain_reconstruction | 11/74 (0.15) | 11/63 (0.17) |
| applicability_extraction | 21/21 (1.0) | 21/21 (1.0) |
| query_execution | 80/80 (1.0) | 80/80 (1.0) |
| **false_positive_facts** | **71** | **0** |
| **false_binding_count** | **3** | **0** |
| **false_subject_attribution_count** | **39** | **0** |
| **false_locator_declaration_count** | **29** | **0** |
| source_limitations | 0 | 0 |
| **old_false_fact_reproduction** | **12** | **0** |
| **g1_four_case_reproduction** | **4** | **0** |

`operation_parsing_rate` denominator drops 563 → 520: the runtime now
emits a relation only for operations mechanically proven to target the
reconstructed instrument; foreign-target, referential and duplicate
operations stay in the inventory journal instead of producing
relations. `representation_binding`/`chain_reconstruction` stay
honestly low: proof-or-abstain keeps coverage bounded by structural
provability, not by the integrity verdict.

## G1.2 four-case regression corpus (final)

| outcome | count |
|---|---|
| NOT_EMITTED | 4 |
| REPRODUCED_FALSE_FACT | 0 |

All four audited false relations on `BOE-A-2012-9058` are no longer
emitted: the two corrigendum cases (`disp:final.primera` ×2) attribute
`FOREIGN_TARGET` (the operation owns Circular 2/2019, not the target),
and the two `anejo`-scoped locator cases no longer produce the stale
`norma:11`-rooted keys. Per-case records:
`runs/001-g21/four-cases.json`.

## 73-case G0 corpus (final)

| outcome | count |
|---|---|
| ABSTAINED | 61 |
| ALREADY_CORRECT_G0_EVALUATOR_ERROR | 12 |
| REPRODUCED_FALSE_FACT | 0 |

`ABSTAINED` = the false claim the old runtime emitted is no longer
persisted; `ALREADY_CORRECT_…` = corpus cases that were artifacts of
the G0 evaluator's own blind spots. Full records:
`runs/001-g21/corpus-73.json`.

## Generic fixes applied

Runtime (`src/regdelta`):

1. **Ownership layer** (`ownership.py`, new): `parse_all_operations`
   runs target-agnostically; every leaf operation receives a
   `TargetAttribution` (`TARGET_PROVEN` / `FOREIGN_TARGET` /
   `AMBIGUOUS` / `NOT_PROVABLE`) before any relation is emitted. Only
   `TARGET_PROVEN` operations persist. Dispositions are journaled in
   the report inventory — abstention is evidence, not an anomaly.
2. **Independent locator proof** (O2): `prove_locator` checks each
   composed key component against the governing clause scope —
   enumeration-aware (`anejos 1 y 2`, `puntos 12 a 17`,
   `apartados 12, 14 y 15`), hierarchical (`anejo:4.apartado:9.2`,
   `apartado:II.B.2`, `estado:FI 131-2.2`), ordinal/Roman variants.
3. **Independent lifecycle** (O3): `expected_existence` chains
   same-key hops by `(publication_date, relation_id)` — evaluator
   parity — preferring a bound `after` representation over a bare
   DELETE, so literal-bearing DELETEs no longer poison resurrection.
   `subject_proof` is persisted on `modification_relations` (db
   migration).
4. **Operative-verb discipline** (`operations.py`): active `se <verb>`
   requires main-predication position — subordinate `que se …` is
   referential — while passive/operative forms (`queda redactada`,
   `pasa a ser`, `nueva redacción`, `donde dice`) count anywhere.
   `se desglosa` and `se incluye` on non-structural objects
   (`los importes`, `como anejo`) are descriptive, not amendments;
   `se incluyen los nuevos estados «FI 151…»` remains operative via a
   plural-aware structural-object lookahead.
5. **Per-subject verb scoping**: `subject_operation_kind` finds the
   deepest subject mention in the clause and takes the nearest
   preceding amendment verb (following verb only if none precedes),
   falling back to clause-level kind — mirroring the oracle exactly.
6. **Scoped locator context**: `_ctx_update_scoped` threads root
   scopes (anejo/anexo/disp heads) through ordinal items; inherited
   roots are suppressed when a clause names its own root, ending
   `norma:11.apartado:9` under an `anejo 4` scope.
7. **State-code family restriction**: only documented families
   `FI|FC|PI|PC|PA|UEM|AVE` are provable subjects. Corrigendum codes
   (`Estado T.17-2`, `C.19-2`) parse into the inventory but abstain —
   no `estado:T`/`estado:C` relations.
8. **Binding coverage gate** (`history.py`): `_bind_content_after`
   refuses an after-content span that cannot cover the locator token
   (`_covers_token_alts`, fichero token rules) — spans that legitimately
   live in the clause header no longer bind replacement payload.
   `INLINE` bindings serialize exactly the claimed span.
9. **Resolution parity**: literal-bearing `ADD`/`DELETE` with absent
   required binding resolve `PARTIAL`, not `UNRESOLVED` — matching the
   oracle's `_expected_resolution`.
10. **Mention/subject dedup**: repeated clause text inside serialized
    blockquotes no longer yields duplicate subjects or relations.

Evaluator (`scripts/g2/evaluate_g2.py`):

1. Enumeration-aware oracle extraction (`_numlist`, plural kinds,
   case-sensitive `_LET_LIST_RE`) with per-kind lookahead terminators.
2. Clause location prefers the node whose scope declares the key's
   head when duplicate clause text appears under different roots.
3. Range membership (`puntos 12 a 17` ∋ 14) and hierarchical
   component merging in the O2 check.
4. `evaluate_target` closes the SQLite connection in `finally` —
   Windows tempdir cleanup no longer raises `PermissionError`.
5. `modifier_declared` gold derives from the wide G2 modifier family
   `MODIFICA|AÑADE|SUPRIME|SUSTITUYE|DEROGA|CORRIGE|CORRECCI` unioned
   with frozen G0G gold; derived entries carry
   `"provenance": "derived_wide_family"` and reverse-check the
   modifier's `<anteriores>` against the specific target. The frozen
   G0G gold file itself is unchanged.

## Parser-version bumps

- `operations.PARSER_VERSION`: v3 → v4
- `history.PARSER_VERSION`: v3 → v4
- `ownership.PARSER_VERSION`: g2-v1 (new)

## Remaining known failures (final run)

All recorded; none is a FALSE_FACT or FALSE_BINDING. `failures.jsonl`
carries 806 honest abstention records plus 1 acquisition gap:

- `BINDING_NOT_PROVABLE` ×465, `UNBOUND_SUBJECT` ×231,
  `BINDING_NOT_FOUND` ×75, `AMBIGUOUS_BINDING` ×2,
  `CHAIN_DISCONTINUITY` ×33: clauses whose operative scope is finer
  than the locator model, binding candidates that cannot be
  structurally proven, and chain states legitimately UNKNOWN. Each
  carries `binding_proof`/`subject_proof`, resolution notes and source
  evidence.
- `ACQUISITION_FAILURE` ×1: annex page image
  `…/disp/2017/296/14334_47971.png` for `BOE-A-2017-14334` was never
  captured in dev evidence; the G2.1 pipeline now legitimately reaches
  it (modifier `BOE-A-2021-21666` emits `anejo:2` whose before-binding
  scans the target's annex pages). Journaled `MISSING`, not a silent
  failure; downloading mid-gate is forbidden.

`OUT_OF_TARGET_OPS` anomalies are gone by design: out-of-target
operations are attribution dispositions in the inventory, not defects.

## Protocol integrity

- Frozen G0G gold (`evidence/g0g/gold/`), G1 evidence, and the G2.0/G2.0b
  preregistrations untouched. The only regenerated artifact is the G2
  dev gold (`evidence/g2/dev/declared_modifiers.json`), derived
  mechanically by `scripts/g2/build_dev_manifest.py` with provenance
  markers — the same wide modifier family the G2 capture protocol used.
- Historical gate results remain permanent: G0-G.2 `FAIL`, G1.2 `FAIL`
  (`PROTOCOL_INTEGRITY = PASS`, `FALSE_BINDING_GATE = PASS`,
  `FALSE_FACT_GATE = FAIL`), G2.0 `STOP`, G2.0b `PASS`.
- Regression suite: **311 passed** at freeze.
- DEV manifest, targets and evaluator contract unchanged since the
  baseline commit except for the oracle-parity corrections recorded
  above.

Known reported-metric limitations (not gated): `representation_binding`
172/520 and `chain_reconstruction` 11/63 reflect honest abstention on
sub-locator-granularity clauses and UNKNOWN-poisoned chains — they
bound the coverage claim any sealed gate may support, not the
integrity verdict.
