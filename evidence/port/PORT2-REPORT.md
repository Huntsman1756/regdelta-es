# PORT-2 report — BdE profile extraction under byte-equivalence

Status: evidence complete, awaiting verdict (`PORT-2 = PASS | FAIL`).

## 1. What moved

All census items classified `PROFILE_MATERIAL` or
`PROFILE_INPUT_CORE_POLICY` are now profile data consumed through
`active_profile()`; enumeration, adjudication, ambiguity and
abstention stayed in core. Extraction proceeded in four slices, each
verified before the next began:

```text
736dbee  PORT-2a  C-016 state_code_families + profile scaffolding
                  (AnnexStateGrammar; 4 duplicated copies -> 1)
896a3d2  PORT-2b  F1-F3: DocumentModel, TextNormalization,
                  LocatorGrammar (+ FicheroGrammar inside F6)
c4493b5  PORT-2c  F4-F5: OperativeGrammar, IdentityReference
28d6725  PORT-2d  F6-F8: applicability_language, source_descriptors,
                  registry DDL rendered from profile source_ids
e779af6  PORT-2d  canonical node-stream contract -> document.py
                  (C-033: Ref/Node/DiarioDoc/DiarioParseResult are
                  core-owned; sources/boe_diario fills them)
```

`SourceProfile` ended with the eight contracted facets
(`document_model`, `text_normalization`, `locator_grammar`,
`operative_grammar`, `identity_reference`, `annex_state`,
`applicability_language`, `source_descriptors`), instantiated once as
`bde-circular / bde-v1` in `profiles/bde.py`.

## 2. Equivalence evidence

Oracle: `evidence/cov/cov2/runs/003-final` (frozen DEV corpus result).

Each slice replayed the frozen COV-2 evaluator with `--run-id
003-final` and `--dev-reference` pointing at the frozen run:

```text
evidence/port/runs/port2a-c016    dev_equivalence = true
evidence/port/runs/port2b-f1f3    dev_equivalence = true
evidence/port/runs/port2c-f4f5    dev_equivalence = true
evidence/port/runs/port2d-f6f8    dev_equivalence = true
evidence/port/runs/port2-final    dev_equivalence = true   (HEAD e779af6)
```

`port2-final` (the closing run) reproduces every canonical comparator
byte-identically — `operations`, `attribution`, `relations`,
`bindings`, `binding-sides`, `lifecycle`, `continuity`, `ordering`,
`audit`, `audit-amendments`, `failures`, `reconciliation`,
`subject-outcomes`, `corpus-73`, `four-cases`, `metrics`,
`cov-metrics`, `per-target`, `targets`, `accounting`,
`combined-smoke`, `debt-census` — and:

```text
positive_binding_assertions 468   (= 003-final)
relations_emitted          519
locator_proven_ops         445
leaf_operation_accounting  true
FALSE_FACT    = 0
FALSE_BINDING = 0
```

Full suite: 347 tests green, no expectation changes.

## 3. RUN_ENVELOPE — expected post-refactor values

Per PREREG §2 the whitelisted volatile fields differ; recorded values
for the closing run (`evidence/port/runs/port2-final/run.json`):

```text
runtime_head      e779af6c49b6eb408b5f27be3594a074fc89e77a
evaluation_head   e779af6c49b6eb408b5f27be3594a074fc89e77a
src_tree_sha256   93a59987ae962eb0309ab8dcdde45f5d158ca4a7
started_at/finished_at  run timestamps
run_id            003-final   (replay-matched)
dev_equivalence.reference  evidence/cov/cov2/runs/003-final
```

All non-volatile envelope fields are identical: `manifest_sha256`
`af78fc…`, `targets_sha256` `8b9b8c…`, `gold_sha256` `c64cf3…`,
`evaluator_sha256` `43cc3d…`, `evaluator_version cov2-v1`.

## 4. Contract invariants

- `PORT_INTENTIONAL_SEMANTIC_CHANGE_COUNT = 0`.
- Parser versions unchanged: `boe_diario_xml/v1`, `boe_operations/v4`,
  `structural_binding/cov-v1`, `history/v5`, `ownership/g2-v1`,
  `applicability/g0d-v3`, `boe_doc/v1`, `boe_pdf_textlayer/v1`,
  `boe_imagen/v1`, `bde_consultas/v1`, `boe_sumario/v1`.
- Profile identity/version appears in no semantic artifact: grep over
  every emitted run file finds no `bde-circular`/`bde-v1`/
  `profile_id`. The profile is discoverable only through the run
  envelope / registry, as contracted.
- No `if <source>` branching in core: every consumer resolves
  `active_profile().<facet>`; the registry fails closed on zero or
  ambiguous profiles.
- Canonical emitted spellings unchanged — `estado:`, `anejo:`,
  `norma:` etc. remain core `LocatorKind` serializations; the profile
  maps source lexemes onto core kinds only.
- DB: `source_id` CHECKs rendered from
  `source_descriptors.source_ids` at DDL build time; for the BdE
  profile the rendered SQL is byte-identical to the former literal.
  The profile supplies rows; core keeps integrity policy.

## 5. Residual boundary notes (not coupling)

- `sources/boe_*`, `bde_consultas`, `watcher.py`, `config.py`,
  `state.py` remain BdE *profile-package* boundary code (acquisition
  and raw-byte parsing). Per the approved three-layer split they may
  legitimately name BdE ids/endpoints; they are not core consumers.
- `COMPLETE`/`INVALID_STRUCTURE` parse-status spellings remain
  declared per source module; they are canonical emitted values and
  were left duplicated rather than consolidated, to keep the move
  byte-safe. Candidate for a future core enum — non-blocking.
- `sources/boe_diario.normalize` is producer-internal byte
  canonicalization (NBSP/whitespace), distinct from the
  `text_normalization` facet used for matching; stays in the parser.

## 6. Scope exclusions honoured

- No CNMV or second-source work.
- No coverage tuning, no debt-class change — metrics identical.
- Frozen evaluators untouched (`evaluator_sha256` identical).
- Prospective-holdout runtime reference `ebbfdde` unaffected.
- Historical gate evidence untouched.

## 7. Claim

If adjudicated PASS:

```text
PORT-2 = PASS
PORT   = PROFILE_EXTRACTION_PROVEN
```

This proves only that the existing BdE semantics can be expressed as
a restrictive profile over the stable core contract. It does not
claim portability: that requires the separately preregistered CNMV
probe, which is the falsification test of this architecture.
