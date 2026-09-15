# Problem: version chains

## Problem statement

Reconstruct the ordered sequence of effective versions of an
instrument across amendments, including same-date ordering,
corrigenda, and gaps — so point-in-time state is provable.

## RegDelta surface

- `chain_reconstruction` 3/45 (6.7%) on the G2.2 sealed run; 11/63
  on DEV — the lowest coverage surface
- `CHAIN_DISCONTINUITY` journal entries (×34 sealed)
- Same-date hop ordering fixes applied in `evaluate_g2.py` during
  G2.1 — the evaluator and runtime both carry ordering logic worth
  comparing against upstream practice

## Candidates

- `projects/indigo.md` — point-in-time consolidation, expression
  versioning (declared production/stable)
- `projects/leos.md` — versioning and comparison at EU scale
- `projects/legaldocml-akn.md` — FRBR work/expression/manifestation
  temporal model

## Open question

How do production consolidation engines order same-date events and
treat corrigendum/correction events — and does their model admit
RegDelta's "no synthetic consolidation" constraint?

## Verdict

PENDING — filled when all candidate fichas are evaluated.
