# legaldocml-akn — OASIS LegalDocML / Akoma Ntoso

## 1. Source freeze

- repo: OASIS LegalDocML TC normative documents (not a code repo)
- url: https://docs.oasis-open.org/legaldocml/ — `akn-core/v1.0`
  (Part 1 vocabulary + Part 2 specifications + XML schemas) and
  `akn-nc/v1.0` (Naming Convention)
- commit/tag inspected: `akn-nc-v1.0-os` OASIS Standard
  2019-02-21; `akn-core-v1.0` OASIS Standard 2018-08-31;
  AKN 3.0 schema namespace WD17/CSD13 drafts cross-checked
- review date: 2026-09-16
- license: OASIS "RF on Limited Terms" (specification); schemas
  normative as separate machine-readable files
- license ref (hash/path): OASIS IPR Policy §RF on Limited Terms,
  docs.oasis-open.org/legaldocml/akn-nc/v1.0/os/ notices section

## 2. Problem fit

RegDelta problem(s) evaluated against:

- `problems/jurisdiction-profiles.md` — primary
- `problems/stable-node-identity.md` — primary (eId/wId duality)
- `problems/version-chains.md` — secondary (FRBR expression dating)
- `problems/representation-binding-evidence.md` — secondary
  (component/portion IRI addressing)

Component(s) of the project addressing each problem:

- FRBR Work/Expression/Manifestation/Item layering (NC §4.5–4.9) —
  the canonical model separating legal identity from any of its
  representations
- `eId` vs `wId` attribute duality (NC §5.4–5.5): `eId` =
  expression-level structural position id (may change when the text
  is renumbered), `wId` = work-level identifier tied to the legal
  provision's identity (stable across renumbering). This is exactly
  the distinction RegDelta needs between a *locator spelling* and a
  *subject identity* under redesignation
- `<meta>`/`<identification>` block: source, lifecycle events
  (`eventRef`), references — metadata separated from `<body>`
- profile mechanism: AKN is deliberately generic; jurisdiction
  profiles = subschema restrictions + naming-convention
  specializations + Schematron rules (AKN4EU, akn-pt, indigo
  grammars are the three observed instantiation shapes)
- `docJurisdiction`, `FRBRcountry`, `FRBRsubtype` metadata slots —
  the standard's own portability surface

## 3. Document assumptions

- input format: AKN XML authored or converted upstream — the
  standard governs documents a producer *marks up*, not evidence a
  system *binds*
- presumes already-structured text?: YES — markup is a production
  act (authoring, conversion, editorial normalization)
- receives consolidated documents?: consolidation is a producer
  concern; the model can *express* point-in-time versions as
  expressions but does not produce them
- IDs come from the source or are minted by the system?: minted —
  FRBR IRIs and eIds are assigned by the producing system per the
  naming convention; the source text does not carry them
- treatment of annexes/tables/images: first-class components
  (`<attachment>`/componentInfo for annexes, `table`, `img`)
- what "a version" means here: an Expression — content of a Work
  at a point in time/language; temporal identity is Work-level +
  `FRBRdate` events

## 4. Evidence-rule compatibility

| question | answer |
|---|---|
| Can output trace to official source bytes? | NO — AKN content is a normalized product; the official source is referenced by IRI, not carried as byte evidence |
| Can claim trace to exact structural span? | YES — eId/wId + component/portion IRI addressing is a precise span model |
| Deterministic? | YES — naming convention and schema are deterministic; markup application is a human/editorial act |
| Can ambiguity remain unresolved? | PARTIAL — the format permits it; producing workflows typically resolve it editorially |
| Can it fail closed rather than guess? | PARTIAL — validation exists (XSD/Schematron) but there is no abstention concept in the model |
| Requires synthetic consolidation? | NO |
| Requires normalized/re-written legal content? | YES — that is what AKN is |
| Preserves original representation separately? | PARTIAL — Manifestation/Item links can point at the source artifact, but the body is normalized |
| Supports temporal provenance? | YES — strong: FRBR expression dating, lifecycle events, references |

## 5. Technical extraction

- The **Work/Expression/Manifestation** split as the reference
  vocabulary for RegDelta's portability boundary — a *three*-layer
  mapping, not two:
  subject identity (`subject` + `locator_key` as its evidence-
  derived spelling) ≈ Work-like identity;
  the subject's legal state at a point in time (what a bound
  representation asserts about the subject under a given
  publication) ≈ Expression-like state;
  captured XML/PDF/image/table bytes ≈ Manifestation-like
  evidence. The intermediate layer matters: a single subject
  identity carries a *different* current legal text after a
  modification, and the bytes proving it are yet another thing —
  collapsing Expression→Manifestation would re-merge legal state
  with evidence artifact, which is exactly the conflation
  `binding_proof` exists to prevent. A subject identity surviving
  renumbering is the wId concept RegDelta lacks as a first-class
  object
- `eId` renumber semantics: eIds follow position, wIds follow
  identity — prior art for `problems/stable-node-identity.md` and
  for the redesignation edge model (EXP-B1)
- **Profile shape**: AKN profiles are *restrictions* of a superset
  schema + naming specializations — confirms that a RegDelta
  jurisdiction profile should be a restrictive overlay on a core
  grammar, not an extension
- `<identification>` vs `<body>` separation — prior art for keeping
  provenance/metadata out of the evidence-carrying content

## 6. Integration cost

- language/runtime: n/a — standard + XSD, no code to integrate
- dependencies: adopting the format means XML toolchain + a
  producer pipeline (editorial or conversion)
- size: spec suite is large (vocabulary, naming, schemas, mod/mods)
- API stability: OASIS Standard, frozen at v1.0; AKN4EU builds on it
- maintenance: TC dormant-to-slow; standard is stable
- license constraints: spec RF-Limited-Terms; schemas freely usable
- vendoring/port feasibility: not applicable — it is a format spec;
  adopting it as storage is a full re-platforming
- coupling surface introduced into RegDelta: if adopted as storage,
  total; as a *conceptual pattern*, zero

## 7. Delta against RegDelta

| capability | upstream | RegDelta | gap/use |
|---|---|---|---|
| stable subject identity | wId (work-level, minted) | locator_key (spelling-derived) | AKN's wId/eId split is the reference for separating subject identity from locator spelling under redesignation |
| operation extraction | out of scope — AKN marks documents, not amendment clauses | deterministic clause parsing + operations | RegDelta unique; no overlap |
| representation binding | span addressing inside a normalized document | binding_proof over captured official bytes | opposite direction: AKN addresses authored structure; RegDelta proves source evidence |
| version lifecycle | FRBR expression dating | O3 lifecycle + chain | convergent model; AKN vocabulary is the canonical naming |
| provenance | metadata block, editorial | snapshots + proofs, machine-verifiable | RegDelta stronger |
| fail-closed | validation-only | abstain + journal | incompatible: AKN has no abstention semantics |

## 8. Minimal falsification experiment

Not required — verdict is PATTERN, not ADOPT/PORT. If a future gate
proposes minting canonical subject URIs, the falsification
experiment would be: apply the AKN naming-convention wId/eId split
to the frozen COV-2 redesignation/collision cases and check whether
any proven binding becomes *less* precise.

## 9. Verdict

PATTERN

secondary_value: the naming convention's wId/eId semantics are the
reference design if RegDelta ever needs subject identity decoupled
from locator spelling (redesignation, renumbering).

## 10. Decision rationale

- what_we_reuse: the FRBR W/E/M layering as a three-level
  vocabulary for the portability boundary (subject identity /
  legal state at a time / captured bytes); the eId-vs-wId
  distinction as prior art for stable subject identity under
  renumbering; the profile-as-restriction mechanism shape
- what_we_explicitly_do_not_reuse: AKN as a storage or
  representation format — adopting it would require normalizing
  official bytes into authored markup, which is precisely what
  RegDelta's evidence contract forbids treating as proof
- why_this_survives_or_fails_RegDelta_evidence_rules: the standard
  solves *how to name and structure* legal content once authored;
  RegDelta solves *what may be claimed* about captured official
  bytes. Complementary layers: AKN can inform identity modeling
  without ever entering the evidence path

## 11. CORE-GAP supplement (2026-09-19 recon)

Renumbering machinery surfaced (akn-core v1.0 docs): `<textualMod
type="renumbering">` is a first-class mod type; `<previous href>`
carries the old→new element edge inside modifications; `<mappings>`
(`<mapping original="wId" current="eId" start end>`) is a temporal
wId↔eId ledger for frequently renumbered documents; `wId` = "the
identifier the structure used to have in the original version … only
needed when a renumbering occurred", anchored to a designated Master
Expression. Anonymous-node rule (NC §5.4.3): unnumbered elements get
an implicit *positional* eId counter — a minted address, not a
declared identity. All of it is producer-asserted metadata; nothing
binds a `<mapping>` to source-span evidence. Verdict unchanged:
PATTERN — the typed-mod + previous-edge + mapping-ledger design is
the richest standard-level redesignation model; its epistemics
(producer assertion, not evidence) are the gap RegDelta fills.
