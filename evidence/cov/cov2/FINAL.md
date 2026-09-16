# COV-2 FINAL — DEV representation-binding coverage hardening

Terminal report for `PREREG.md`. Executed DEV-only per the COV-2A
decision recorded in `protocol.md` (COV-3 selection STOP — no
materializable holdout).

## §63 headline — CURRENT_OPERATIONAL

```text
baseline positive bindings    354   (before 182 / after 172)
final positive bindings       468   (before 296 / after 172)
required                      443

delta                        +114   (+32.2% vs baseline)

relations emitted            519 -> 519
locator-proven ops           445 -> 445
leaf operation accounting    1266 / 1266 = 100%

FALSE_FACT                    0
FALSE_BINDING                 0
FALSE_SUBJECT_ATTRIBUTION     0
FALSE_LOCATOR_DECLARATION     0

before binding coverage       296 / 519 sides
after binding coverage        172 / 519 sides
distinct contributing rels    356
Wilson 95% (sides)            0.4510  [0.4208, 0.4813]
```

## HISTORICAL_PREDECESSOR (reported separately, §50/§63)

```text
positive bindings             0 -> 1   (norma:2 before, BOUND via F1)
relations emitted             1 -> 1
locator-proven ops            1 -> 1
leaf operation accounting     16 / 16 = 100%
FALSE_*                       0/0/0/0
```

Historical floors satisfied (non-regression; the stratum improved).

## Verdict

```text
COV-2_DEV       = PASS
COV-3_READINESS = NOT_READY_FOR_COV_3
```

## §73 deliverable

```text
 1. base HEAD
      7066fa0aa1fc60a0ac45999d354fce0c098f7318 (PREREG base)
 2. COV-3 selected targets and strata
      none — selection STOP: CURRENT_OPERATIONAL eligible 0 < 3;
      sole eligible candidate BOE-A-1995-22113 is
      HISTORICAL_PREDECESSOR (vigencia_agotada=S)
      (evidence/cov/cov3/selection.json)
 3. COV-3 SEAL hashes
      none — holdout UNMATERIALIZABLE; nothing was sealed;
      discovery-raw contains 5 metadata-only fetches
      (CAPTURED_STRUCTURALLY, never semantically read)
 4. semantic seen-set hash
      evidence/cov/semantic-seen-set.json (87 boe_ids)
      sha256 259bf7c0ba00ab1923d34b5cce2dd7b4fd0628b2611b7d678a3af589c29d652c
 5. baseline HEAD
      6bda96f46be0983c5ac236c0dc00b96d6a4806d3
 6. baseline src tree
      sha256 6dd38af07b0b9d5db80a90b2a073f818817319f3
      (byte-identical DEV reproduction vs evidence/g2/dev/runs/001-g21)
 7. evaluator HEAD/hash
      frozen at 46a77f4224c62f0f2bb2ad4432b0ec22a95edf1d
      evaluate_cov2.py sha256
      43cc3d965cfe79c9a4fc6f64d1a9c252f93a55dbb71e17bcc957ed34458a43b4
      (unchanged through COV-2C/2D)
 8. debt census
      evidence/cov/cov2/debt-census.json (baseline, 684 unclaimed
      CURR sides); final-run census in runs/003-final/debt-census.json
 9. baseline CURRENT metrics
      354 positive / 519 relations / 445 locator-proven / 100% leaf /
      FALSE_* 0 / 684 unclaimed sides
10. baseline HIST metrics
      0 positive / 1 relation / 1 locator-proven / 100% leaf
11. generic fixes
      F1 c4bed51 — before-binding for sub-scoped operations
      F2 ebbfdde — tolerant structural marker enumeration +
                  level-aware candidate regions
      (evidence/cov/cov2/fixes.jsonl)
12. RED→GREEN evidence
      tests/cov/test_cov2_subscope.py (6 tests, RED on frozen runtime,
      GREEN after F1)
      tests/cov/test_cov2_markers.py  (13 tests, RED on F1 runtime,
      GREEN after F2)
13. table-binding methods added
      none — table enumeration was investigated and rejected:
      the suspected table debt is image-only annex content absent
      from captured XML; no honest mechanism exists on frozen
      evidence (recorded in census notes)
14. redesignation edges
      discovered 0 / actionable 0 / used 0 / refused 0 —
      no source-declared redesignations in the DEV corpus
      (continuity.jsonl, 520 hops journaled)
15. same-date groups
      33 groups journaled, all ORDER_RESOLVED_OFFICIAL
      (ordering.jsonl); 0 ORDER_AMBIGUOUS
16. scope collisions identified
      15 hops with incompatible scope signature
      (continuity.jsonl, scope_compatible=false)
17. scope collisions prevented from chaining
      15 — none emitted CHAIN_PREDECESSOR
18. final positive bindings CURRENT
      468
19. required 443 target
      met (468 >= 443, margin +25)
20. positive binding delta
      +114 (+32.2%)
21. before/after distribution
      before 296 / after 172
22. distinct contributing relations
      356 (of 519 emitted)
23. Wilson interval
      0.4510 [0.4208, 0.4813] over 1038 CURR binding sides
24. relations baseline->final
      519 -> 519
25. locator-proven ops baseline->final
      445 -> 445
26. leaf-operation accounting
      1266/1266 = 100% (reconciliation_problems 0)
27. historical metrics baseline->final
      0->1 positive / 1->1 relations / 1->1 locator-proven
28. debt matrix
      final-metrics.json debt_matrix; headline:
      SUBJECT_SCOPE_NOT_PROVABLE  374 -> 82 converted
      NO_STRUCTURAL_CANDIDATE      44 -> 25 converted
      TABLE_CONTENT_NOT_ENUMERATED 25 ->  7 converted
      (remaining classes unchanged or honestly reclassified;
      coverage-delta.jsonl has the per-side ledger)
29. mechanism attribution of coverage gain
      F1 sub-scope before-binding:  +75 CURR (+1 HIST)
      F2 marker/region enumeration: +39 CURR
      no unexplained gain: 114 = 75 + 39
30. FALSE_FACT               0
31. FALSE_BINDING            0
32. FALSE_SUBJECT_ATTRIBUTION 0
33. FALSE_LOCATOR_DECLARATION 0
34. B1-B6
      0 failures — decide() still unique-or-abstain; F2 ambiguity
      degrades (letra:i vs roman-i abstains AMBIGUOUS, 2 cases)
35. binding_proof consistency
      0 violations — every runtime BOUND verdicted BINDING_CORRECT
      by the frozen evaluator (469/469, both strata)
36. subject_proof consistency
      0 violations — O2 PROVEN 520/520, O1 TARGET_PROVEN 482
37. G0/G1/G2 regressions
      corpus-73: 61 ABSTAINED -> 60 ABSTAINED + 1 CORRECTED
      (improvement, zero REPRODUCED_FALSE_*)
      four-cases: 4 NOT_EMITTED (identical)
      G2 factual gates: 0 failures (520/520 audit PASS)
38. applicability
      evaluate_cov2 applied to all 16 DEV targets; audit_amendments 0
39. query execution
      0 failures; subject outcomes 1539 rows, o2_proven_not_emitted 0
40. anti-hardcoding
      PASS — test_no_new_target_specific_literals green; zero new
      BOE IDs / Circular numbers / locator literals in src/regdelta
41. COV-3 holdout integrity
      no holdout exists (UNMATERIALIZABLE); discovery-raw untouched
      since COV-2A; no semantic read occurred
42. runtime HEAD
      ebbfdde3eb513de05a57d86d004d23ca71e91f59  (COV_RUNTIME_HEAD)
43. evaluation HEAD
      ebbfdde3eb513de05a57d86d004d23ca71e91f59  (evaluator file
      unchanged since 46a77f4; sha above)
44. src_tree_sha256
      1736a9c6ad025041a9d6250ffd005657d9ee9151
45. full suite
      COV-2 targeted tests        = 97 PASS
        (tests/g1 + tests/g0g + tests/cov)
      repository full suite       = 347 PASS
        (uv run pytest -q; includes the six G0-cohort count anchors
        updated under COV-2_INTENTIONAL_SEMANTIC_CHANGE — F1/F2
        legitimately shift representations 186 -> 255 and anomalies
        457 -> 361 on the CORE target; see
        test_g0c_counts_unchanged)
46. git status
      clean at freeze commit (all run artifacts committed)
47. READY / NOT_READY
      NOT_READY_FOR_COV_3
```

## Runtime freeze (§67/§68)

```text
COV_RUNTIME_HEAD    ebbfdde3eb513de05a57d86d004d23ca71e91f59
src_tree_sha256     1736a9c6ad025041a9d6250ffd005657d9ee9151
parser versions     history v4->v5 ; structural_binding g1-v1->cov-v1
                    (operations v4, boe_* parsers unchanged)
runtime-literals    baseline sha256
                    031566007ffb638ffaa278c646ef0aee5527c9886960069d0f4ae327c166aea5
COV_EVALUATION_HEAD ebbfdde3eb513de05a57d86d004d23ca71e91f59
evaluator sha256    43cc3d965cfe79c9a4fc6f64d1a9c252f93a55dbb71e17bcc957ed34458a43b4
```

## Claim ceiling (§70)

> On the frozen DEV CURRENT_OPERATIONAL corpus, RegDelta increased
> independently verified positive representation-binding assertions
> from 354 to 468 while preserving the preregistered factual surface
> and zero-false-claim gates.

No fresh-corpus claim is made. Fresh-corpus validation is deferred to
a separate preregistration — preferably a prospective-temporal
holdout (the next qualifying BdE Circular becomes genuinely future
evidence against the COV-2-frozen runtime).
