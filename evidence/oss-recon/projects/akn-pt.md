# akn-pt — perfil nacional portugués de Akoma Ntoso

## 1. Source freeze

- repo: dapl-sggov/akn-pt
- url: https://github.com/dapl-sggov/akn-pt
- commit/tag inspected: `e65d84cbf04b31c5cf10f613b94769ea59cbeb18`
  (main, pushed 2026-07-28); spec v0.1.0 / ELI-PT v0.2 / corpus v0.2
- review date: 2026-09-16
- license: EUPL-1.2 (SPDX EUPL-1.2, `LICENSE`)
- license ref (hash/path): `LICENSE` @ e65d84c — EUPL-1.2 text

## 2. Problem fit

RegDelta problem(s) evaluated against:

- `problems/jurisdiction-profiles.md` — primary: this is the
  closest observed artifact to "common core + jurisdiction profile"
  done the way RegDelta would need it — a *new* national profile
  built on the AKN core with every profile surface made explicit

Component(s) of the project addressing each problem:

- `docs/spec/pt/` — 18-chapter authoritative national spec:
  profile semantics written *before* code
- `schema/xsd/` — modular 4-file XSD subset of AKN core
- `schema/schematron/` — 9 patterns / 3 validation phases on top of
  the XSD (the "restrictive overlay" mechanism in action)
- `eli-pt/` — national URI scheme (ELI-PT over canonical
  `data.dre.pt` / INCM) — the jurisdiction's identity namespace
  kept as a separable artifact
- `mapping/v0.1.0/` — explicit structure table: PT structural
  concepts → AKN elements, 9 doctypes covered
- `corpus/` — 8 real diplomas whose ELI resolves against the DR;
  a previous synthetic corpus was *removed* for not resolving —
  the fixture discipline RegDelta already practices
- `validator/` — Python 3.12 CLI+lib+Docker, 51 tests

## 3. Document assumptions

- input format: AKN-PT XML (markup of Portuguese legislative
  diplomas, produced by the profile's own tooling/editor)
- presumes already-structured text?: YES — markup is a production
  act; the corpus diplomas are normalized copies of DR content
- receives consolidated documents?: NO — point-in-time documents,
  not consolidations
- IDs come from the source or are minted by the system?: minted —
  ELI-PT URIs assigned per profile rules; eIds minted in-document
- treatment of annexes/tables/images: AKN attachment/table/img
  machinery inherited from core
- what "a version" means here: an AKN expression of a diploma; no
  amendment-lifecycle machinery

## 4. Evidence-rule compatibility

| question | answer |
|---|---|
| Can output trace to official source bytes? | PARTIAL — corpus diplomas carry real ELIs resolving to the DR, but the AKN body is a normalized copy, not byte-bound evidence |
| Can claim trace to exact structural span? | YES — AKN eId addressing within the marked document |
| Deterministic? | YES — XSD + Schematron validation is deterministic |
| Can ambiguity remain unresolved? | PARTIAL — schema/Schematron can encode it; the corpus workflow resolves editorially |
| Can it fail closed rather than guess? | YES — the validator rejects rather than repairs; this is the strongest evidence-rule property observed in the profile ecosystem |
| Requires synthetic consolidation? | NO |
| Requires normalized/re-written legal content? | YES — AKN markup is the storage format |
| Preserves original representation separately? | PARTIAL — ELI points to the official DR publication; body is normalized |
| Supports temporal provenance? | PARTIAL — ELI/FRBR dating; no lifecycle-event machinery |

## 5. Technical extraction

- **The profile artifact checklist** — the single most valuable
  observation for `jurisdiction-profiles.md`. A complete
  jurisdiction profile, as actually built, consists of:
  spec document + XSD subset + Schematron phases + national
  identifier scheme + doctype mapping table + verified real corpus
  + validator. Translating to RegDelta terms, a `SourceProfile`
  would need: locator grammar + ordinal/citation vocabulary +
  dispositive clause grammar + target-ref derivation + state-code
  families + a *verified fixture corpus* + a profile-local
  validator — with the core (ownership → locator → lifecycle →
  binding → proof) untouched
- **Spec-first discipline**: 18-chapter authoritative spec exists
  before/independently of the validator — a profile is a
  documented contract, not just code
- **Corpus honesty precedent**: their own history removed a
  synthetic corpus whose ELIs did not resolve — direct prior art
  for RegDelta's "fixtures must be real captured evidence" rule
- **Validation phasing**: Schematron split into 3 phases over 9
  patterns — prior art for layered profile validation (syntax →
  structure → jurisdiction rules)

## 6. Integration cost

- language/runtime: Python 3.12 (validator); spec/schema artifacts
  language-agnostic
- dependencies: small — lxml-family validation stack
- size: small project (v0.1.0, ~96 commits, niche visibility)
- API stability: pre-1.0, young — profile vocabulary still moving
- maintenance: active but small bus factor
- license constraints: EUPL-1.2 — rubric rule 5 → PATTERN by
  default
- vendoring/port feasibility: nothing to port — the value is the
  *shape* of the profile package, not its code
- coupling surface introduced into RegDelta: zero (pattern only)

## 7. Delta against RegDelta

| capability | upstream | RegDelta | gap/use |
|---|---|---|---|
| stable subject identity | ELI-PT URIs + eIds (minted) | evidence-derived locator_key | minted vs proven — opposite identity sources |
| operation extraction | none — no amendment-clause machinery | deterministic clause parsing | akn-pt has no operational layer at all |
| representation binding | document structure = representation | binding_proof over official bytes | RegDelta's evidence problem is absent upstream |
| version lifecycle | none (single-expression corpus) | O3 lifecycle + chains | RegDelta unique |
| provenance | ELI references the DR publication | snapshots + proofs | theirs is a link, ours is proof |
| fail-closed | validator rejects invalid docs | abstain + journal | convergent intuition, different layer |

## 8. Minimal falsification experiment

Not required — verdict is PATTERN, not ADOPT/PORT. When a
`SourceProfile` subsystem is preregistered, the falsification
experiment should replay akn-pt's checklist: can the BdE surface be
expressed as (locator grammar + vocabulary + clause grammar +
identifier scheme + fixture corpus + validator) without touching
the core pipeline?

## 9. Verdict

PATTERN

secondary_value: TEST-CORPUS-shaped precedent — a corpus of real,
identifier-resolving instruments as the fixture policy for any
future jurisdiction profile (their synthetic corpus was deleted
for failing exactly this test).

## 10. Decision rationale

- what_we_reuse: the complete profile-artifact shape (spec +
  schema subset + schematron phases + identifier scheme + mapping
  table + verified corpus + validator); the spec-first discipline;
  the real-fixture precedent
- what_we_explicitly_do_not_reuse: AKN as document model, ELI-PT
  naming, the validator code, the corpus content (Portuguese law —
  wrong jurisdiction for RegDelta's next target: CNMV/ES)
- why_this_survives_or_fails_RegDelta_evidence_rules: akn-pt is a
  markup profile — its documents are authored artifacts, not
  evidence. But as *prior art for how to package a jurisdiction
  profile* it is the best observed reference: every profile surface
  is an explicit, reviewable artifact. That packaging discipline is
  what RegDelta's portability layer needs, and it costs nothing to
  adopt conceptually
