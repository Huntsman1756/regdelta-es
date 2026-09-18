# CORE-GAP — WS-A terminal evidence: redesignation continuity

**Terminal: `PROVEN`** — pending publication commit.

Structural redesignations (`pasa a ser/denominarse`) are now explicit,
evidence-backed `old_locator -> new_locator` continuity edges in a new
`subject_redesignations` table, emitted only when the clause provably
declares both endpoints and pairing is unambiguous. No ordinary relation
is emitted for a proven code redesignation; same-code relabels keep
their baseline relation; unprovable destinations are journaled
`REDESIGNATION_REFUSED` with baseline relations preserved.

## Mechanism (as implemented)

- `operations.redesignation_segments` — finds structural redesig verbs
  on quote-masked text; dest zone bounded by the next operative verb or
  `, y <designator>`; a designator gate separates `pasa a ser la norma
  10` (structural) from `pasa a ser aplicable a…` (non-structural).
- `operations.redesignation_pairs` — positional subject→destination
  pairing inside the current sentence; classifies per EXP-B1:
  `CODE_REDESIGNATION` | `RELABEL_SAME_CODE` | `UNPROVABLE`.
- `history._emit_redesignation_edges` — validates (self-edge,
  new-key collision, `destination_already_exists` FALSE_MERGE guard),
  inserts edges, migrates chain state in topological order (chain-end
  first), refuses cycles. Resolution `RESOLVED` iff old chain state
  was proven `PRESENT`, else `DECLARED`.
- Name-carried leaf kinds (profile facet `redesig_name_kinds`,
  BdE: `fichero`) locate mentions by normalised quoted-span equality —
  quote masking would erase their only occurrence.

## Replay evidence

### BdE dev (16 targets, `evaluate_g2`, run `core-gap-wsa2`)

```text
edges emitted      6 (all DECLARED)
refusals           2 (REDESIGNATION_REFUSED, destination_unprovable)
FALSE_*            all 0
diff vs baseline   IDENTICAL 5010 / EXPECTED_DELTA 50 / UNEXPECTED 0
determinism        wsa2 vs wsa3: 5018 IDENTICAL, 0 deltas;
                   byte-diffs confined to volatile run_id
```

Edges (all match adjudicated EXP-B1 `new_key` where predicted):

```text
BOE-A-2005-4749  fichero:Banco de España - Entidad Gestora del Mercado
                 de Deuda Pública Anotada
              -> fichero:Entidad Gestora del Mercado de Deuda Pública
                 Anotada                      (EXP-B1 ACTIONABLE)
BOE-A-2011-2378  fichero:Servicio de Reclamaciones
              -> fichero:Reclamaciones, quejas y consultas
                                             (EXP-B1 ACTIONABLE)
BOE-A-2013-7467  fichero:Registro de agentes de entidades de crédito
                 y de pago
              -> fichero:Registro de agentes de entidades de crédito,
                 de entidades de dinero electrónico y de entidades de
                 pago                             (EXP-B1 ACTIONABLE)
BOE-A-2012-9058  norma:10.apartado:2.letra:d -> ...letra:e  (chain)
BOE-A-2012-9058  norma:10.apartado:2.letra:e -> ...letra:f  (chain)
BOE-A-2017-14334 disp:adicional.única -> disp:adicional.primera
```

EXP-B1 cross-check: all 4 ACTIONABLE cases on replayed targets emit the
predicted edge; all `NOT_ACTIONABLE_O1_*` cases abstain (incl.
`estado:FI 16-1 -> FI 16-1.2` on BOE-A-2013-5720, O1=FOREIGN_TARGET).
The 4th ACTIONABLE case sits on BOE-A-2004-21845, outside the dev
manifest — not replayed, no claim.

Honest refusals (journaled, baseline relations stand):

```text
estado:FI 143 «Préstamos sobre bienes inmuebles…»  (no code in dest)
apartado:II.B.2  «Operaciones de refinanciación…»  (no code in dest)
```

Superseded relations (8): the 3 fichero MODIFYs, `letra:d/e` +
dest-side `letra:f` on 2012-9058, `única` + dest-side `primera` on
2017-14334 — all registered in `expected-deltas.json`.

### CNMV dev (4 targets, run `core-gap-wsa-016`)

```text
edges emitted      5 (all DECLARED)
refusals           1 (cross-level letra n) -> número 4, honest)
relations          IDENTICAL to adjudicated dev-run-014
anomaly ledgers    identical except +1 REDESIGNATION_REFUSED
```

```text
BOE-A-2008-20895 norma:30.apartado:{13,14,15,16} -> {10,11,12,13}
                 (bulk, in-order, chained 16->13 after 13->10)
BOE-A-2008-20895 norma:49.apartado:4 -> norma:49.apartado:5
BOE-A-2010-13162 node 151 'Se renumera la norma 11.ª…'
                 CANDIDATE_NOT_EMITTED (O1 FOREIGN_TARGET — honest)
```

Known profile limit (pre-existing, not introduced by WS-A): the
lettered grouping `apartado E)/C)` is not representable in CNMV
locators — `números 13 del apartado E)` composes to
`norma:30.apartado:13`, the same flat encoding baseline relations
already used (adjudicated R2). Recorded as input to WS-B.

## Coverage vs prereg cases

| case | status |
|---|---|
| A1 former FLDs (13162) | edges `apartado:4->5`; `letra:n->número` refused cross-level (F3 territory, honest) |
| A2 bulk renumber (20895) | 4 edges, ordered, chained |
| A3 norma 11.ª->10.ª (13162) | candidate, not emitted — O1 FOREIGN_TARGET (fail-closed) |
| A4 BdE redesignations | all ACTIONABLE emit; all non-actionable abstain |
| A5 chains | d->e->f on 2012-9058; 16->13/13->10 on 20895; topological migration |
| A6 ambiguity | cardinality mismatch -> all left subjects UNPROVABLE; cycle/self/collision refused |
| A7 renumber+retext | `con la siguiente redacción` dests unprovable -> refusal, not guessed |
| A8 projection | edge ledger `redesignations.jsonl` additive; no derivation touched |
| adversarial | `pasa a ser aplicable`, name-only «…», malformed/kindless, quoted colons, dotted values — covered in tests |

## Test evidence

```text
tests/coregap/test_ws_a_redesignation.py   13 passed
tests/g0d-g0f regression                  134 passed
full suite                                347 passed (identical count
                                          to adjudicated f8e3a08)
```

## Invariants

```text
FALSE_FACT                = 0
FALSE_BINDING             = 0
FALSE_LOCATOR_DECLARATION = 0
FALSE_CONTINUITY          = 0   (every edge endpoint provably declared;
                                 unprovable -> refusal, never guess)
holdout                   sealed; census/probe reference holdout paths
                          only to exclude them mechanically
```
