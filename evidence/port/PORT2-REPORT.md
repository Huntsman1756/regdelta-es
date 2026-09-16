# PORT-2 report — BdE profile extraction under byte-equivalence

## Verdict (adjudicated)

```text
PORT-2  = FAIL            (contract compliance; immutable history)
PORT-2R = PASS
PORT    = PROFILE_EXTRACTION_PROVEN
```

PORT-2R was adjudicated PASS on the `3470f69` remediation: frozen
evaluators restored byte-for-byte, core-owned `source_registry` with
FK integrity (no profile-injected DDL), `LOCATOR_KINDS` /
`enabled_kinds` / `UNKNOWN_CORE_KIND`, `validate_profile`, F8
mappings, and a replay byte-identical to `003-final`.

The original PORT-2 failure record follows — kept unchanged.

Semantic equivalence to `003-final` was achieved and is not in
question (468 bindings, 0 FALSE_FACT/FALSE_BINDING, all canonical
comparators IDENTICAL). The FAIL is on the preregistered contract:

- Frozen evaluators were modified (G1 `f05276a`→`2ce0f99`,
  G2 `3a22546`→`c53d0d1`, sealed `e36c96f`→`6609d3f`) — prohibited
  outright, and it weakened auditor independence from the vocabulary
  under audit.
- The DB `source_id` CHECK was rendered from profile data inside
  SCHEMA — profile-injected DDL, which PORT-1 A5 excluded; with a
  second profile the schema would vary.
- The contracted core `LocatorKind` registry / `enabled_kinds` /
  `UNKNOWN_CORE_KIND` validation was not implemented.
- Profile well-formedness validation and the F8
  `metadata_mapping`/`relation_mapping` were contract-only.

## PORT-2R — Contract Compliance Remediation (preregistered)

```text
R1  restore frozen G1/G2 evaluators byte-for-byte
R2  runtime-side compatibility aliases; evaluator never imports
    SourceProfile
R3  core-owned source_registry + referential integrity; schema
    invariant across profiles; profile supplies rows only
R4  core LOCATOR_KINDS registry + profile enabled_kinds +
    UNKNOWN_CORE_KIND validation at registration
R5  profile well-formedness validator + F8 mappings
R6  rerun the exact PORT oracle: byte-identical semantic artifacts,
    PORT_INTENTIONAL_SEMANTIC_CHANGE_COUNT = 0, suite unchanged,
    frozen evaluator hashes restored
```

No F1–F8 changes; the functional extraction stands. No CNMV work.

## PORT-2R evidence

```text
R1  DONE — git checkout 1a04c82 restored the three frozen evaluators
    byte-for-byte (blobs f05276a / 3a22546 / e36c96f). The port2r run
    records evaluator sha256s identical to 003-final's envelope.

R2  DONE — module-level __getattr__ aliases (PEP 562) in
    operations/binding/history resolve the pre-PORT names
    (_ORDINALS, _QUOTED_SPAN_RE, _OP_KINDS, _MARKER_RE,
    _FICHERO_OWNER_RE, _CIRCULAR_RE) from active_profile() at use
    time. Evaluators contain no profile import.

R3  DONE — SCHEMA now declares a static core-owned
    source_registry(source_id PK, media_type) and both
    source_snapshots.source_id / source_checks.source_id are plain
    REFERENCES. Schema text is profile-invariant; the profile
    supplies registry rows via _sync_source_registry (verified:
    undeclared source_id -> FOREIGN KEY constraint failed; declared
    ids accepted). Migrations rebuild any table still carrying
    'CHECK (source_id IN' — G0-C era or interim PORT-2d — into the
    registry shape.

R4  DONE — profile.py: LOCATOR_KINDS frozenset (18 canonical kinds:
    core superset including BdE-only 'estado'/'fichero'), OP_KINDS
    taxonomy, and LocatorGrammar.enabled_kinds. validate_profile
    raises UNKNOWN_CORE_KIND when a profile references a kind
    outside the registry, and 'kind used but not enabled' when the
    grammar touches a kind the profile does not declare.

R5  DONE — validate_profile() runs inside register_profile:
    kind-keyed grammar fields ⊆ enabled_kinds ⊆ LOCATOR_KINDS,
    op-kind tokens ⊆ OP_KINDS, source_ids unique/non-empty,
    capture rules/default/media types reference only declared ids,
    relation_mapping targets ∈ {anterior, posterior}.
    SourceDescriptors gained metadata_mapping (BdE: identity — the
    BOE XML already emits canonical compatibility names, A3) and
    relation_mapping (anteriores/posteriores -> anterior/posterior).

R6  DONE — replay at HEAD against 003-final:
    all canonical comparators IDENTICAL (operations, attribution,
    relations, bindings, binding-sides, lifecycle, continuity,
    ordering, audit, failures, reconciliation, subject-outcomes,
    corpus-73, four-cases, metrics, cov-metrics, targets, ...)
    468 positive_binding_assertions | FALSE_FACT=0 | FALSE_BINDING=0
    PORT_INTENTIONAL_SEMANTIC_CHANGE_COUNT = 0
    347 tests green, no expectation changes
    frozen evaluator sha256s restored to 003-final's values
    no profile identity in any emitted artifact
    run: evidence/port/runs/port2r/
```

## Original run evidence (kept; applies to semantic equivalence only)

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
