# leos — Legislation Editing Open Software (EC)

## 1. Source freeze

- repo: leos group on code.europa.eu (canonical); public mirror
  `l-e-x/leos` on GitHub inspected
- url: https://code.europa.eu/leos —
  mirror https://github.com/l-e-x/leos
- commit/tag inspected: mirror HEAD
  `7a8399788e3e6e03013982b77de457fe5f06b2dd` (2020-04-18);
  canonical release stream reviewed via Joinup/Interoperable-Europe
  release notes through LEOS 5.2.4.x (2024+)
- review date: 2026-09-16
- license: EUPL-1.2
- license ref (hash/path): `LICENSE` in repo root (EUPL-1.2 text);
  Joinup solution page states EUPL 1.2

## 2. Problem fit

RegDelta problem(s) evaluated against:

- `problems/jurisdiction-profiles.md` — primary: LEOS is the
  reference implementation of an *institutional profile* of AKN
  (AKN4EU) — i.e., how an organization layers its grammar on a
  generic legal-XML core
- `problems/annexes-and-tables.md` — secondary: structured annex
  handling (level annexes vs article annexes)
- `problems/stable-node-identity.md` — secondary: configurable
  autonumbering of AKN elements

Component(s) of the project addressing each problem:

- AKN4EU subschema usage — LEOS restricts Akoma Ntoso to the EU
  interinstitutional profile; its *restrictive-by-design* stance is
  documented policy ("as restrictive as possible … helps drafters
  follow the rules")
- document template + configuration model: document templates,
  configuration JSON, structure XMLs stored in the repository DB —
  the profile surface is configuration-driven
- CKEditor plugin-per-AKN-element architecture (`leos-js`
  plugins for paragraphs, subparagraphs, points, alinea)
- act model: an act = set of elements (explanatory memorandum,
  legal text, annexes) with global metadata propagated across
  sub-elements; major/minor version management with split-mode
  comparison

## 3. Document assumptions

- input format: AKN4EU XML produced *by the tool itself* — LEOS is
  an authoring environment, not an importer of third-party text
- presumes already-structured text?: YES — drafting happens inside
  the tool; paste-from-Word exists as an import aid only
- receives consolidated documents?: NO — it produces proposals and
  versioned drafts; consolidation is downstream (OP/CELLAR)
- IDs come from the source or are minted by the system?: minted —
  configurable autonumbering mints element ids; document identity
  comes from the repository/templates
- treatment of annexes/tables/images: annexes are managed
  components (level vs article annexes); tables supported via
  editor plugins; images as attachments
- what "a version" means here: proposal/document version inside a
  CMIS repository — editorial versioning, not legal time

## 4. Evidence-rule compatibility

| question | answer |
|---|---|
| Can output trace to official source bytes? | NO — LEOS *produces* the source; there is no upstream evidence layer |
| Can claim trace to exact structural span? | PARTIAL — AKN4EU element addressing inside its own documents |
| Deterministic? | PARTIAL — deterministic services, but the core loop is interactive human editing |
| Can ambiguity remain unresolved? | NO by design — the drafter resolves; that is the product |
| Can it fail closed rather than guess? | NO — authoring tool, no abstention surface |
| Requires synthetic consolidation? | NO (produces drafts; consolidation is external) |
| Requires normalized/re-written legal content? | YES — content lives as AKN4EU markup |
| Preserves original representation separately? | YES — versioned documents retained in the repository |
| Supports temporal provenance? | PARTIAL — document versioning and change markers; legal-time modeling is minimal |

## 5. Technical extraction

- **Restrictive profile doctrine**: LEOS' explicit design rule —
  restrict the generic grammar so that only valid structures are
  producible — is the same intuition behind a fail-closed RegDelta
  jurisdiction profile: a profile should *narrow* what can be
  claimed, not widen it
- **Configuration-driven profile surface**: document templates +
  configuration JSON + structure XMLs per document type — prior art
  for how a `Profile` object could be packaged in RegDelta
  (grammar + locator scheme + doctype config as data, not code)
- annex modeling split (level annexes vs article annexes) — prior
  art for `annexes-and-tables` profile decisions
- autonumbering as configuration — minted ids are a *profile
  concern*, reinforcing that RegDelta's evidence-derived locators
  must stay distinct from system-minted numbering

## 6. Integration cost

- language/runtime: Java EE (WAR) + Maven; AngularJS/CKEditor
  front-end; CMIS repository backend
- dependencies: heavy — application server, CMIS store, relational
  DBs, annotation service
- size: full collaborative drafting platform
- API stability: evolving; canonical code moved between Joinup
  releases and code.europa.eu
- maintenance: active within EC; community contributions secondary
- license constraints: EUPL-1.2 — strong copyleft; rubric rule 5
  defaults to PATTERN
- vendoring/port feasibility: none — application, not library
- coupling surface introduced into RegDelta: adopting any of it
  presumes AKN4EU as the document model — excluded by the evidence
  contract

## 7. Delta against RegDelta

| capability | upstream | RegDelta | gap/use |
|---|---|---|---|
| stable subject identity | minted element ids via autonumbering | evidence-derived locator_key | different direction: LEOS assigns ids to authored text; RegDelta derives them from captured bytes |
| operation extraction | none — amendments are drafted in the tool | deterministic clause parsing | disjoint |
| representation binding | document == representation (authoring) | binding_proof over official bytes | disjoint problem classes |
| version lifecycle | repository versioning (editorial) | legal-time lifecycle (O3) | editorial vs legal time — different notions of "version" |
| provenance | version history in repo | snapshots + proofs | RegDelta stronger for audit |
| fail-closed | no | hard gates | incompatible evidence models |

## 8. Minimal falsification experiment

Not required — verdict is PATTERN, not ADOPT/PORT.

## 9. Verdict

PATTERN

secondary_value: the AKN4EU profile mechanism it implements
(restrictive subschema + per-doctype configuration) is the
*institutional* reference shape for `jurisdiction-profiles.md`;
useful when designing how a RegDelta `SourceProfile` should be
packaged and versioned.

## 10. Decision rationale

- what_we_reuse: the profile-as-restriction doctrine; the idea that
  a jurisdiction profile is a *packaged configuration layer*
  (templates + grammar rules + numbering policy) over a shared core
- what_we_explicitly_do_not_reuse: the entire implementation
  (Java/CMIS/editor stack), AKN4EU as document model, editorial
  versioning as lifecycle semantics
- why_this_survives_or_fails_RegDelta_evidence_rules: LEOS' truth
  is what a drafter produced — a legitimate model for legislative
  authoring, orthogonal to RegDelta's contract (claims proven from
  captured official bytes or abstained). It cannot emit
  binding_proof-grade evidence, and nothing in it needs to

## 11. CORE-GAP supplement (2026-09-19 recon)

AKN4EU/ELI canonical scheme mints `unp`-typed positional ids for
unnumbered paragraphs (see eli-subdivisions ficha) — consistent with
LEOS configurable autonumbering: all observed production systems mint
positional identity for anonymous nodes; none treats it as
source-declared. The differentiator RegDelta must keep is labeling
the mintedness (MetaLex method enum / ELI kind token).
