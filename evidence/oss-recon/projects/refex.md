# legal-reference-extraction (openlegaldata "refex")

## 1. Source freeze

- repo: openlegaldata/legal-reference-extraction —
  https://github.com/openlegaldata/legal-reference-extraction
- commit inspected: `a74242a5b55a` (review 2026-09-19)
- license: MIT — Python ≥3.11, active

## 2. Problem fit

- `problems/hierarchical-diff.md` — primary

Component: `CitationExtractor().extract("§§ 1, 2 Abs. 2, 3, 10 Abs. 1
Nr. 1 BGB")` — expands enumerations into per-section citations with
ordered component fields; `cit.span` plain-text spans;
`map_span_to_raw` maps spans back to raw offsets; law-book context for
bare `§` refs.

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | YES (spans into caller text, raw mapping) |
| exact structural span | YES per citation (not per level) |
| deterministic | YES |
| ambiguity unresolved | PARTIAL |
| fail closed | PARTIAL (no-match, no journal) |
| normalized content | NO |
| temporal provenance | NO |

## 4. Verdict

**PATTERN** — enumeration expansion ("§§ 1, 2 Abs. 2" → multiple
component paths sharing suffix context) is the closest analog to
Spanish enumeration/qualifier forms ("apartados 1 y 2", "letras a) y
c)"). Span-carrying citation objects are the right evidence shape.
TEST-CORPUS secondary: its benchmark shows failure-class organization.
