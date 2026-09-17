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

- `projects/words-to-data.md` — evaluated Batch 1: PATTERN;
  `Redesignations`/`TreeDiff` pairing is a PORT candidate gated on
  its falsification experiment
- `projects/leos.md` — comparison of legislation in production
- `projects/indigo.md` — evaluated Batch 1: PATTERN; uses patched
  `xmldiff` with attribute-ignore

## Open question

Do upstream diffs produce per-node provable change events (with
source-span evidence on both sides), or only a rendered comparison —
and can a diff ever *contradict* a declared operation's proven
emission in a way RegDelta can surface as a finding?

## Verdict

Evaluated (CORE-GAP recon 2026-09-19):
- `projects/citation.md` — PATTERN; ordered component array shape
- `projects/refex.md` — PATTERN; enumeration expansion + span-carrying cites
- `projects/legalize-pipeline.md` — PATTERN; ES struct-token vocabulary, fuzzy-anchoring negative result
- `projects/legislation-gov-uk.md` — PATTERN; (kind,number) URI grammar, source-faithful spelling
- `projects/xmldiff.md` — DISCARD; heuristic move detection
