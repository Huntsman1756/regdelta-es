# legislation-gov-uk (URI scheme + CLML + TOES)

## 1. Source freeze

- sources: legislation.gov.uk/developer/uris (URI scheme docs);
  legislation.github.io/clml-schema + data-documentation repos;
  community.legislation.gov.uk editorial wiki (TOES)
- java lib: digitalheir/java-legislation-gov-uk-library @
  `9cb3eaad6a38` (v1.5.0, MIT, stale 2016)
- review date: 2026-09-19
- license: OGL-3.0 (data/docs); MIT (java lib)

## 2. Problem fit

- `problems/hierarchical-diff.md` — primary (URI composition)
- `problems/stable-node-identity.md` — secondary
- `problems/representation-binding-evidence.md` — secondary

Components:

- Compositional identifier grammar `/id/{type}/{year}/{number}
  [/{divisionName}/{number}]*` — ordered (kind, number) pairs;
  controlled division keywords; **numbers not normalized** ("Part II"
  ≠ "Part 2", source spelling preserved). Identifier/document/
  representation URI triple ≈ W/E/M.
- CLML `<Image>` → `<Resource>` indirection (ResourceRef: external
  file or inline data) — separates structural reference from byte
  payload; prior art for `artifact_locator` design.
- CLML user guide: "the website does not support navigating to
  provisions within attachments, and so the descendant elements of an
  attachment should not have structural IDs or URIs" — production
  precedent for **deliberate non-identification** (fail-closed).
- TOES "Changes to legislation": ~20-field structured effect records
  (affected/affecting provision, effect type incl. renumbering,
  in-force dates, applied flag); NLP-preidentified + human-verified —
  edges are trusted, not proven.

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | PARTIAL (URIs dereference to versions) |
| exact structural span | PARTIAL (division granularity) |
| deterministic | YES (scheme) / PARTIAL (TOES human-curated) |
| ambiguity unresolved | NO (resolution service, not abstention) |
| fail closed | PARTIAL |
| synthetic consolidation | YES (revised versions are the product) |
| original preserved | YES (versioned docs) |
| temporal provenance | YES |

## 4. Verdict

**PATTERN** — cleanest ordered (kind,number) locator grammar with
source-faithful spelling; Image→Resource indirection; and the
deliberate non-identification precedent for attachment internals.
legislate.js: no public repo found (likely internal to
website-frontend); the documented URI scheme is the artifact.
