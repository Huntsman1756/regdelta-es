# CORE-GAP — umbrella preregistration

Status: PREREGISTERED. Single approval covers the whole program: four
internal workstreams executed continuously to material terminals, then
the post-freeze hardening integration. No inter-workstream approval
gates. Global stops are listed in §10 only.

## 1. Program question

Can the six CNMV `PROFILE_LIMIT` families — or the subset that is
safely solvable — be removed **in the core**, preserving
proof-or-abstain, byte provenance, determinism and every previously
proven behavior?

Terminal per workstream: `PROVEN` | `HONEST_LIMIT` |
`SOURCE_LIMIT` | `FAIL` | `MODEL_EXTENSION_UNSAFE`. A workstream FAIL
does not stop the others if semantically independent.

## 2. Base, isolation, forbidden

```text
BASE            core-gap @ f8e3a08 (PORT-CNMV-1 adjudicated
                PROFILE_LIMIT; freeze record FREEZE.json)
BRANCH          core-gap (worktree F:/_Proyectos/regdelta-cnmv1)
SEALED          evidence/port-cnmv/split-v2/holdout/**
                evidence/port-cnmv/holdout/**
                evidence/g0g/holdout/**  evidence/g1/holdout/**
                evidence/g2/holdout/**
NOT AUTHORIZED  PORT-CNMV-2
```

- No semantic access to any `*/holdout/*` path: no reads, greps,
  globs, manifest traversal, tests or tooling resolving into them.
  SEAL files are integrity anchors, not an opening.
- No network. All bytes replay via `EVIDENCE_IMPORT` manifests.
- `hardening/public-release` is not merged/cherry-picked/rebased
  during the scientific program; integration happens only after the
  CORE-GAP freeze (§12).
- Historical gate evidence is immutable (AGENTS.md).

## 3. Allowed evidence

```text
CNMV DEV          evidence/port-cnmv/split-v2/dev/** (4 targets,
                  22 modifier docs, manifest-isolated)
BdE seen corpora  all non-holdout captured bytes + frozen ledgers:
                  g0*/**, g1/dev, g2/dev, g2/g2.2/dev-equivalence,
                  cov/**, port-cnmv/dev (v1, superseded but seen)
OSS recon         evidence/oss-recon/** + new recon under RUBRIC.md
```

## 4. Census (step 2 result — evidence/core-gap/census.json)

Detector counts (mention-level upper bounds; operative subsets are
established per workstream):

| family | CNMV dev | BdE seen |
|---|---|---|
| F1 seccion heads / refs | 48 / 127 | 117 / 358 |
| F2 unnumbered disposición heads | 33 | 62 |
| F3 apartado↔número two-level refs | 65 | 8 |
| F4 image nodes | 576 | 1020 |
| F5 continuation items (heuristic) | 114 | 7638 |
| F6 `pasa a ser` raw / structural | 15 / 6 | 150 / 8 + EXP-B1 |

EXP-B1 (frozen): 85 BdE redesignation clauses, 15 CODE_REDESIGNATION
edges, verdict `PORT` for the words-to-data redesignation-edge
mechanism (algorithm only).

## 5. OSS recon adoption register

Recorded per RUBRIC.md; a `PORT`/`ADOPT` verdict authorizes use
**inside this program only**, under the fail-closed guards the
falsification established.

| workstream | project | component | verdict | guards |
|---|---|---|---|---|
| A | words-to-data @ccc44e0 | `Redesignations`/`TreeDiff::moved`, `legislature.redesignated_as` | PORT (EXP-B1 adjudicated) | refuse unless O1 proven + single old-key ledger row; refuse when both keys have proven independent existence; journal ambiguity |
| A | words-to-data | ADR-0001 "paths locate, links carry continuity" | PATTERN | — |
| A | legaldocml-akn (suppl.) | `<previous>` edge + `<mappings>` wId↔eId ledger + `renumbering` mod type | PATTERN | producer-asserted, no byte evidence |
| A | uslm @10033899 | `redesignate` action + `renumbered`/`transferred` tombstone status | PATTERN | — |
| A | legislation-gov-uk | TOES effect rows (curated, not proven) | PATTERN | — |
| A | xmldiff @0b16e5e5 | `MoveNode` similarity pairing | DISCARD | heuristic pairing cannot fail closed |
| B | citation @953c03d3 | ordered component array + composed key shape | PATTERN | outside-in grammar not portable |
| B | refex @a74242a5 | enumeration expansion, span-carrying cites | PATTERN | — |
| B | legalize-pipeline @5596f1d4 | ES struct-token vocabulary; skip-and-log verb filter; Jaccard negative result | PATTERN | fuzzy matching not portable |
| B | legislation-gov-uk | `(kind,number)` URI grammar, non-normalized spelling | PATTERN | — |
| B | cobalt @cfae0245 (LGPL) | FRBR URI decompose/compose | PATTERN | LGPL — no adoption |
| C | metalex-cwa-15710 | `LocalNamingConventionMethod` {individual, ordinal, positional} | PATTERN | — |
| C | eli-subdivisions v2 | `unp` positional kind-token; annex internals excluded | PATTERN | — |
| C | uslm @10033899 | 4-slot identity: @id / @identifier / @temporalId / @name | PATTERN | — |
| C | legaldocml-akn (suppl.) | implicit positional eId for unnumbered nodes | PATTERN | — |
| C | indigo (suppl.) | `hcontainer` positional eIds unstable under reparse | PATTERN | — |
| D | boe-image-channels | 3-channel inventory + authenticity hierarchy | PATTERN | — |
| D | pypdf @095d5af1 (BSD-3) | embedded image stream extraction | PORT **candidate** — gated on byte-equality falsification (EXP-D1) before any use | pin version; raw stream bytes only |
| D | eurlex-cellar-formex | fmx4 zip = XML + image files | PATTERN | — |
| D | legislation-gov-uk | CLML Image→Resource indirection; deliberate non-ID | PATTERN | — |
| D | ALTO/OCR layers | — | DISCARD (no official layer exists) | — |
| D | PyMuPDF/Ghostscript/poppler renderers | — | DISCARD (AGPL/GPL; rendered output is derived, not byte-provable) | — |
| D | BOE consolidada API | — | DISCARD (synthetic consolidation) | — |

Cross-cutting recon conclusions:

1. **No prior art carries per-level declaration provenance** — every
   compositional scheme mints a flat locator. RegDelta's
   per-component `proof_components` is novel; no adoption risk.
2. **Outside-in vs inside-out**: all citation parsers assume
   outside-in declaration; Spanish `de`-chains are inside-out. Any
   composition model must separate declaration order from hierarchy
   order.
3. **Anonymous identity is always minted, never source-derived** —
   the honest encoding is a *kind/method tag* that cannot be confused
   with a declared locator (MetaLex `positional`, ELI `unp`).
4. Debt flag: `annexmap.py` positional anejo fill emits `anejo:N`
   spellings indistinguishable from declared ones — WS-C must address
   this before it can feed a `binding_proof`.
5. **Image evidence needs no OCR**: three official byte-provable
   channels exist; the signed PDF is the only authentic format.

## 6. Workstream definitions

### A — redesignation/renumbering continuity

Add the missing semantic: an explicit, evidence-backed edge

```text
old_locator --REDESIGNATED_TO--> new_locator
```

Old and new remain distinct locators; continuity is an edge with
proof, not locator mutation or positional guessing. Emission only when
O1 attribution is proven AND both endpoints are declared in the
clause. Fail-closed guards (from EXP-B1): refuse when O1 not
TARGET_PROVEN; refuse when new key already has proven independent
existence as a distinct subject (FALSE_MERGE guard); journal
ambiguity.

Cases (all DEV/seen):
- A1 former FLDs: `norma:49.apartado:3.letra:n → número 4`,
  `norma:49.apartado:4 → número 5` (BOE-A-2025-8206 → 2010-13162).
- A2 bulk renumber `apartados 13–16 → 10–13` (BOE-A-2011-19550 →
  2008-20895).
- A3 `norma 11.ª → norma 10.ª` (BOE-A-2025-8206 → 2010-13162).
- A4 all BdE redesignations (EXP-B1 corpus: 15 edges incl. the
  `estado:FI 16-1 → FI 16-1.2` repair).
- A5 chains: consecutive redesignations compose.
- A6 conflict/ambiguity: multiple old→new candidates, distinct-cardinality
  ranges, pre-existing new key → refuse/journal.
- A7 delete+add vs move: renumber+retext same clause.
- A8 query/history projection through edges.
- Adversarial: "pasa a ser aplicable", "pasa a denominarse «X»"
  (nominal, non-structural), 3→4 with existing 4, N→M cardinality
  mismatch.

PASS: zero false merges, zero invented continuity, provenance
preserved, explicit abstention when continuity unprovable.

### B — locator composition and hierarchy

Generic hierarchy model over existing `LocatorKind`s — not more
`_compose_keys` branches. Covers `seccion:` materialization and
`apartado X) → número N` paths. Every composed component requires
declaration provenance (`proof_components` discipline already in
`SubjectRef`).

Constraint: **BdE locator output byte-identical** unless a specific
case is preregistered as repaired (register in expected-deltas.json).
CNMV richer paths only when every component is independently proven.

### C — anonymous structural identity

Covers unnumbered disposiciones and unnumbered continuation items.
Investigate anchored-subject representation: identity bound to
official evidence span without fabricating a canonical locator the
source never declared. Terminals: `ANCHORED_SUBJECT_PROVEN` /
`HONEST_ABSTENTION_IS_CORRECT` / `MODEL_EXTENSION_UNSAFE`. Must fail
closed when evidence does not uniquely identify the node. Distinct
from locator composition and from redesignation continuity.

### D — image/representation evidence

Image-only annexes: exhaust official channels first (BOE diario XML
`<img>` assets, boe_doc/boe_pdf image objects, official image
endpoints). NO OCR. Terminals: `REPRESENTATION_PROVEN` /
`OFFICIAL_BYTES_UNAVAILABLE` / `NO_DETERMINISTIC_BINDING`. Distinguish
source acquisition failure from semantic binding failure; a negative
result is valid.

## 7. Common evaluator and regression discipline

Baselines (this freeze): `evidence/core-gap/baseline/bde-dev/` (fresh
evaluate_g2 replay at base) and `evidence/core-gap/baseline/cnmv-*`
(probe replay). Note: the fresh BdE replay is the regression baseline
— it already reflects runtime drift since the frozen g2.2 ledger.

Every replayed row classifies as exactly one of
`IDENTICAL` / `EXPECTED_DELTA:<case>` / `UNEXPECTED_DELTA`
(`scripts/core-gap/diff_runs.py`, registry
`evidence/core-gap/expected-deltas.json`). Any `UNEXPECTED_DELTA` on a
previously proven corpus blocks until adjudicated.

Every new semantic capability requires: positive fixture, negative
near-neighbour, ambiguous fixture, mutation test, round-trip/replay
determinism, provenance trace.

## 8. Execution order

```text
A to terminal → B (if safe) → C → D → cross-workstream interaction
tests → replay all permitted corpora → differential analysis →
mutation/adversarial per new capability → full test suite →
consolidated REPORT → commit+publish evidence chain
```

## 9. Safety invariants (checked every run)

```text
FALSE_FACT                = 0    FALSE_BINDING    = 0
FALSE_LOCATOR_DECLARATION = 0    FALSE_CONTINUITY = 0
no silent dropping (all exclusions stay in accounting)
no target/BOE-ID/year special-casing in grammar or core
determinism: same inputs → byte-identical artifacts on re-run
```

## 10. Global stop conditions (only these)

```text
HOLDOUT_ACCESS
PROVENANCE_VIOLATION
PREREG_INVALIDATED
GLOBAL_CORE_REGRESSION  (UNEXPECTED_DELTA not adjudicable inside
                         the program's own discipline)
UNRECOVERABLE_EVIDENCE_CONTAMINATION
```

## 11. Deliverables

`evidence/core-gap/`: FREEZE.json, census.*, PREREG.md (this file),
recon fichas under evidence/oss-recon/, baseline/, runs/<id>/,
expected-deltas.json, per-workstream terminal evidence, REPORT.md.

## 12. Post-freeze integration (pre-authorized)

After the scientific result is frozen: seal CORE-GAP, merge
`hardening/public-release`, resolve conflicts, run the full hardening
suite, re-replay semantics, verify packaging/license/security, publish
a clean candidate branch, produce the consolidated final report.
