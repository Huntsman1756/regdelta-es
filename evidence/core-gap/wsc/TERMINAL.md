# CORE-GAP — WS-C terminal evidence: anonymous structural identity

**Terminal: `ANCHORED_SUBJECT_PROVEN` for positional leaves and
unnumbered disposition classes; `HONEST_ABSTENTION_IS_CORRECT` for
items the source leaves anonymous.**

Two new locator kinds — `parrafo`/`guion` — are declared **positional**
(`LocatorGrammar.positional_kinds`): they compose only inside a proven
parent path or a proven scope, they never head a standalone subject, and
they carry `proof_components` like any declared component. Unnumbered
`Norma/Disposición <tipo>` heads emit `disp:<tipo>` — a declared class
identity whose uniqueness is proven by head enumeration (fail-closed on
plurality). Items whose kind is named but whose identity cannot be keyed
journal `UNKEYED_ANONYMOUS_ITEM` instead of silently disappearing or
fabricating a subject.

## Mechanism (as implemented)

- `LocatorGrammar.positional_kinds` / `opaque_kinds` — a positional kind
  is a derived structural address (`parrafo:N` = Nth non-dash paragraph
  in the proven parent span; `guion:N` = Nth dash-prefixed item), never
  a source-declared identity. `opaque_kinds` names kinds the key model
  cannot capture (used only for journaling, never for emission).
- `operations._de_bound_paths` — extended with `_A_LINK`: positional
  children also bind through destination connectors (`párrafo tercero
  a la letra d)` -> `…letra:d.parrafo:3`), the reading `de`-links cannot
  express.
- `operations._unkeyed_kinds` + `Operation.unkeyed` — clause-level
  detection of kind-words that were mentioned but not captured
  (`los dos guiones`, `el anexo`, plural `estados` without codes);
  shared-spelling aliases (`anexo`/`anejo`, `disp`) are not flagged when
  the declared spelling was captured.
- `operations._suppress_anchor_subjects` — a captured positional mention
  that only anchors anonymous items is not emitted as a subject: the op
  carries `subjects=[]` plus the journal, not a false relation.
- `operations.split_sections` + `DocumentModel.block_head` /
  `context_head` — old-format CNMV documents carry operative structure
  in `centro_*` display classes: `centro_negrita` heads split sections
  (only when they name the target instrument), `centro_cursiva`/
  `centro_redonda`/`anexo` heads update scope context.
- `operations._disp_ord_alt` + `history/ownership/binding` — unnumbered
  `disposición/norma` heads supported by a negative-lookahead
  alternation that rejects ordinal tails; `disp:<tipo>` uniqueness is
  enumerated over target heads.
- `ownership` — positional `_sub_present` counts positional nodes inside
  the proven parent span; rootless positional keys refuse to resolve as
  heads.
- `binding` — `disp_spans` recognizes unnumbered heads; positional
  candidates resolve the Nth node of the positional class inside the
  parent's proven span.
- `annexmap.declared_anejos` — PREREG §5 debt closed: an `anejo:N`
  minted by the positional fill is a derived address, not a declared
  identity, and no longer feeds image binding (`subject_pages` returns
  None for non-declared numbers; the caller falls back to structural
  XML candidates or abstains).
- `history._scope_word_kind` — `sub_scope` surface words normalize
  accents/plurals and the anejo→punto alias, so a clause naming its own
  locator kinds no longer fails the scope proof.
- `history` — `UNKEYED_ANONYMOUS_ITEM` journal after the TARGET_PROVEN
  gate; `_upsert_subject` admits PARRAFO/GUION; `db` CHECK extended
  with rebuild migration.
- `bde.disposicion_head` — template reshaped so the `{ord}` segment
  carries its own whitespace; BdE emitted output unchanged (verified by
  replay).
- `diff_runs._match_expected` — fixed a catch-all: entries with only
  `match_key_prefix`/`match_contains` matched every row of their file
  because `all()` over an empty `match` predicate is vacuously true.
  The harness now classifies exactly.

## Replay evidence

### BdE dev (16 targets, `evaluate_g2`, run `core-gap-wsc2`)

```text
diff vs wsb3 (post-WS-B):   4982 IDENTICAL / 64 EXPECTED_DELTA /
                            0 UNEXPECTED_DELTA / 0 unmatched
diff vs frozen baseline:    4974 IDENTICAL / 114 EXPECTED_DELTA /
                            0 UNEXPECTED_DELTA / 0 unmatched
determinism                 wsc2 vs wsc3: all ledgers byte-identical
FALSE_*                     all 0 (audit_rows 512)
```

All WS-C deltas live on `BOE-A-2017-14334` and decompose into two
preregistered cases:

- `WS-C:declared-anejo-gate` — anejos 1/3/4/5/6 of Circular 2/2017 are
  positionally filled (declared heads: 2,7,7.x,8,8.x,9). Their
  before-side image bindings drop or fall back to structural XML
  candidates; `anejo:5.indice` DELETE abstains RESOLVED→UNRESOLVED with
  `BINDING_NOT_FOUND`+`UNBOUND_SUBJECT` journaled. Honest direction:
  a derived address no longer masquerades as declared identity.
- `WS-C:scope-word-normalization` — after-content bindings that were
  suppressed by the literal sub_scope match now bind where provable
  (`anejo:9.punto:151.nota:a` MODIFY UNRESOLVED→PARTIAL, evaluator
  `BINDING_CORRECT`), or re-journal the same abstention one gate later.

### CNMV dev (4 targets, run `wsc2`, baseline `wsb4` post-WS-B)

```text
16091  +disp:transitoria ADD RESOLVED (unnumbered disposition class)
20895  5 subjects recompose with proven .parrafo:N leaf; one improves
       UNRESOLVED->PARTIAL (after bound); RESOLVED preserved elsewhere
28725  old-format heads: +3 relations (anejo:I PARTIAL,
       anejo:1.apartado:C UNRESOLVED, norma:7.parrafo:1 PARTIAL);
       seccion:5 UNRESOLVED->PARTIAL (after binds inside the
       newly-recognized block-head span)
all    +UNKEYED_ANONYMOUS_ITEM rows (bare 'el anexo'/'estados',
       'los dos guiones', 'Anexos ter y quater') — journaled, never
       fabricated
determinism  wsc1 vs wsc2: envelope + all DB tables byte-identical
```

Smoke check on `BOE-A-1998-30048` (old-format modifier): 0 → 34
operations, including `@23 SUBSTITUTE subjects=[] unkeyed=('guion',)`
— the anonymous-item shape the workstream was built for.

## Coverage vs prereg terminals

| case | terminal |
|---|---|
| `parrafo`/`guion` leaf inside proven path (`tercer guión del número 4 del apartado 12 de la norma 30` -> `norma:30.apartado:12.numero:4.guion:3`) | ANCHORED_SUBJECT_PROVEN |
| destination link (`párrafo tercero a la letra d) del apartado 2 de la norma 5` -> `norma:5.apartado:2.letra:d.parrafo:3`) | ANCHORED_SUBJECT_PROVEN |
| unnumbered `disposición/norma <tipo>` (`disp:transitoria`) | ANCHORED_SUBJECT_PROVEN |
| `los dos guiones … del primer párrafo` (anonymous plural) | HONEST_ABSTENTION_IS_CORRECT — `subjects=[]`, `unkeyed=('guion',)` journaled |
| rootless positional mention | refused as head; journaled if anchored |
| ambiguous connector/parent cardinality | chain refused; flat fallback only where baseline-provable |
| old-format operative structure (`centro_*` heads) | recognized, honestly resolved or abstained |

`MODEL_EXTENSION_UNSAFE` was not reached: no case required minting
identity the source did not declare.

## Test evidence

```text
tests/coregap/test_ws_c_anonymous.py   28 passed
tests/coregap/ (ws_a + ws_b + ws_c)    55 passed
full suite                             374 passed
```

## Invariants

```text
FALSE_FACT                = 0
FALSE_BINDING             = 0
FALSE_LOCATOR_DECLARATION = 0  (positional keys are derived addresses
                                inside proven parents; unkeyed items
                                journal instead of keying)
FALSE_CONTINUITY          = 0
unexpected deltas         = 0  (BdE: every delta registered under a
                                WS-C case; CNMV: cnmv_deltas entries)
holdout                   sealed
```
