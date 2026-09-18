# Problem: amendment action extraction

## Problem statement

Extract operative amendment actions (add, delete, substitute,
redesignate, repeal, renumber) from dispositive clause text, with
their scope and target — the parsing layer upstream of O1
attribution.

## RegDelta surface

- `operations.parse_all_operations` (`src/regdelta/operations.py`,
  v4) — `operation_kind`, scoped clause context, enumeration and
  hierarchical mention extraction
- `operation parsing` denominator is being renamed (G2.2 follow-up):
  leaf op accounting is now ledger-backed
- The `0 clauses parsed` journal entry and the `BOE-A-2004-21845`
  O1-NOT_PROVABLE concentration (85/438 leaf ops) suggest uncovered
  dispositive clause forms, especially in older circulars

## Candidates

- `projects/words-to-data.md` — amendment action taxonomy
  (`Add`, `Delete`, `Redesignate`, `Repeal`, `StrikeAndInsert`, ...)
  extracted from USLM-style clause text
- `projects/law-factory-parser.md` — dispositive parsing with an
  external regression corpus

## Open question

Does any upstream action grammar cover Spanish dispositive forms
("queda redactada", "se añade", "se suprime", corrigendum "debe
decir") — or are upstream taxonomies useful only as a classification
target for our own parsed kinds?

## Verdict

Evaluated (CORE-GAP recon 2026-09-19):
- `projects/uslm.md` — PATTERN; `redesignate` action + `renumbered`/`transferred` tombstone status
