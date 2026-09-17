# legalize-pipeline (legalize-dev)

## 1. Source freeze

- repo: legalize-dev/legalize-pipeline —
  https://github.com/legalize-dev/legalize-pipeline
- commit inspected: `5596f1d4f6c8` (main HEAD, review 2026-09-19;
  fast-moving repo)
- license: MIT

## 2. Problem fit

- `problems/hierarchical-diff.md` — primary (only ES-locator prior
  art found)
- `problems/amendment-actions.md` — secondary

Components:

- `transformer/anchor.py` — `Anchor` dataclass: BOE locator hints,
  struct tokens art/apartado/letra/disp/anexo/**norma**, ordinal
  words, compound splits ("articulo 96.2" → articulo 96 + apartado 2).
- `fetcher/es/amendments.py` — walks BOE `analisis/referencias`
  (official structured relations, controlled verbs), extract quoted
  blocks, multi-patch resolution via **greedy Jaccard matcher**.
- `llm/` — Groq dispatcher + `StructuredEdit` for hard cases.

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | PARTIAL (re-downloads BOE XML; no span ledger) |
| exact structural span | PARTIAL (anchor hints, not spans) |
| deterministic | NO (Jaccard fuzzy matching + LLM stage) |
| ambiguity unresolved | PARTIAL (confidence labels) |
| fail closed | PARTIAL (unrecognized verbs skipped-with-log — real
  fail-closed instinct — but fuzzy matching guesses) |
| synthetic consolidation | YES (consolidated corpus is the product) |
| normalized content | YES (Markdown) |
| temporal provenance | YES (commits dated by publication) |

## 4. Verdict

**PATTERN** — transferable: (a) skip-and-log verb filter = fail-closed
done right; (b) ES struct-token vocabulary incl. "norma" as a level
name; (c) negative quantification — their ~34–44% fuzzy-anchoring
fidelity on live BOE corpora prices exactly what non-proven matching
costs. Anchor = *matching target* vs RegDelta locator = *declared
path*: different epistemics, no code to port.

Falsification idea: run their token vocabulary over frozen DEV
locator spellings; expected FAIL on ordinal-name levels ("sección
quinta") and inside-out `de`-chains — a cheap coverage-gap measure.
