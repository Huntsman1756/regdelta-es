# G0-G.1 — DEV Generalization & Generic Hardening — FINAL

State: `READY_FOR_ONE_SHOT_HOLDOUT` inputs complete. This gate does not
decide generalization; that verdict belongs to G0-G.2.

## Heads

- G0-G.0 preregistered base: `3e8e27df8999307bf4cbce42f77891a5827b4d81`
- Baseline commit (before any runtime change): `51e9cdfc4fbc83d63723bb7283e29105cd6748e3`
- Fix commits: `bdf2b0567a837aadcf5aff3be29f633eb1e3c0d8`,
  `4ced0d129962261703c6609f66e13e286929e201`
- Final freeze HEAD: see this commit.

## Runs

| run | slug | role |
|---|---|---|
| 000 | baseline | pipeline of `3e8e27d` over the 8 DEV targets |
| 001 | generic-ops | unmarked ops, fichero subjects, target refs, dynamic disposiciones |
| 002 | evaluator-fixes | independent resolver + verb-check corrections |
| 003 | nearest-verb | fichero governing-verb scoping |
| 004 | articulo-heads | ordinal/bracket heading tolerance |
| 005 | redaccion-verb | 'dar nueva redacción' + quoted content spans — final state |

`git diff -- src/regdelta` was empty before the baseline run.

## Aggregate: baseline → final

| metric | 000-baseline | 005-final |
|---|---|---|
| declared_modifier_recall | 19/19 (1.0) | 19/19 (1.0) |
| operation_parsing_rate | 12/12 (1.0) | 51/51 (1.0) |
| subject_locator_resolution | 10/12 (0.83) | 41/51 (0.80) |
| representation_binding | 4/12 (0.33) | 36/51 (0.71) |
| chain_reconstruction | 0/0 (null) | 0/0 (null) |
| applicability_extraction | 1/2 (0.5) | 2/2 (1.0) |
| query_execution | 40/40 (1.0) | 40/40 (1.0) |
| false_positive_facts | 2 | 0 |
| source_limitations | 0 | 0 |

Relations emitted: 12 → 51 (baseline emitted relations for 1 of 8
targets; final for 7 of 8 — see remaining failures).

## Per-target resolution distribution (final)

- BOE-A-2005-4749: 16 rels — RESOLVED 15, PARTIAL 1
- BOE-A-2010-12488: 1 rel — RESOLVED 1
- BOE-A-2010-1824: 2 rels — RESOLVED 2
- BOE-A-2011-2378: 11 rels — RESOLVED 10, PARTIAL 1
- BOE-A-2012-3169: 6 rels — UNRESOLVED 6
- BOE-A-2013-7467: 3 rels — RESOLVED 2, PARTIAL 1
- BOE-A-2016-4356: 10 rels — RESOLVED 4, PARTIAL 6
- BOE-A-2019-17286: 2 rels — RESOLVED 2

query_execution: 5/5 surfaces OK on every target (baseline and final).
Audit coverage: 51/51 emitted relations audited in the final run
(100 %); cumulative audit register at `evidence/g0g/audit.jsonl`.

## Generic fixes applied (see `evidence/g0g/fixes.jsonl`)

1. Unmarked operative paragraphs inside dispositive sections +
   leading-preamble target refs + 'Circular del Banco de España N/YYYY'
   + named-entity per-op attribution in unnamed sections.
2. `fichero:` subjects end-to-end: extraction, three official annex
   heading shapes, connector-insensitive name equality, fichero-scoped
   governing verb (last preceding).
3. Composed `disp:` locators, parenthetical `(Estado CODE)` subjects,
   self-contained unmarked-op content spans.
4. Dynamic disposición discovery in `applicability_parser`
   (transitoria/final/adicional/derogatoria × numeric+linguistic
   ordinals incl. única).
5. 'dar nueva redacción a' as SUBSTITUTE-class verb; unmarked clauses
   ending ':' consume following quoted/indented nodes as content.
6. `history` articulo headings: optional `[precepto]`-style bracket
   prefix, digit or linguistic ordinal.
7. Passive-infinitive amendment verbs ('debe añadirse/modificarse/…'),
   `crea` in ADD recognition.

RED→GREEN regression tests: `tests/g0g/test_dev_eval.py`
(10 tests, one per generic rule family).

## Parser-version bumps (§18)

- `operations.PARSER_VERSION`: v1 → v2
- `history.PARSER_VERSION`: v1 → v2
- `applicability_parser.PARSER_VERSION`: g0d-v1 → g0d-v2

## Evaluator deviations recorded (EVALUATOR.md frozen, not edited)

Contract-consistent operationalizations added in the implementation
after the baseline (recorded here per the contract's deviation clause):

- `target_locator_resolves` for `ADD` ops and for `estado:`/`pagina:`
  keys bound to image evidence is `NOT_CHECKABLE` (no mechanical path
  to the actual claim: the pre-change target cannot contain a subject
  the op creates; image content is not OCR-readable).
- The independent verb check strips `«...»` quoted spans (rubric/literal
  citations) before matching the earliest positional verb.
- The independent resolver handles `disp:`/`fichero:`/composed keys,
  `capitulo_tit` fichero headings, linguistic ordinals and bracket
  tag prefixes on articulo headings, and connector-insensitive fichero
  name equality — mirroring, independently, the runtime's resolution.

## Remaining known failures (final run, 21)

All classified; none is a FALSE_FACT:

- `ACQUISITION_FAILURE` ×2 (+1 FETCH_ERROR): modifier BOE-A-2021-21666
  (a declared modifier of C4/2019) was not captured in dev evidence;
  §13 forbids downloading mid-gate.
- `PARSER_FAILURE` ×19, all honest anomaly records:
  - `ANCHOR_MISMATCH` ×6, `UNBOUND_SUBJECT` ×6 (BOE-A-2012-3169): T/C
    estado codes cannot anchor in the annex map (established code
    families only); emitted relations stay honestly UNRESOLVED.
  - `ANNEX_REFERENCE_UNRESOLVED` ×3: after-side annex refs of fichero
    ops unresolved in some modifiers.
  - `OUT_OF_TARGET_OPS` ×3 + BOE-A-2010-12488's second modifier
    produces 0 relations: multi-target modifiers' ops that correctly
    belong to other circulars are excluded and recorded.

No `SOURCE_LIMITATION` was claimed; no `SCHEMA_FAILURE` occurred
(schema unchanged).

## Regression status

- Full suite: 232 passed (including the 3 G0-A–F invariant tests and
  both G0-G.0 guard tests).
- Frozen corpus counts unchanged: subjects 221, representations 335,
  modification_relations 292 (RESOLVED 182 / PARTIAL 93 / UNRESOLVED 17),
  clauses 26, effects 16, targets 98, anomalies 23.
- `test_no_target_specific_code`: current literals − baseline = ∅.
- `test_holdout_sealed`: seal verified; holdout never opened,
  parsed, or evaluated.

## Combined DEV smoke

`evidence/g0g/dev/runs/005-redaccion-verb/combined-dev.json`: ok=true —
all eight targets sequentially in one DB; no PK collisions, no
cross-target subject/relation leakage, all FKs valid, all five query
surfaces execute per target.
