# Problem: stable node identity

## Problem statement

Assign a stable identity to a legal node (norma, apartado, anejo,
table row) that survives amendments across versions — ADD,
SUBSTITUTE, DELETE, renumbering, anejo↔norma moves — without
generating false continuities or false splits.

This is the *identity* half of the `BINDING_NOT_PROVABLE` debt:
knowing which node a binding refers to across time. It is distinct
from `representation-binding-evidence` (proving *which* captured
representation is the right one) — an identity scheme may help the
first without touching the second.

## RegDelta surface

- `locator_key` / `SubjectRef` (`src/regdelta/operations.py`)
- `representations` rows and `binding_proof` locator spans
- `chain_reconstruction` 3/45 in the G2.2 sealed run — chains break
  where node identity cannot be carried across amendments
- `modification_relation_id` today binds (modifier, subject, locator,
  before, after) — node identity across time is implicit, not first-class

## Candidates

- `projects/words-to-data.md` — USLM-based stable identifiers
- `projects/legaldocml-akn.md` — AKN `eId` / FRBR URIs / ELI
- `projects/leos.md` — AKN4EU identity in production versioning
- `projects/akn-pt.md` — national profile applying eId/ELI/FRBR

## Open question

Which identity scheme survives amendment types RegDelta already
handles (explicit root transition, anejo vs norma ownership,
hierarchical apartado, qualified locators) without inventing identity
the source never declared?

## Verdict

PENDING — filled when all candidate fichas are evaluated.
