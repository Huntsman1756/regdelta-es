# xmldiff (Shoobx)

## 1. Source freeze

- repo: Shoobx/xmldiff — https://github.com/Shoobx/xmldiff
- commit inspected: `0b16e5e52fcf` (master HEAD, review 2026-09-19)
- license: MIT (rewrite; heritage Logilab fmes.py was GPL-2 —
  verify file-level if ever vendored)
- algorithm: Chawathe et al. FMES "Change Detection in Hierarchically
  Structured Information"

## 2. Problem fit

- `problems/hierarchical-diff.md` — evaluated
- `problems/stable-node-identity.md` — evaluated

Component: `align_children` → `MoveNode(from_xpath, to_xpath)` —
genuine move detection in the edit script. `uniqueattrs` (default
`xml:id`) matched *first*, remaining nodes paired by LCS + similarity
thresholds (F≈0.6, T≈0.5).

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | NO (operates on XML trees) |
| exact structural span | PARTIAL (XPath, not source spans) |
| deterministic | YES given params |
| ambiguity unresolved | NO — threshold pairing always resolves |
| fail closed | NO — guesses pairing; silent false merge risk |
| normalized content | YES |
| temporal provenance | NO |

## 4. Verdict

**DISCARD** (for redesignation continuity / hierarchical diff
pairing). Similarity-threshold pairing is architecturally opposite to
source-declared edges: it *guesses* node identity and can silently
produce false continuities or false delete+add splits — incompatible
with RegDelta's proof-or-abstain contract. Recorded so the question
does not recur.

Useful negative confirmation: an upstream diff can never *falsify* a
declared move because its pairings are heuristic, not proven. The
`uniqueattrs`-first matching order (declared ids beat computed
similarity) is the one idea worth remembering conceptually.
