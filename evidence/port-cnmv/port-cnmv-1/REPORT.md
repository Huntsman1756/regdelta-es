# PORT-CNMV-1 — DEV report

**Proposed terminal state: `PROFILE_LIMIT`**

The second `SourceProfile` (`cnmv-circular`) operates end-to-end on the
four DEV targets with zero core changes and zero evaluator-confirmed
false claims — but enumerated CNMV constructs admit only documented
abstention under the frozen contract (register below). Adjudication
of this proposal is the gate decision; `PROFILE_LIMIT` preregisters a
narrower PORT-CNMV-2 scope.

## Freeze record

| artifact | sha256 / ref |
|---|---|
| profile `src/regdelta/profiles/cnmv.py` | `b10473487d18065b823df5c1637cc6a7103e5d019b4ff4f74ca7b1897333a8b9` |
| runtime `src/regdelta` tree | `b67755f73912217242921f0c8c8cc5babd4b0e97` (git tree @ `3f713cc`) |
| boundary adapter `scripts/port-cnmv/cnmv_boundary.py` | `d5af7efcd52f3753baddd61e507cd40b6cd17675e4a70d550738ad174e3f5ff1` |
| runner `scripts/port-cnmv/run_dev_probe.py` | `5777f1ea469d7cdc9aa61869e7518348cafc49ba364feb20a8b3afb9fc19d690` |
| evaluator `scripts/port-cnmv/evaluate_dev.py` | `69ab3428d086bb9e15cc5c21395242779f40c3df0ad715fc8198433597498193` |
| journal `journal.jsonl` | `e3e1e8522392b8ce6b1ea12b3ca5f447aeadf1ceac467328b8f7d9a5b70b9385` |
| DEV run envelope | `dev-run-013.json` (materialized: `runs/013-dev-final/`) |
| evaluator output | `eval-dev-005.json` |

Evaluator import manifest (firewall audit — complete transitive
project-module set): `regdelta`, `regdelta.document`,
`regdelta.sources`, `regdelta.sources.boe_diario`,
`regdelta.sources.boe_doc`, `regdelta.sources.boe_pdf`. No profile,
registry, `active_profile`, or profile-backed helper is imported.
`EVALUATOR_INDEPENDENCE_BROKEN` does not apply.

## DEV observed volume

| target | modifiers | leaf ops | accounting | relations | RESOLVED | PARTIAL | UNRESOLVED | confirmed | abstained |
|---|---|---|---|---|---|---|---|---|---|
| BOE-A-2008-16091 | 10 | 68 | 17+39+12=68 ✓ | 18 | 4 | 4 | 10 | 4 | 14 |
| BOE-A-2008-20895 | 9 | 116 | 54+57+4+1=116 ✓ | 70 | 20 | 24 | 26 | 20 | 50 |
| BOE-A-2010-13162 | 6 | 55 | 14+39+2=55 ✓ | 30 | 9 | 6 | 15 | 9 | 21 |
| BOE-A-1994-28725 | 6 | 12 | 3+3+6=12 ✓ | 1 | 1 | 0 | 0 | 1 | 0 |

Evaluator totals over 119 relations: `CONFIRMED_POSITIVE` 34,
`ABSTENTION_CONFIRMED` 85, `ABSTENTION_DISPUTED` 0, `FALSE_FACT` 0,
`FALSE_SUBJECT_ATTRIBUTION` 0, `FALSE_LOCATOR_DECLARATION` 0,
`FALSE_BINDING` 0. Independent clause census: 2002.

## §9 checks

- **Operation accounting 100%** — leaf ops = sum of dispositions on
  all four targets (table above).
- **Zero false facts** — every FALSE_* class is 0.
- **No silent pass** — every target emits ≥1 evaluator-confirmed claim
  (28725: the `norma:11` rewrite, RESOLVED + CONFIRMED_POSITIVE).
- **BdE regression** — `import regdelta.profiles` registers exactly
  `bde-circular` (implicitly active); `pytest tests` = 347 passed.

## Abstention register (cause → span)

Binding/lifecycle abstentions, all journaled in `audit.jsonl`:

- `BINDING_NOT_FOUND` `no_structural_candidate` (43): before-side
  content absent from the target XML — image-only annex models and
  unnumbered sub-structure.
- `BINDING_NOT_PROVABLE` `no operation-owned content link` (32),
  `clause scopes below the recorded subject locator` (15),
  `following content is governed by a different sub-clause` (9),
  `bound span does not restate the subject locator` (1),
  `subject state UNKNOWN/DELETED` (10): ownership, scope and
  chain-lifecycle discipline.
- `CHAIN_DISCONTINUITY` deleted/unknown (10).
- `AMBIGUOUS_BINDING` `candidate_count>1` (2).
- `UNBOUND_SUBJECT` (51): relations whose required bindings all
  abstained (ADD 11, DELETE 11, MODIFY 16, SUBSTITUTE 13).

Construct-level abstentions (the PROFILE_LIMIT register):

1. **`seccion:` locators** — `LOCATOR_KINDS` (frozen) has no section
   kind; "La Sección Quinta … queda redactada" (28725, modifier
   2008-7880 item Dos) is declared in the mention record but cannot
   compose a subject. Honest non-emission; composing it requires a
   core taxonomy extension.
2. **Unnumbered disposiciones** — "una disposición transitoria con la
   siguiente redacción" carries no ordinal; `disp:` keys are
   `tipo.ordinal` pairs, so no key is composed (journal #12).
3. **Two-level nesting** — "número N del apartado X) de la norma M"
   nests under a lettered apartado; the flat key space cannot express
   the intermediate level, so the composed key abstains.
4. **Image-only annex content** — `boe_diario` `<img href>` carries no
   fetchable source and the 162-page legacy PDF of 20895 has zero
   image-annex pages (`n_images=0` → PREANNEX), so `estado:*` subjects
   on that target abstain rather than fabricate.
5. **Unnumbered continuation items** — apartados 6–8 of norma 29
   (20895) exist as unnumbered continuations, not item starts;
   `norma:29.apartado:8` correctly abstains `NOT_PROVABLE`.

## Frozen positive-evidence rule for PORT-CNMV-2

```text
Per HOLDOUT target:
  - operation accounting = 100% (leaf ops = sum of dispositions)
  - >= 1 CONFIRMED_POSITIVE relation, OR every emitted relation a
    classified abstention with a named cause
  - FALSE_FACT = FALSE_SUBJECT_ATTRIBUTION = FALSE_LOCATOR_DECLARATION
    = FALSE_BINDING = 0
  - no fetch outside the HOLDOUT manifest; no semantic HOLDOUT access
    before this gate's adjudication
Expected DEV-observed volume: ~1-70 relations/target depending on
modifier density; confirmed-positive fraction ~15-30%.
```

## Journal summary (14 entries)

Harness/ordering (#1–#4), canonical `anejo` keying + `bis|ter|quáter`
(#5–#6), ordinal-word operative openers + `seccion` visibility (#7),
legacy stylesheet boundary adapter (#8), marked numeric ordinals (#9),
letter-spaced/legacy PDF state codes (#10–#11 with families A/CA/GA/P),
bogus `disp:transitoria.con` ordinal capture (#12), stale persist-dir
contamination (#13), evaluator finding adjudication (#14).
