# Problem: jurisdiction profiles

## Problem statement

Separate the RegDelta core (ownership → locator → lifecycle →
binding → proof) from source-specific grammars — the prerequisite
for the CNMV portability test and any future source family.

## RegDelta surface

Current BdE coupling points (predicted portability boundary):

- `history._CIRCULAR_RE` — target reference derived from BdE
  Circular numbering
- Locator grammar `norma:/anejo:/apartado:` and state-code families
  `FI|FC|PI|PC|PA|UEM|AVE` — BdE-specific
- Dispositive clause patterns tuned to Circular/BOE forms
- Predicted to port cleanly: ownership layer, locator proof,
  lifecycle, subject_proof/binding_proof, the evidence contract

## Candidates

- `projects/akn-pt.md` — national AKN profile (AKN + ELI + FRBR +
  Schematron): the reference shape for "common core + jurisdiction
  profile"
- `projects/indigo.md` — per-country doctype/language system
- `projects/leos.md` — AKN4EU as an institutional profile of AKN

## Open question

What is the minimal `CNMVProfile` surface — locator grammar, state
codes, dispositive grammar, target-ref derivation — and do upstream
profile mechanisms (Schematron validation, profile XML,
country-specific schemas) map onto RegDelta's fail-closed evidence
rules?

## Verdict

PATTERN — resolved 2026-09-16 (Batch 2). All candidates evaluated:

- `projects/akn-pt.md` = PATTERN — the reference artifact shape for
  a jurisdiction profile: spec + schema subset + phased Schematron
  + national identifier scheme + doctype mapping + verified real
  corpus + validator
- `projects/legaldocml-akn.md` = PATTERN — FRBR W/E/M layering and
  the wId/eId identity-vs-position split; profiles are
  *restrictions* of a superset, never extensions
- `projects/leos.md` = PATTERN — restrictive-profile doctrine and
  configuration-driven profile packaging (AKN4EU as institutional
  profile)
- `projects/indigo.md` = PATTERN (Batch 1) — per-country
  doctype/language system

Convergent answer to the open question: a `SourceProfile` is a
packaged restrictive overlay — locator grammar + vocabulary +
clause grammar + identifier scheme + verified fixture corpus +
profile validator — over an untouched core. No upstream component
survives RegDelta's evidence rules for ADOPT/PORT (all require
normalized/minted content rather than proven captured bytes).
