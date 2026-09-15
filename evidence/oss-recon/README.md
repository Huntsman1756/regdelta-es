# OSS reconnaissance — prior art before new subsystems

RegDelta constraint: **OSS-first, custom-second**. Before implementing a
new structural parsing, legal-identity, amendment, versioning,
consolidation, diff, or jurisdiction-profile subsystem, the problem must
have a reviewed prior-art entry here.

## Organization — two levels, problem-driven

- `problems/` — one file per concrete RegDelta debt. This is the index:
  reconnaissance is organized around what we need to solve, never
  around "interesting repos".
- `projects/` — one ficha per evaluated upstream project, using the
  frozen 10-section structure in `RUBRIC.md`.

A problem file lists its candidate projects; a project ficha names the
problem(s) it was evaluated against. A project may appear under several
problems; every project verdict is evaluated per problem context.

## Status

Batch 1 (2026-09-15): `words-to-data` = PATTERN (PORT candidate for
the redesignation-pairing algorithm, gated on its §8 experiment);
`indigo` = PATTERN. All other verdicts PENDING. A verdict is recorded
only after the ficha is complete, including a pre-registered
falsification experiment where required.

## Flow into gates

A verdict of `ADOPT` or `PORT` does not authorize incorporating the
work mid-gate. Adoption decisions enter through the preregistration of
the next gate. `PATTERN`, `TEST-CORPUS` and `DISCARD` may inform design
immediately but must not silently expand a running gate's scope.

See `RUBRIC.md` for verdict definitions, the evidence-rule
compatibility table and the anti-goal.
