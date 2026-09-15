# EXP-B1 — redesignation-aware pairing

Prereg: `evidence/cov/PREREG.md` §8. Verdict space: `PORT | REJECT`.
Candidate mechanism: words-to-data `ccc44e0` — consult demonstrated
redesignation/continuity edges **before** positional pairing.
Algorithm only: no crate, no USLM assumptions, no LLM pipeline.

**Verdict: `PORT`**

## Method

Script: `scripts/cov/exp_b1.py` (deterministic; two runs byte-equal).
Frozen inputs: `evidence/g2/g2.2/dev-equivalence/` (DEV ledger),
`evidence/g2/g2.2/run/` (opened sealed ledger, supplementary),
captured `boe_diario_xml__*.xml` under `evidence/**/raw/`.

1. Enumerate `pasa a ser/denominarse` clauses in every modifier
   document that the frozen reconciliation attributes to a target,
   reusing evaluator-side clause enumeration (`_sections`,
   `_leaf_clauses`, `_eval_mentions`) — same contract as the audit.
2. Classify mechanically: `CODE_REDESIGNATION` (key-changing edge),
   `RELABEL_SAME_CODE`, `SUBFIELD_RENAME`, `NON_STRUCTURAL`,
   `UNPARSEABLE` (fail-closed — never guessed).
3. For each actionable edge (O1 `TARGET_PROVEN`, single ledger
   locator matching the old code): replay the target's frozen
   relation stream under G1 §28 transitions, migrate chain state
   `old_key -> new_key` at the event date, compare against every
   adjudicated `expected_existence_before` on same-date and
   post-event hops.

## Results (`cases.json`, `simulation.json`)

```text
cases=85   CODE_REDESIGNATION 15 | SUBFIELD_RENAME 39 |
           NON_STRUCTURAL 10 | RELABEL_SAME_CODE 5 | UNPARSEABLE 16

edges=15   NOT_ACTIONABLE 11 | CONFIRMED 3 | REPAIRED 1 |
           FALSE_MERGE_RISK 0 | CONTRADICTED 0 | LOST 0
```

- `REPAIRED`: `estado:FI 16-1 -> estado:FI 16-1.2` on
  `BOE-A-2004-21845` via `BOE-A-2016-11483` — the frozen ledger holds
  the rename as two dangling same-date `MODIFY`s with
  `UNKNOWN / NO_STRUCTURAL_PROOF` on both keys; the declared edge
  converts them into proven subject-continuity.
- `CONFIRMED`: three `fichero:` rubric renames where the old key was
  already proven `PRESENT / ORIGINAL_PUBLICATION_STRUCTURAL` — the
  edge agrees with the ledger.
- `NOT_ACTIONABLE`: correctly refused wherever O1 attribution was not
  `TARGET_PROVEN` (e.g. the same FI 16-1 clause under target
  `BOE-A-2013-5720` is `FOREIGN_TARGET` — it modifies 4/2004, not
  1/2013).

## Criterion check

`REJECT if any FALSE_MERGE / CONTRADICTED / LOST` → none observed on
either frozen ledger → `PORT`. Repair yield was reported, not
required.

## Limitations (recorded, not hidden)

- `locator_resolves` cannot see table content (estados/anejos live in
  XML tables), so original-existence detection under-approximates —
  `FALSE_MERGE_RISK` detection is weaker for table subjects. The edge
  population was small: 4 edges interacted with the ledger at all.
- A `PORT` verdict authorizes considering the mechanism in a COV-2
  preregistration — nothing more. The observed words-to-data pipeline
  (LLM amendment extraction, 899 vs 893 non-reproducible links) is not
  portable and is not implicated by this result.
- Any future port must keep the fail-closed guards the experiment
  applied: refuse when O1 is not proven, refuse when both keys have
  proven independent existence, journal ambiguity.
