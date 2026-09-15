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

PENDING — filled when all candidate fichas are evaluated.
