# G0-G.2 — Sealed Holdout Evaluation

**Result: `G0-G.2 = FAIL`** — `PROTOCOL_INTEGRITY = PASS`, `FALSE_FACT_GATE = FAIL` (73 FALSE_FACT on 2 of 4 targets).

No runtime, evaluator, test, selection, gold or evidence change was made after `HOLDOUT_OPENED`. This report documents the outcome; per the frozen protocol, nothing was fixed or rerun.

## 1. Frozen state

| Item | Value |
|---|---|
| runtime_head | `d30d40f3dda1af2b4821788fd262f9a76fa7c357` |
| evaluation_head (`G0G2_EVALUATION_HEAD`) | `b7906213095239626b06deafa9ca0586ff81c58a` |
| evaluator code freeze commit | `0e4acdc28c9615ed85a1cedfd6206cf39ba492c3` |
| runner | `scripts/g0g/evaluate_sealed.py` sha256 `84b769da…6b52` |
| evaluator impl | `scripts/g0g/evaluate_dev.py` sha256 `99ff575e…3dc8` |

`git diff d30d40f..evaluation_head -- src/regdelta` → empty. All PREOPEN hashes are in `PREOPEN.json`.

## 2. DEV equivalence (pre-open, §6)

The sealed runner on `GENERALIZATION_DEV` reproduced the frozen G0-G.1 state exactly (`evidence/g0g/g0g2/dev-equivalence` vs `runs/005-redaccion-verb`): identical aggregate, identical per-target metrics, identical per-target inventories; 8 targets / 51 relations / 51 audit rows / 0 FALSE_FACT; modifier recall 19/19; ops 51/51; applicability 2/2; queries 40/40; resolution 34 RESOLVED / 9 PARTIAL / 6 UNRESOLVED; combined smoke ok=true.

## 3. Opening

- SEAL re-verified before opening (`test_seal_integrity` green; byte-level only).
- `opened_at` = `2026-09-14T09:19:11.267471+00:00` (official attempt `started_at`, `attempts.jsonl`).
- One attempt, `status: completed`, `official: true`. One-shot satisfied.
- Zero network; all bytes via `EVIDENCE_IMPORT` from the sealed manifest.

## 4. Per-target headline (§22)

| target | cell | gold modifiers | relations emitted | relations audited | FALSE_FACT |
|---|---|---|---|---|---|
| BOE-A-2013-5720 | TEXT×CONS | 13 | 137 | 137 | **68** |
| BOE-A-2016-1238 | VISUAL×CONS | 5 | 31 | 31 | **5** |
| BOE-A-2021-19805 | TEXT×NON_CONS | 1 | 0 | 0 | 0 |
| BOE-A-2021-21220 | VISUAL×NON_CONS | 1 | 0 | 0 | 0 |

The two zero-emission targets are not a hidden precision pass: their sole declared modifier is a *corrección de errores* (BOE-A-2022-9029, BOE-A-2021-21796), which declares no amendment operations; declared_modifier_recall is 1/1 on both.

## 5. Preregistered metrics — per target

| metric | 2013-5720 | 2016-1238 | 2021-19805 | 2021-21220 | aggregate |
|---|---|---|---|---|---|
| declared_modifier_recall | 13/13 | 5/5 | 1/1 | 1/1 | **20/20** |
| operation_parsing_rate | 137/137 | 31/31 | n/a | n/a | **168/168** |
| subject_locator_resolution | 107/137 (.781) | 30/31 (.968) | n/a | n/a | **137/168 (.815)** |
| representation_binding | 91/137 (.664) | 29/31 (.935) | n/a | n/a | **120/168 (.714)** |
| chain_reconstruction | 11/15 (2 BROKEN, 2 NOT_PROVABLE) | 1/4 (3 BROKEN) | n/a | n/a | **12/19** (5 BROKEN, 2 NOT_PROVABLE) |
| applicability_extraction | 5/6 | 3/3 | n/a | n/a | **8/9** |
| query_execution | 5/5 | 5/5 | 5/5 | 5/5 | **20/20** |
| false_positive_facts | **68** | **5** | 0 | 0 | **73** |
| source_limitations | 0 | 0 | 0 | 0 | 0 |

## 6. Resolution distribution (emitted relations)

| target | RESOLVED | PARTIAL | UNRESOLVED |
|---|---|---|---|
| BOE-A-2013-5720 | 91 | 35 | 11 |
| BOE-A-2016-1238 | 29 | 1 | 1 |
| total | 120 | 36 | 12 |

## 7. FALSE_FACT analysis (documented, not fixed)

73 relations carry at least one claim contradicted by official evidence:

| target | locator class | count |
|---|---|---|
| 2013-5720 | `anejo:` | 47 |
| 2013-5720 | `norma:` | 20 |
| 2013-5720 | `disp:` | 1 |
| 2016-1238 | `norma:` | 5 |

Contradicted claims (a relation may contradict several): `before_binding` ×46, `after_binding` ×44, `target_locator_resolves` ×16, `operation_verb_consistent` ×7.

Binding contradictions mean the emitted before/after representation's recorded content does not match the text found at the claimed node span in the official target document (or the span does not cover the locator token). The concentration on `anejo:`/`norma:` locators of Circular 1/2013 — the most heavily amended holdout target, with 13 declared modifiers and repeatedly substituted annexes — indicates the frozen runtime bound several clauses to the wrong structural span (e.g., renumbered/duplicated annex headings across versions), i.e. emitted a factually wrong binding claim rather than marking it unbound. `disp:transitoria.primera` and `operation_verb_consistent`/`target_locator_resolves` contradictions are smaller classes of the same failure mode. Per §19–20 each is a FALSE_FACT; no "close enough" category exists.

This is a genuine generalization failure of the frozen runtime on structures not present in DEV. Correction requires runtime/evaluator work that this gate forbids; it belongs to a future preregistered gate (G1) with a new holdout.

## 8. Failure inventory (closed taxonomy, `failures.jsonl`)

| class | 2013-5720 | 2016-1238 | 19805 | 21220 | total |
|---|---|---|---|---|---|
| EVALUATION_FAILURE (FALSE_FACT) | 68 | 5 | 0 | 0 | 73 |
| PARSER_FAILURE | 24 | 3 | 0 | 0 | 27 |
| ACQUISITION_FAILURE | 0 | 0 | 0 | 0 | 0 |
| SCHEMA_FAILURE | 0 | 0 | 0 | 0 | 0 |
| SOURCE_LIMITATION | 0 | 0 | 0 | 0 | 0 |

PARSER_FAILURE kinds: UNBOUND_SUBJECT, ANNEX_REFERENCE_UNRESOLVED, OUT_OF_TARGET_OPS (recorded exclusions), and one applicability miss on 2013-5720 ("disposicion sections present but 0 clauses").

## 9. Combined smoke (NON_GATE_DIAGNOSTIC)

`run/combined-smoke.json`: ok=true — the four targets sequentially in one DB produce no PK collisions, identity aliasing, cross-target leakage, FK failures or query contamination.

## 10. Protocol integrity

All §27 conditions verified post-run: src tree identical to `d30d40f` (content hash `a691825c…b6f2`); evaluator+runner committed pre-open and hashes match `PREOPEN.json`; DEV equivalence passed pre-open; SEAL, sealed manifest and sealed aggregate hashes unchanged after the run; selection and gold unchanged; zero network; 168/168 relations audited; results complete. → **PASS**

## 11. Verdict

```text
PROTOCOL_INTEGRITY = PASS
FALSE_FACT_GATE    = FAIL   (68 on BOE-A-2013-5720, 5 on BOE-A-2016-1238)
G0-G.2             = FAIL
claim              = none (GENERALIZATION_SUPPORTED_ON_SEALED_HOLDOUT not earned)
```

Interpretation per §30: at least one FALSE_FACT appeared, so the gate fails. The cause is documented above; it was not fixed and DEV was not reopened. The coverage metrics above (modifier recall 20/20, op parsing 168/168, locator resolution .815, binding .714, applicability 8/9) are reported exactly as measured and carry no post-hoc threshold.
