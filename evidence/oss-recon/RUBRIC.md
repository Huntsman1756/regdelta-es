# OSS reconnaissance rubric — frozen

## Anti-goal

> OSS reconnaissance is not a search for something to adopt.
> `DISCARD` is a successful result when external prior art conflicts
> with RegDelta's evidence contract.

The reconnaissance exists to prevent rebuilding solved problems and to
prevent adopting incompatible ones — not to find dependencies.

## Verdicts — exactly one primary verdict per project per problem

| verdict | meaning |
|---|---|
| `ADOPT` | code/dependency usable essentially as-is; compatible with provenance, determinism and fail-closed operation |
| `PORT` | a concrete algorithm or data structure is valuable, but the upstream format/runtime/model must not enter the core |
| `PATTERN` | architecture or conceptual model is useful; zero dependency |
| `TEST-CORPUS` | primary value is fixtures/regression cases |
| `DISCARD` | cost, license, document assumptions or evidence model incompatible |

Combined verdicts (e.g. `ADOPT/PATTERN`) are not permitted — one
primary decision is required. An optional `secondary_value` note may
follow the verdict, but the verdict itself is unequivocal.

## Evidence-rule compatibility — section 4 of every ficha

| question | answer |
|---|---|
| Can output trace to official source bytes? | YES / NO / PARTIAL |
| Can claim trace to exact structural span? | YES / NO / PARTIAL |
| Deterministic? | YES / NO |
| Can ambiguity remain unresolved? | YES / NO |
| Can it fail closed rather than guess? | YES / NO |
| Requires synthetic consolidation? | YES / NO |
| Requires normalized/re-written legal content? | YES / NO |
| Preserves original representation separately? | YES / NO |
| Supports temporal provenance? | YES / NO / PARTIAL |

An excellent project that fails here may still be `PATTERN` — it
cannot be `ADOPT`.

## Falsification experiments

Section 8 of every ficha defines a minimal, cheap experiment with its
`PASS`/`FAIL` criterion fixed **before** execution. A `PORT` or `ADOPT`
verdict without a pre-registered experiment is invalid.

## Decision rules

1. Source freeze is mandatory: exact commit/tag + review date + license
   hash. Verdicts apply to that revision only.
2. `ADOPT`/`PORT` verdicts enter only through the preregistration of
   the next gate — never mid-gate.
3. `DISCARD` requires no remedy: recording the incompatibility is the
   deliverable.
4. The delta table (section 7) protects what RegDelta already does
   better; an upstream capability does not displace a working
   RegDelta mechanism without a falsification experiment showing the
   gap.
5. License compatibility is evaluated per use (dependency vs.
   vendoring vs. pattern study); strong copyleft (e.g. EUPL) defaults
   to `PATTERN` unless the adoption case is exceptional.
