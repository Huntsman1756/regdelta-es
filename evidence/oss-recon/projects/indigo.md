# indigo

## 1. Source freeze

- repo: laws-africa/indigo (+ laws-africa/indigo-akn)
- url: https://github.com/laws-africa/indigo
- commit/tag inspected: `652e58fca163f5974b96c4979dea563cd8c85919`
  (main, pushed 2026-08-28); indigo-akn @
  `bc3f012371798496248dc362eeb906e5ecfc946e`
- review date: 2026-09-15
- license: LGPL-3.0 (indigo); MIT (indigo-akn)
- license ref (hash/path): `LICENSE` @ 652e58f — GNU Lesser GPL v3 text

## 2. Problem fit

RegDelta problem(s) evaluated against:

- `problems/version-chains.md` — primary
- `problems/jurisdiction-profiles.md` — secondary
- `problems/representation-binding-evidence.md` — secondary (weak)
- `problems/annexes-and-tables.md` — secondary

Component(s) of the project addressing each problem:

- `indigo_api/models/amendments.py` — `Amendment` model:
  work→work dated edge; `order_further` sorts same-date amendments
  by (date, amending_work.date, subtype, number)
- work/expression/document model — point-in-time = expression set
- commencement/uncommenced-provision tracking
  (`update_commencements`, `_work_uncommenced_provisions_detail`)
- consolidation timeline UI (`timeline/_edit_consolidation`)
- `xmldiff` dependency with attribute-ignore for document comparison
- `indigo-akn` — HTML→AKN grammars, per-jurisdiction grammar support

## 3. Document assumptions

- input format: Akoma Ntoso XML; HTML imported and normalized to AKN
- presumes already-structured text?: normalized to AKN on import
- receives consolidated documents?: consolidation is an editorial
  product built inside the platform, not an input
- IDs come from the source or are minted by the system?: FRBR URIs
  minted per work (`/akn/xx/act/...`); `eId`s managed in-document
- treatment of annexes/tables/images: AKN component attachments;
  tables via AKN `table`; images as attachment components
- what "a version" means here: a `Document` = expression of a `Work`
  at an expression_date; amendments are dated edges between works

## 4. Evidence-rule compatibility

| question | answer |
|---|---|
| Can output trace to official source bytes? | PARTIAL — imported docs normalized to AKN; source-of-truth is the edited document, not raw official bytes |
| Can claim trace to exact structural span? | PARTIAL — AKN `eId` addressing inside documents |
| Deterministic? | PARTIAL — platform is deterministic software, but amendment/consolidation facts are human-curated records |
| Can ambiguity remain unresolved? | NO by design — an editor resolves it; that is the product |
| Can it fail closed rather than guess? | NO — human judgement is the resolution mechanism; there is no abstention surface |
| Requires synthetic consolidation? | YES — consolidated expressions are the core product |
| Requires normalized/re-written legal content? | YES — AKN normalization is the storage format |
| Preserves original representation separately? | YES — every expression is a stored document |
| Supports temporal provenance? | YES — strong: dated expressions, commencements, amendment edges |

## 5. Technical extraction

- `Amendment.order_further` — `indigo_api/models/amendments.py`:
  same-date ordering = (amendment date, amending work date, subtype,
  natural-sorted number). Compare with the adjudicated same-date hop
  ordering in our G2.1 evaluator
- commencement + uncommenced-provision model —
  `update_commencements`, `_provisions_tree` templates
- per-country doctype/language/profile system (`indigo_za` etc.) —
  the reference shape for `problems/jurisdiction-profiles.md`
- `xmldiff` (patched, attribute-ignoring) for document comparison —
  `pyproject.toml` deps
- `indigo-akn` grammars: `slaw`-style grammars for HTML→AKN —
  candidate grammar decomposition prior art

## 6. Integration cost

- language/runtime: Python/Django application (not a library)
- dependencies: large — Django, postgres ecosystem, cobalt, lxml
- size: full editorial platform
- API stability: declared Production/Stable
- maintenance: active (pushed 2026-09-05)
- license constraints: LGPL-3.0 — copyleft; indigo-akn is MIT
- vendoring/port feasibility: not a candidate — it is an app, not a
  component; pattern extraction only
- coupling surface: adopting any of it means adopting AKN as storage
  model — excluded by our evidence contract

## 7. Delta against RegDelta

| capability | upstream | RegDelta | gap/use |
|---|---|---|---|
| stable subject identity | FRBR URIs + AKN eIds | locator_key (no minted identity) | their IDs are minted editorially, not proven from source |
| operation extraction | human editors write amendment instructions | deterministic clause parsing | different evidence class entirely |
| representation binding | expressions as stored documents | binding_proof + byte evidence | RegDelta stronger for provability; theirs richer as product |
| version lifecycle | strong — dated expressions, commencements | O3 lifecycle + chain metrics | prior art for commencement/uncommenced modeling |
| provenance | user/task history (django-reversion) | snapshots + proofs, machine-verifiable | RegDelta stronger for audit; theirs for edit history |
| fail-closed | no — editor resolves | hard gates | incompatible evidence models |

## 8. Minimal falsification experiment

Experiment: replay indigo's same-date amendment ordering rule
(date, amending_work.date, subtype, number) over the adjudicated
same-date hop cases from the frozen G2.1 DEV chain ledger.

PASS criterion (fixed before execution): the rule reproduces the
adjudicated ordering for every case, or identifies a case as
genuinely ambiguous (no source-declared order) rather than silently
reordering it.

FAIL criterion: it emits an order that contradicts an adjudicated
case, or silently imposes order the source never declared.

## 9. Verdict

PATTERN

secondary_value: `indigo-akn` (MIT) grammar decomposition is PATTERN
material for `jurisdiction-profiles`; the commencement/
uncommenced-provision model is the strongest external reference for
`version-chains` and O3 lifecycle semantics. LGPL + human-curated
evidence model rule out ADOPT/PORT regardless of technical quality.

experiment outcome: EXP-L1 (`evidence/cov/exp-l1/`) replayed the
same-date ordering tuple over every order-sensitive group in both
frozen ledgers — deterministic on official metadata, zero hard
contradictions, never imposes an undeclared order. Verdict
`PATTERN_CONFIRMED` — usable as a deterministic ordering prior to be
re-proven per case; not an adoption.

## 10. Decision rationale

- what_we_reuse: the work/expression/amendment-edge lifecycle model,
  the same-date ordering rule as a falsifiable ordering prior, the
  commencement/uncommenced-provision distinction, the jurisdiction
  profile separation shape
- what_we_explicitly_do_not_reuse: AKN as storage format, the
  editorial-consolidation model, minted FRBR identity, any
  LGPL-covered code
- why_this_survives_or_fails_RegDelta_evidence_rules: indigo's truth
  is what an editor recorded — an excellent model for a publishing
  platform, and the opposite of RegDelta's contract (facts must be
  proven from official bytes or abstained). Nothing in its data
  model can produce a `binding_proof`-grade claim, but its
  lifecycle/versioning semantics are the best-documented prior art
  for how legal time should be modeled
