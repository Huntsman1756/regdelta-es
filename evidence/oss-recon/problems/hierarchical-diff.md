# Problem: hierarchical diff

## Problem statement

Compute provable differences between two versions of an instrument
at structural granularity — node added/deleted/substituted/moved —
rather than flat text diff.

## RegDelta surface

- `diff` query surface (one of the five frozen queries)
- `changes`/`affects` queries currently derive from persisted
  `modification_relations`, not from tree comparison — a structural
  diff engine could either complement or falsify that derivation
- Wrong-locator and root-transition classes (G2.2 §47) are exactly
  the events a hierarchical diff must represent correctly

## Candidates

- `projects/words-to-data.md` — version comparison over
  hierarchical trees (a core feature, Rust core + Python bindings)
- `projects/leos.md` — comparison of legislation in production
- `projects/indigo.md` — expression diffing for consolidation

## Open question

Do upstream diffs produce per-node provable change events (with
source-span evidence on both sides), or only a rendered comparison —
and can a diff ever *contradict* a declared operation's proven
emission in a way RegDelta can surface as a finding?

## Verdict

PENDING — filled when all candidate fichas are evaluated.
