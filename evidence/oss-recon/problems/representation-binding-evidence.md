# Problem: representation binding evidence

## Problem statement

Prove — from captured official evidence, not inferred structure —
*which* concrete representation (XML node, image, table span) a
declared subject locator binds to, at each point in the instrument's
history. The dominant G2.2 journal entry, `BINDING_NOT_PROVABLE`
(×321 on the sealed corpus), is this failure: the subject and locator
are proven, but no captured evidence suffices to prove the binding.

This is the *evidence* half of the binding debt. Do not conflate with
`stable-node-identity`: an upstream identity scheme can be excellent
and still contribute nothing here.

## RegDelta surface

- `binding_proof` on `modification_relations` and the B1–B6 audit
  (`scripts/g1/evaluate_g1.py`)
- `representation_binding` 24/286 (8.4%) on the G2.2 sealed run
- Journal classes: `BINDING_NOT_PROVABLE`, `BINDING_NOT_FOUND`,
  `AMBIGUOUS_BINDING`, `UNBOUND_SUBJECT`
- `ACQUISITION_FAILURE` — evidence capture gaps also cap binding

## Candidates

- `projects/indigo.md` — consolidation/expression model
- `projects/words-to-data.md` — node paths into diffable structures
- `projects/akn4olf.md` — provenance-first metadata normalization

## Open question

Do upstream engines bind extracted nodes to provable source spans, or
only to positions inside their own normalized model — and can any of
that be made evidence-traceable to BOE raw bytes?

## Verdict

Evaluated (CORE-GAP recon 2026-09-19):
- `projects/boe-image-channels.md` — PATTERN; verified official image channels + authenticity hierarchy
- `projects/eurlex-cellar-formex.md` — PATTERN; fmx4 zip ships images as first-class files
- `projects/legislation-gov-uk.md` — PATTERN; Image→Resource indirection, deliberate non-ID precedent
- `projects/pypdf.md` — PORT candidate gated on byte-equality falsification
