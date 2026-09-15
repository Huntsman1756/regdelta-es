# EXP-L1 — same-date lifecycle ordering

Prereg: `evidence/cov/PREREG.md` §8. Verdict space:
`PATTERN_CONFIRMED | REJECT`. Candidate rule (indigo
`Amendment.order_further`, algorithm only): order same-date hops by
`(event date, amending work date, subtype, natural-sorted number)`,
document order inside one amending work.

**Verdict: `PATTERN_CONFIRMED`**

## Method

Script: `scripts/cov/exp_l1.py` (deterministic; two runs byte-equal).
Frozen inputs: both ledgers (`dev-equivalence`, `g2.2/run`),
`subject-outcomes.jsonl` for clause node positions, captured diario
XML for `fecha_disposicion` / `rango` / `numero_oficial`.

Every `(target, locator_key)` with ≥2 same-date hops is an
order-sensitive group. The frozen ledger orders them by
`relation_id` hash (`evaluate_g2.py` sorts hops by
`(publication_date, relation_id)`) — deterministic but with no
official basis. The candidate order uses only official metadata +
document position. Each group is replayed under both orders with G1
§28 transitions, seeded by the pre-date same-scope chain state, and
each simulated before-state is compared to the adjudicated
`expected_existence_before`.

Before replaying, groups are de-conflated by subject scope: a bare
`apartado:6` or `estado:FI 136` key can name several real subjects
(norma scope, `módulo`/`cuadro`/`índice`/`encabezamiento` sub-element
context, anejo context). Hops with different scope signatures, or an
unrecoverable scope, are not the same subject — recorded as
`order_testable: false`, never silently ordered.

## Results (`same-date-groups.json`)

```text
inter-modifier clusters   1 (deterministic tuple, official metadata)
order-sensitive groups   76
  order_testable         45 groups / 124 hops
  scope collisions       31 groups untestable
frozen classes  REPRODUCED 26 | FLOOR_CHANGED 64 |
                UNPROVEN_UNDER_ORDER 3 | NOT_APPLICABLE 31
indigo classes  REPRODUCED 21 | FLOOR_CHANGED 66 |
                UNPROVEN_UNDER_ORDER 6 | HARD_CONTRADICTION 0
```

## Findings

1. **Determinism holds.** The single inter-modifier cluster
   (`BOE-A-2020-6186` + `BOE-A-2020-6187` on `BOE-A-2017-14334`,
   2020-06-16) resolves fully on official metadata: same
   `fecha_disposicion` (2020-06-11), same `rango` (Circular),
   `numero_oficial` 2/2020 < 3/2020 → 6186 first — which is also the
   posterior-act ordering.
2. **No source-undeclared order is ever imposed.** Intra-modifier
   ties resolve to document order — the document's own clause
   sequence, which the source declares.
3. **Zero hard contradictions.** No adjudicated `CHAIN_PREDECESSOR`
   expectation is provably falsified under the candidate order.
4. **The shared-locator case is real and the candidate order is
   better grounded.** `anejo:9.punto:99` was deleted by
   `BOE-A-2018-17880` (2018-12-28). The hash order put 6187 first,
   giving its MODIFY a `DELETED` chain proof and leaving 6186's MODIFY
   on an `ORIGINAL` floor. The candidate order (2/2020 first) gives
   the *earlier* instrument the `DELETED` before-state — the state the
   chain actually supports — and the later instrument an honest
   `UNKNOWN`. Same adjudication data, source-grounded order.
5. **Ledger finding (not a rule failure):** 6 adjudicated
   `CHAIN_PREDECESSOR` expectations exist only under the hash
   tiebreak (`UNPROVEN_UNDER_ORDER` under the candidate order), and
   31 groups are scope-collision artifacts — the frozen ledger chained
   `apartado:N`/`estado:*`/`anejo:N` keys across distinct normas,
   módulos, cuadros and índices. Those chains are key-collision
   artifacts, not lifecycle facts. Locator qualification is real
   debt for COV-2.

## Criterion check

`REJECT` requires a contradiction of an adjudicated case or an
imposed order the source never declared. Neither occurs: every
divergence from the frozen ledger traces to the hash tiebreak having
no official standing, or to same-key collisions that are not
same-subject sequences. `PATTERN_CONFIRMED` licenses the ordering
rule as a deterministic prior to be re-proven per case in a COV-2
preregistration — it is not adoption of indigo (no code, no AKN
storage, no editorial evidence model).
