# eli-subdivisions (EUR-Lex / OP)

## 1. Source freeze

- spec: "Specifications for the identification of subdivisions in EU
  legislation using ELI", v2 —
  eur-lex.europa.eu/content/eli-register/ELI-subdivisions-specifications-v2.pdf
- review date: 2026-09-19 (CORE-GAP recon)
- license: public EC specification

## 2. Problem fit

- `problems/stable-node-identity.md` — primary
- `problems/hierarchical-diff.md` — secondary

Components:

- Canonical subdivision IDs exist even for unnumbered subdivisions:
  `pbl_1` for preamble; **unnumbered paragraphs typed `unp`** (vs
  `par` numbered, `sub` subparagraph) — "present and identified as
  such in the canonical identifier".
- IDs are English-canonical across language variants
  (`art_1a` not `art_1bis`); per-language mapping tables normative.
- Subdivision path inserted *before* the version segment —
  `…/eli/dir/yyyy/nnnn/art_2/unp_3/oj` — locator is work-level stable.
- §13.1: subdivisions inside annexes are excluded from canonical IDs.

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | NO (identifier convention) |
| exact structural span | YES (within the doc) |
| deterministic | YES |
| ambiguity unresolved | PARTIAL |
| fail closed | YES (annex internals excluded outright) |
| normalized content | YES |
| original preserved | YES |
| temporal provenance | YES (version segment after locator) |

## 4. Verdict

**PATTERN** — the `unp` kind-token is the concrete encoding of
MetaLex's `positional` method: a positional identifier that cannot be
confused with a declared number because its type tag differs
(`unp:2` ≠ `par:2`). Also precedent that even a full institutional
system *abstains* on annex-internal canonical addressing.
