# citation (unitedstates)

## 1. Source freeze

- repo: unitedstates/citation —
  https://github.com/unitedstates/citation
- commit inspected: `953c03d32000` (master HEAD, last push
  2020-06-07, review 2026-09-19)
- license: CC0-1.0

## 2. Problem fit

- `problems/hierarchical-diff.md` — primary

Component: `Citation.find("5 U.S.C. 552(a)(1)(E)")` → ordered
component array `subsections:["a","1","E"]` + composed canonical id +
whole-match char span; `parents:true` emits cumulative-prefix parent
cites each with own match/index. Outside-in grammar (US only).

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | YES (match+index into caller text) |
| exact structural span | YES per citation; per-level only as
  overlapping prefixes |
| deterministic | YES |
| ambiguity unresolved | PARTIAL (silent no-match) |
| fail closed | PARTIAL (no abstention record) |
| normalized content | NO |
| temporal provenance | NO |

## 4. Verdict

**PATTERN** — best observed "parse nested citation → ordered
component path + composed key" shape. CC0 + tiny codebase. Not
PORTable as grammar (US-only, outside-in); the *shape* — ordered
component array with per-level evidence — is the reusable part.

Falsification experiment (WS-B): transcribe the ordered-array shape
onto ~20 adjudicated RegDelta locator spellings incl. inside-out
forms ("apartado C), número 3, de la norma 49"). PASS: ordered path
reconstructs every proven locator_key with declaration order recorded
separately. FAIL: any case where a flat array loses which
`de`-connector bound which level.
