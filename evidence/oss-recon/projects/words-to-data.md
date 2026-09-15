# words-to-data

## 1. Source freeze

- repo: wordstodata/words-to-data
- url: https://github.com/wordstodata/words-to-data
- commit/tag inspected: `ccc44e023931843aaaae3caebf25bf29a5706ef1`
  (main, pushed 2026-09-13)
- review date: 2026-09-15
- license: Apache-2.0 (also ships LICENSE-MIT; API reports Apache-2.0)
- license ref (hash/path): `LICENSE-APACHE` @ ccc44e0

## 2. Problem fit

RegDelta problem(s) evaluated against:

- `problems/stable-node-identity.md` — primary
- `problems/hierarchical-diff.md` — primary
- `problems/amendment-actions.md` — secondary
- `problems/representation-binding-evidence.md` — secondary (weak)

Component(s) of the project addressing each problem:

- `src/diff/mod.rs` — `TreeDiff`, `Redesignations`, `NodeMove`:
  diff consults redesignation links *before* pairing by position
- `src/link.rs` — `legislature.redesignated_as` edges; continuity is
  a projection walked over links (`LinkReader::provision_history`)
- `docs/adr/0001-structural-paths-locate-not-identify.md` — decided
  NOT to mint provision identity; paths locate, links carry
  continuity. Same conclusion RegDelta reached implicitly
- `docs/adr/0005-evidence-is-stored-once-and-never-deleted.md` —
  content-addressed, append-only evidence store
- `src/uslm/` — `AmendingAction` incl. `Redesignate`, `Move`;
  bill amendment extraction

## 3. Document assumptions

- input format: USLM XML (US Code titles + Public Laws) only
- presumes already-structured text?: YES — USLM is publisher-structured
- receives consolidated documents?: reads title expressions as
  published; no consolidation step
- IDs come from the source or are minted by the system?: mixed —
  `identifier` attribute where present, heading-derived segment where
  not (ADR-0001 documents 6,962 heading-named paths and their
  instability against publisher rewording)
- treatment of annexes/tables/images: not evaluated deeply; USLM
  structure-typed (`ElementType` closed enum)
- what "a version" means here: an expression of a work at a date
  (`uscode/title_26@2025-07-18`), FRBR work/expression split

## 4. Evidence-rule compatibility

| question | answer |
|---|---|
| Can output trace to official source bytes? | PARTIAL — verbatim text fields + path locators; no byte-span ledger |
| Can claim trace to exact structural span? | PARTIAL — structural paths, not byte offsets |
| Deterministic? | NO for the amendment pipeline — `match-amendments` re-queries an LLM and is non-reproducible (899 vs 893 links across identical builds, ADR-0005); the USLM parser itself is deterministic |
| Can ambiguity remain unresolved? | YES — position pairing documents genuinely unresolvable cases (§ 6724(d)(2)) and keeps them honest |
| Can it fail closed rather than guess? | PARTIAL — verification states (`MachineSuggested` vs human) journaled, but the model pipeline guesses by design |
| Requires synthetic consolidation? | NO — expressions stored raw; no consolidation |
| Requires normalized/re-written legal content? | NO — verbatim fields preserved |
| Preserves original representation separately? | YES — work/expression split, append-only evidence |
| Supports temporal provenance? | YES — expression dates, dated links |

## 5. Technical extraction

- `Redesignations::from_links` + `TreeDiff::moved` —
  `src/diff/mod.rs` (~1167 lines): pairing rule = consult
  redesignation edges first, position pairing as documented fallback
- `legislature.redesignated_as` link kind — `src/link.rs`
- ADR corpus `docs/adr/0001..0010` — the closest external write-up
  of RegDelta's own design space, including honest failure records
- `src/uslm/bill_redesignation.rs` — redesignation extraction from
  bill text

## 6. Integration cost

- language/runtime: Rust (Python bindings exist but USLM-shaped)
- dependencies: Cargo ecosystem
- size: ~103 source files, medium
- API stability: 0.3.0, pre-1.0
- maintenance: active (pushed 2026-09-13)
- license constraints: Apache-2.0/MIT — adoption-friendly
- vendoring/port feasibility: port of the *algorithm* feasible
  (~200 lines for Redesignations+pairing); the code is USLM-typed
- coupling surface: adopting the crate would import USLM document
  assumptions — incompatible with BOE input

## 7. Delta against RegDelta

| capability | upstream | RegDelta | gap/use |
|---|---|---|---|
| stable subject identity | deliberately none — redesignation edges | locator_key + relation chains | convergent design; their `moved` edge is our missing renumbering continuity |
| operation extraction | USLM AmendingAction + LLM matching | deterministic parse_all_operations | theirs is non-reproducible — no use |
| representation binding | path locators, no span ledger | binding_proof + byte evidence | RegDelta stronger |
| version lifecycle | work/expression, dated links | representations + lifecycle O3 | comparable; theirs LLM-augmented |
| provenance | append-only evidence store, prompt hashes | snapshots + proofs, fully reproducible | RegDelta stronger (their pipeline is not reproducible) |
| fail-closed | partial (verification labels) | hard gates | RegDelta stronger |

## 8. Minimal falsification experiment

Experiment: apply the redesignation-edge pairing rule (consult
`moved`/redesignation edges before positional pairing) to the already
audited renumbering cases in the frozen DEV corpus — operations of the
form "pasa a ser apartado/letra X" and enumerator renumberings — and
compare continuity outcomes against the adjudicated G2.1 chain ledger.

PASS criterion (fixed before execution): continuity is preserved for
every adjudicated renumbering case with zero false delete+add pairs
and zero relations emitted that the proven O1/O2 ledger did not
prove.

FAIL criterion: any false continuity (two distinct subjects merged)
or any lost continuity the adjudicated ledger proves.

## 9. Verdict

PATTERN

secondary_value: `Redesignations`/`TreeDiff` pairing is a PORT
candidate for `hierarchical-diff` — the algorithm, not the crate —
gated on the §8 experiment; its amendment pipeline is a negative
result (LLM, non-reproducible) confirming RegDelta's deterministic
requirement.

experiment outcome: EXP-B1 (`evidence/cov/exp-b1/`) ran the §8
falsification over both frozen ledgers — 85 redesignation cases, 15
actionable edges, zero false merges / contradictions / lost
continuity, one proven repair (`FI 16-1 -> FI 16-1.2` on 4/2004).
Verdict `PORT` — mechanism eligible for a COV-2 preregistration.

## 10. Decision rationale

- what_we_reuse: the redesignation-edge continuity model (record
  `moved`/`redesignated_as` edges, project chains on demand), and
  ADR-0001's documented failure catalogue as a checklist for our
  own wrong-locator classes
- what_we_explicitly_do_not_reuse: the crate, USLM document model,
  the LLM amendment-extraction pipeline, minted-identity designs
- why_this_survives_or_fails_RegDelta_evidence_rules: the parser and
  link model are deterministic and source-faithful, but the
  amendment pipeline is non-reproducible (899 vs 893 links on
  identical input — ADR-0005) and nothing binds claims to byte-level
  official evidence; usable as architecture prior art, not as
  dependency
