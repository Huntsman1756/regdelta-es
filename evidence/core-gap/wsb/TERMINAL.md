# CORE-GAP — WS-B terminal evidence: hierarchical locator composition

**Terminal: `PROVEN`** — published as `d0919fa`.

Generic profile-declared hierarchy (`LocatorGrammar.child_parents`)
replaces the flat-cascade collision of CNMV `número`/`apartado`. Inside-out
`X de Y` chains compose multi-component locators only when every link is
an admissible declared parent and every component is proven. Ungoverned
`Sección X`/`Capítulo Y` materialize as subjects; governed `de la
sección` qualifiers emit nothing. BdE declares no `child_parents` — the
machinery is inert there and its output is byte-identical.

## Mechanism (as implemented)

- `LocatorGrammar.child_parents` — declared (child -> admissible parents)
  map; empty means the profile is flat-only (BdE).
- `operations._mention_spans` — position-carrying mention extraction on
  the quote-masked clause; enum groups stay grouped so `números 10, 11
  y 12 del apartado D)` binds all three to D.
- `operations._de_bound_paths` — builds inside-out chains over
  de-connectors only (`_DE_LINK` admits connectors + reference
  adjectives, nothing else). A link fails closed when the parent kind is
  inadmissible or the parent mention is multi-valued. Inner members of a
  longer chain cannot head suffix sub-chains — only the full path emits.
  Root-family mentions are never children: `normas 43 a 48 de la
  sección 7` keeps the normas flat; the sección is qualifier context.
- `operations._GOVERNED`/`_STANDALONE_KINDS` — `de/a/por/según…`
  governed mentions never become subjects; ungoverned `capitulo`/
  `seccion` mentions compose standalone subjects.
- `_compose_keys` — paths compose before the flat cascade; consumed
  components are subtracted so nothing double-emits. Every component
  carries `proof_components` (`EXPLICIT_CLAUSE|INHERITED`, node_index,
  scope) exactly like the flat cascade. Numbered units under an
  anejo/anexo normalize to `punto:N` — the same rule the flat cascade
  applies — so chained and flat references share one identity.
- `ownership.prove_locator` — ordinal/roman `capitulo`/`seccion` heads,
  `numero` structural component, and fail-closed uniqueness for bare
  `seccion:N` when the same head repeats under chapters.
- `binding._level_boundary` value-aware: lettered levels (`apartado A`)
  accept numeric children (`número 3`) instead of terminating.
- `db._ensure_subject_kinds` — rebuild migration preserving rows; new
  kinds NUMERO/LETRA/NUMERAL/SECCION/CAPITULO instead of degrading to
  APARTADO.
- CNMV grammar: `número` is its own level (no longer aliased to
  `apartado`); `apartado` accepts letters (`apartado A)`); `capitulo`
  declared; `nota` requires a word boundary (`Notas aclaratorias` no
  longer captures a phantom `nota:a`).

## Replay evidence

### BdE dev (16 targets, `evaluate_g2`, run `core-gap-wsb3`)

```text
diff vs wsa2 (post-WS-A): 5018 IDENTICAL / 0 deltas of any class
                          — WS-B is byte-identical inert for BdE
FALSE_*                   all 0 (audit_rows 512, same as wsa2)
```

### CNMV dev (4 targets, run `wsb2`, baseline `dev-run-016` post-WS-A)

```text
relations      18/63/30/2 -> 18/63/30/2 (+1 new resolved sub-op)
subjects       63->69 on 20895; kinds APARTADO 42->5, +NUMERO 30,
               +LETRA 12, +NUMERAL 1; +SECCION 1 on 28725
FALSE_*        all 0
determinism    wsb2 vs wsb4: envelope + all DB tables byte-identical
```

Semantic deltas (all registered in `expected-deltas.json#cnmv_deltas`):

```text
28725  +seccion:5 MODIFY UNRESOLVED  — 'La Sección Quinta … queda
       redactada' materializes; binding honestly NOT_FOUND/NOT_PROVABLE
       (WS-B:seccion-materialization)
20895  'apartado 8 de la Norma 29' RESOLVED->PARTIAL(before:NOT_FOUND)
       — flat apartado:8 was a key collision; the real entity is
       norma:29.apartado:B.numero:8 (WS-B:collision-chain-break)
20895  'norma 30 queda modificada' RESOLVED->PARTIAL(after:NOT_PROVABLE)
       + new 'apartado A' sub-op RESOLVED owning span (448,452)
       (WS-B:subop-content-ownership)
20895  clause 18 'número 2 del apartado C)' UNRESOLVED(before:AMBIGUOUS)
       ->PARTIAL: numero-level removes the apartado:2 collision; the
       AMBIGUOUS_BINDING anomaly disappears (WS-B:numero-level)
16091  anejo:*.apartado:9.letra:* -> anejo:*.punto:9.letra:* (identity
       preserved); 'Notas aclaratorias' phantom .nota:a dropped
       (WS-B:anejo-punto-normalization + WS-B:nota-miscapture)
13162  norma:4.apartado:2 -> norma:4.numero:2 — Norma 4 numbers items
       directly; PARTIAL unchanged (WS-B:numero-level)
```

Ground-truth spot checks (dev targets, same bytes the pipeline saw):

- Norma 29 has lettered apartados only; its `8.` lives under `B)` —
  baseline `apartado:8` was a false collision, now honestly NOT_FOUND.
- Norma 49 `C) Patrimonio neto.` restarts numbering — `letra n) del
  número 3 del apartado C)` -> `norma:49.apartado:C.numero:3.letra:n`,
  every component `EXPLICIT_CLAUSE` at the clause's node.
- Circular 4/1994 (28725) has globally ordered secciones (no chapters)
  — `Sección Quinta` -> `seccion:5` is provable; Circular 7/2008
  restarts secciones per capítulo, so a bare `seccion:N` there is
  refused as ambiguous (uniqueness check, fail-closed).

## Coverage vs prereg cases

| case | status |
|---|---|
| numero distinct level | `número N de la norma M` -> `norma:M.numero:N`; `del apartado X)` -> `apartado:X.numero:N` |
| deep inside-out chains | `norma:29.apartado:A.numero:1.letra:a.numeral:i` — all components EXPLICIT_CLAUSE |
| seccion materialization | `seccion:5`, `capitulo:1.seccion:2`; governed `de la sección 7` emits nothing |
| ambiguity fail-closed | bare `seccion:N` with repeated heads refused; multi-value parent mentions break chains |
| BdE byte-identical | 5018 IDENTICAL vs wsa2, zero deltas — no registered repair needed |
| component provenance | every path element in `proof_components` with node_index + scope |
| content ownership | sub-op owns (448,452); container stops over-claiming |
| collision honest abstain | `norma:29.apartado:8` before:NOT_FOUND instead of false continuity |

## Test evidence

```text
tests/coregap/test_ws_b_hierarchy.py   14 passed
full suite                             374 passed
```

## Invariants

```text
FALSE_FACT                = 0
FALSE_BINDING             = 0
FALSE_LOCATOR_DECLARATION = 0  (seccion:5 binds honestly unproven;
                                 mis-declared apartado:8 abstains)
FALSE_CONTINUITY          = 0
unexpected deltas         = 0  (BdE: byte-identical; CNMV: every delta
                                 registered under a WS-B case)
holdout                   sealed
```
