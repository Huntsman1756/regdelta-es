# RegDelta — agent rules

## OSS prior-art constraint (permanent, OSS-first / custom-second)

Before implementing a new structural parsing, legal-identity,
amendment, versioning, consolidation, diff, or jurisdiction-profile
subsystem, check `evidence/oss-recon/`. If the problem has not been
reviewed, perform and record OSS prior-art reconnaissance first,
using `evidence/oss-recon/RUBRIC.md`. Any custom implementation must
state why existing OSS is not `ADOPT`/`PORT`-compatible with
RegDelta's provenance, determinism, and fail-closed evidence rules.

A verdict of `ADOPT` or `PORT` does not authorize incorporating the
work mid-gate: adoption decisions enter only through the
preregistration of the next gate.

## Evidence discipline

- Historical gate results are permanent: `G0-G.2 = FAIL`,
  `G1.2 = FAIL`, `G2.0 = STOP`, `G2.0b = PASS`, `G2.2 = PASS`.
  Never edit, reinterpret, or replace historical evidence.
- `evidence/g2/holdout/` content must not be read semantically by
  source, test, or evaluation code except through the sealed-runner
  protocol. Hash/integrity checks are not an opening.
- Fail-closed: abstain and journal rather than fabricate certainty.
