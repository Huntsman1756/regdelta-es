# G1 protocol — structural binding integrity

Companion to `PREREG.md`. Defines operational rules for G1.x; the
preregistration defines what is being tested.

## Evidence handling

- All evaluation bytes arrive via `EVIDENCE_IMPORT` from a manifest
  selected by CLI argument. Zero network at evaluation time.
- Capture (`scripts/g1/capture_g1.py`, when run) is content-agnostic:
  what is fetched is decided by mechanical markup enumeration of
  official documents, never by the RegDelta pipeline. Same artifact set
  as G0-G.0: target diario XML, declared modifier XMLs, doc/txt/PDF
  officials, enumerable images, consolidada probes.
- The G1 sealed tree (created only if selection succeeds) is verified
  by `tests/g1/test_holdout_sealed.py`: SEAL sha256 over manifest +
  aggregate raw bytes + per-entry sha256.
- `evidence/g0g/g0g2/**` is immutable. G1 references its failure IDs
  without rewriting them.

## Splits

- `GENERALIZATION_DEV` (G1) = the 12 G0-G targets. Development and
  iteration happen only here.
- `SEALED_HOLDOUT` (G1) = 4 fresh targets per PREREG §6 — currently
  `STOP` (VISUAL pool underpopulated; see selection.json).

## Semantic opening

`HOLDOUT_OPENED` occurs when the G1 evaluator first loads the sealed
manifest for evaluation, parses a sealed artifact, or queries sealed
gold. Byte-level hash verification by the seal test is not opening.
After opening: runtime, evaluator, tests, metrics, selection, gold and
evidence are immutable; only results/audit/report artifacts may be
added.

## Evaluation semantics

The G1 evaluator reuses the frozen G0-G.1 audit semantics with the G1
additions: truth_verdict/root_cause_class separation (PREREG §7),
binding invariants B1–B6 (§8), binding_proof fields (§9), and the
explicit binding outcomes of §13. 100% of emitted relations are
audited. A doubtful claim is FALSE_FACT; a doubtful binding is
BINDING_FALSE.

## Metrics (reported, no post-hoc thresholds)

declared_modifier_recall, operation_parsing_rate,
subject_locator_resolution, representation_binding,
chain_reconstruction, applicability_extraction, query_execution,
false_positive_facts, false_binding_count, source_limitations,
old_false_fact_reproduction_count (DEV regression corpus),
ambiguous_binding_abstention count. Per target, per group, aggregate.

## Attempts

Every invocation of the official runner is appended to
`evidence/g1/g1x/attempts.jsonl` (timestamp, HEAD, runner/evaluator/
selection/manifest/gold hashes, split, targets, output, official flag,
status). One-shot rule identical to G0-G.2: environmental retries only,
identical inputs; a deterministic evaluator bug is recorded, not fixed.

## Hard gates

Per holdout target: FALSE_FACT_COUNT = 0 and FALSE_BINDING_COUNT = 0.
Gate result: PROTOCOL_INTEGRITY and FALSE_FACT_GATE as in G0-G.2, plus
FALSE_BINDING_GATE; G1.2 = PASS iff all PASS.

## Immutability during G1.0

No `src/regdelta/` change. The only permitted writes are
`evidence/g1/**`, `scripts/g1/**`, `tests/g1/**` and the G1 baseline.
