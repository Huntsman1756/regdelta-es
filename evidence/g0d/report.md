# G0-D — Applicability Discovery Report

**Target**: `BOE-A-2025-26847` — Circular 1/2025, de 19 de diciembre, del Banco de España
**Mode**: discovery only. No production model implemented. No `src/regdelta` changes.

## 0. Git state

```text
HEAD:        2af7ee6e0a091f1311532d89e52b644d4b0ee7a6
origin/main: 2af7ee6e0a091f1311532d89e52b644d4b0ee7a6
tree:        clean at probe start
```

## 1. Sources / raws used (byte-identical reuse, no new fetches)

| raw | path | SHA-256 |
|---|---|---|
| modifier diario XML | `evidence/g0c/raw/boe_diario_xml__BOE-A-2025-26847.xml` | `689fbe5e47569045d3bb…` |
| target diario XML | `evidence/g0c/raw/boe_diario_xml__BOE-A-2017-14334.xml` | `4f995cd7d647216658ec…` |

Frequency data comes from the target document itself: norma 67's structured
`table` node (53 rows: Estado / Denominación / Periodicidad / Plazo) —
DECLARED, not inferred. Norma 68 (FC states) carries frequency in prose
("trimestralmente") — usable but lower-grade; not needed for D1–D11.

Clause → relation binding replays `history.reconstruct` offline over the
existing manifests (EVIDENCE_IMPORT; no source_checks fabricated).

## 2. Applicability-clause inventory

26 clauses extracted (see `clauses.json`; every record carries
`node_span` + `char_span` into the source blob):

```text
disposición final única (dfu)
  base:s1   INSTRUMENT_EFFECTIVE_FROM 2025-12-30 (DERIVED: publication+1)
  a–d:s1    EXCEPTION → APPLY_FROM 2026-01-01
  e:s1      EXCEPTION → 3 × FIRST_REFERENCE_DATE (frequency-conditioned)
            └── :carveout  EXCEPTION → "sin perjuicio de … transitoria tercera"
  f:s1      EXCEPTION → FIRST_REFERENCE_DATE 2026-06-30 (riesgo-país)

disposición transitoria primera (dt1) — contratos electricidad
  1:s1      SCOPE_PERIOD (cuentas anuales ejercicio 2026)
  1:s2      RETROACTIVE_APPLICATION + introducers b),d) + exceptions 2–6
  1:s3      INITIAL_APPLICATION_DATE 2026-01-01
  2:s1      EXCEPTION — ABSENCE_OF_OBLIGATION (no reexpressar comparativos)
  2:s2      QUALIFIER — OBLIGATION conditioned on exercising the option
  3:s1      EXCEPTION — OPTION (designación irrevocable, condition)
  4:s1      EXCEPTION — PROSPECTIVE_APPLICATION (OBLIGATION)
  4:s2      ALTERNATIVE — OPTION (interrumpir cobertura)
  5:s1      QUALIFIER — NON_APPLICATION conditioned on option
  6:s1      EXCEPTION — ABSENCE_OF_OBLIGATION

disposición transitoria segunda (dt2) — carteras de activos financieros
  same pattern: scope, retroactive base, option, conditioned consequence,
  obligation (memoria), non-application, absence of obligation.
  Note: no explicit PROSPECTIVE_APPLICATION apartado (genuine difference);
  the initial application date is implied via "a 1 de enero de 2026"
  balance dates, not declared.

disposición transitoria tercera (dt3)
  único:s1  LAST_REFERENCE_DATE 2026-06-30, OBLIGATION, FI 131 + FI 141
```

## 3. Required temporal taxonomy (corpus-driven)

```text
INSTRUMENT_EFFECTIVE_FROM   instrument-level entry into force
APPLY_FROM                  specific modifications apply from a later date
FIRST_REFERENCE_DATE        first data reference date (may be conditioned)
LAST_REFERENCE_DATE         last data reference date
RETROACTIVE_APPLICATION     applies retroactively (framework rule)
INITIAL_APPLICATION_DATE    the anchor date retroactivity counts from
PROSPECTIVE_APPLICATION     applies only to new positions going forward
SCOPE_PERIOD                period scope ("cuentas anuales ejercicio 2026")
```

All eight are needed by this single instrument; none is reducible to another.
`INSTRUMENT_EFFECTIVE_FROM ≠ APPLY_FROM ≠ FIRST_REFERENCE_DATE` is the core
distinction: 2025-12-30 / 2026-01-01 / 2026-03-31 are three different dates
answering three different questions for the same modification.

## 4. Required modality taxonomy

```text
DECLARED_RULE           "se aplicarán", "entrará en vigor" (declarative)
OBLIGATION              "deberá", "deben reportar", "reconocerá"
OPTION                  "podrá optar", "podrá interrumpir"
ABSENCE_OF_OBLIGATION   "no estará obligada a"  ← real category; forcing it
                        into MAY would lose the legal meaning (it is a
                        relief, not a permission to act)
NON_APPLICATION         "no aplicará las modificaciones … para elaborar
                        la información comparativa" — a scoped exemption
```

`PROHIBITED` did not occur in this corpus — reserved, not used.

## 5. Parent/child model

Edges actually observed (all mechanically derivable from explicit text):

```text
BASE          top-level rule of a disposición
EXCEPTION     "con las excepciones establecidas en los apartados 2 a 6",
              "con las siguientes especificidades", "sin perjuicio de"
ALTERNATIVE   intra-item options ("podrá interrumpir…")
QUALIFIER     conditioned consequences ("Si optara…", "Cuando haya optado…")
PART_OF       structural decomposition of multi-sentence apartados
              (mechanical; no juridical semantics)
```

`sin perjuicio de` is an **EXCEPTION carve-out**, not a date-priority rule:
clause `dfu:e` carries a child record citing `dt3` for FI 131/FI 141. The
right answer is coexistence: the FI 131/141 relations sit inside `dfu:e`'s
scope (their delete ops are under letters j) and m)) **and** carry `dt3`'s
LAST_REFERENCE_DATE — both true simultaneously; `sin perjuicio` declares that
`dt3` is not displaced.

## 6. Clause → modification_relation binding

`target-matrix.json`: two deterministic channels —

1. **introducer-driven** ("introducidas por la letra b)… de la norma 1"):
   cited letter/numeral marker paths expand to the operations under them;
   their subjects' relations bind. `dfu:e` → letters j,k,m,n,o → 30 relations.
2. **subject-driven** ("los estados FI 131 y FI 141"): locator keys bind
   directly. `dt3` → 4 relations (2 ops × 2 estados).

```text
clauses with bindings: 16
DECLARED subject bindings: 57   relations bound: 49 / 65
CONTAINER_EXPANDED: norma:67/68, anejo:4/5/6/9, norma:31 (cited containers
                    whose member ops carry the relations)
```

The 16 unbound relations must not be silently assumed GENERAL_ONLY.
Pending classification of every relation (to be recomputed after the
G0-C.2 locator remediation):

```text
SPECIFIC_BOUND                specific clause + deterministic target link
SPECIFIC_EXPECTED_BUT_UNBOUND source cites the target, no link — GAP
GENERAL_ONLY                  no specific clause detected; inherits only
                              the instrument effective date
NOT_APPLICABLE                outside the evaluated clause/instrument scope
```

At discovery time, two subject families already fall into
SPECIFIC_EXPECTED_BUT_UNBOUND — `norma:31.apartado:3` and
`norma:22.apartado:18–20` — because of the parser defects below, not because
the clauses lack targets.

**Two real G0-C.2 recall gaps surfaced by the binding (reported, not fixed):**

```text
norma:31.apartado:3          op "i) Se modifica el apartado 3…" is wrapped in
                             a <blockquote> node → never became a locator →
                             no relation. Cited by dfu:a + dt1 (retroactivity).
norma:22.apartado:18/19/20   op "ii) Se modifican los apartados 17 a 20" bound
                             only apartado 17 — no range expansion in
                             subject extraction. Cited by dfu:c + dt2.
```

Both are objective parser defects (fixture-independent), documented here as
`subjects_cited_without_relation`. Recommended for a future G0-C.x fix, not
touched under this gate's rules.

**Rule references are correctly not bound**: `norma:17.apartado:6–8` and
`norma:60.apartado:6` are cited as the *applied accounting framework*
("de acuerdo con lo establecido en…"), not as modified subjects —
classified `cited_rule_references`.

## 7. D1–D11 verdicts (cases.json)

```text
D1  PASS  INSTRUMENT_EFFECTIVE_FROM 2025-12-30 (publication+1, DERIVED)
D2  PASS  a)–d) APPLY_FROM 2026-01-01, each bound to real relations
D3  PASS  monthly+quarterly → FIRST_REFERENCE 2026-03-31
D4  PASS  semiannual        → FIRST_REFERENCE 2026-06-30
D5  PASS  annual            → FIRST_REFERENCE 2026-12-31
D6  PASS  riesgo-país       → FIRST_REFERENCE 2026-06-30 (anejo 9.132 + IV)
D7  PASS  FI 131/141        → LAST_REFERENCE 2026-06-30, coexists with dfu:e
D8  PASS  RETROACTIVE_APPLICATION + INITIAL_APPLICATION_DATE as siblings
D9  PASS  option = ABSENCE_OF_OBLIGATION, EXCEPTION child of retro base
D10 PASS  consequence = QUALIFIER child of the option (conditioned)
D11 PASS  dt2 reproduces the pattern — model is not fixture-shaped
```

## 8. OBSERVED / DERIVED / INFERRED

```text
OBSERVED  22 clauses — every literal date, marker, subject, condition
          taken verbatim from the official text.
DERIVED    4 clauses — publication+1 resolution; frequency→state map via
          the norma 67 table; marker-path expansion to ops/relations.
INFERRED   0 persisted. One INFERRED-grade observation stays in this report
          only: dt2:4 ("La entidad no aplicará las modificaciones…") lacks
          the explicit "cuando haya optado" condition that dt1:5 carries;
          whether it is implicitly conditioned is a legal question, so the
          clause is stored conditioned = NULL (unconditioned), exactly as
          written.
```

## 9. Answers to the 12 questions

1. **26 explicit applicability clauses** (4 disposiciones, sentence-level).
2. **All 26 mechanically parsed** — every temporal effect, modality, subject
   and condition comes from patterns over the official text.
3. **16 clauses bind to relations; 49/65 relations bound.** Unbound
   relations legitimately inherit only the instrument effective date.
4. Parent/child edges observed: BASE, EXCEPTION, ALTERNATIVE, QUALIFIER,
   plus structural PART_OF. `sin perjuicio` = EXCEPTION carve-out.
5. Modalities: DECLARED_RULE, OBLIGATION, OPTION, ABSENCE_OF_OBLIGATION,
   NON_APPLICATION.
6. Temporal effects: the 8 in §3 — all required, none redundant.
7. Safely normalized conditions: `frequency_in {…}` (via norma 67 table),
   `exercise 2026`, `cites_section`, `PUBLICATION_PLUS_1`. Kept raw:
   "si un contrato deja de reconocerse…", "cuando haya optado por no
   reexpresar…" — preserved verbatim, not booleanized.
8. Retroactivity + option + consequence: **yes** — RETROACTIVE_APPLICATION
   base + EXCEPTION option + QUALIFIER consequence, all linked.
9. FIRST + LAST reference coexist: **yes** — different clauses on
   overlapping relations, no overwrite (FI 131/141).
10. Multiple clauses per relation: **yes** — demonstrated on the FI 131/141
    delete relations and generally via the matrix join.
11. No true conflicts found — everything is hierarchy: base rule +
    exceptions/options/qualifiers. The two "gaps" are G0-C.2 recall
    defects, not clause conflicts.
12. Outside automatic production (legal-interpretation boundary):
    whether dt2:4 is implicitly conditioned (unmarked in text); whether a
    stated option was *exercised* (depends on entity behavior — can only
    ever be recorded as external fact input, never inferred); equivalence
    between "aplicará retroactivamente" and NIIF 39-style transition
    mechanics cited by reference (norma 17.6–8).

## 10. Gaps

- `norma:31.apartado:3` — op lost to blockquote wrapping (G0-C.2 parser).
- `norma:22.apartado:18/19/20` — "apartados 17 a 20" range not expanded
  (G0-C.2 subject extraction).
- `modification_relations.effective_date` holds the modifier's general
  `fecha_vigencia`. **Recommendation: rename to `instrument_effective_date`
  in the G0-D implementation gate** — it is document metadata, not
  applicability.
- Sentence-level sub-clause splitting is heuristic-grade (deterministic
  rules, not LLM) — adequate for this corpus; widen corpus before
  freezing split rules.
- Norma 68 frequencies live in prose, not a table — DECLARED-grade for FI
  states only; FC-state frequency normalization needs more corpus.

## 11. Recommended production schema (NOT implemented)

```text
applicability_clause
  clause_id               deterministic hash
  declaring_instrument_id FK instruments
  source_locator          (section, item, sub, node_span, char_span)
  parent_clause_id        NULLABLE FK applicability_clause
  relation_to_parent      NULL|BASE|EXCEPTION|ALTERNATIVE|QUALIFIER|PART_OF
  modality                DECLARED_RULE|OBLIGATION|OPTION|
                          ABSENCE_OF_OBLIGATION|NON_APPLICATION
  action_raw              TEXT
  evidence_text           TEXT
  source_snapshot_id      FK source_snapshots
  epistemic               OBSERVED|DERIVED
  parser_name/version

applicability_effect      (one clause → N effects)
  effect_id, clause_id
  temporal_effect         the §3 taxonomy
  date_value NULL | date_raw NULL | period_raw NULL
  condition_raw NULL | condition_normalized JSON NULL
  epistemic

applicability_target      (many-to-many)
  clause_id → relation_id
  binding                 DECLARED|CONTAINER_EXPANDED
  via                     INTRODUCER_PATH|SUBJECT_LOCATOR
```

Clause-level `epistemic` never admits INFERRED — inferred readings live in
reports only. `modification_relations.effective_date` → rename to
`instrument_effective_date` at implementation time.

## 12. Verdict

```text
G0-D Discovery = GO
```

D1–D11 all representable with a generic clause/effect/target model — no
instrument-specific fields, no flattening, no LLM, no single-date collapse.
The conditions that resist mechanical normalization are preserved as raw
text with `normalized: NULL`, which is exactly the honest behavior.
```
