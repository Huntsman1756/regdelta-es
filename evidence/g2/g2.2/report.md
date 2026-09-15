# G2.2 sealed evaluation

run_id: g22-sealed

| target | risk class | gold | leaf | TP | FOR | AMB | NP | subj | O2P | rels | audited | R/P/U | bound | UNK | FF | FB | FSA | FLD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BOE-A-2004-21845 | CORRIGENDUM_PROPAGATION_RISK | 23 | 438 | 253 | 81 | 19 | 85 | 565 | 244 | 244 | 244 | 19/103/122 | 59 | 166 | 0 | 0 | 0 | 0 |
| BOE-A-2008-9915 | CORRIGENDUM_PROPAGATION_RISK | 7 | 20 | 15 | 3 | 0 | 2 | 21 | 13 | 13 | 13 | 1/7/5 | 2 | 8 | 0 | 0 | 0 | 0 |
| BOE-A-2016-5203 | MULTI_TARGET_MODIFIER | 2 | 24 | 24 | 0 | 0 | 0 | 30 | 28 | 28 | 28 | 4/3/21 | 6 | 4 | 0 | 0 | 0 | 0 |
| BOE-A-2019-15683 | MULTI_TARGET_MODIFIER | 1 | 2 | 1 | 1 | 0 | 0 | 2 | 1 | 1 | 1 | 0/1/0 | 1 | 0 | 0 | 0 | 0 | 0 |

## Limitations (§57 — not factual failures)

| target | ACQUISITION_FAILURE | other journal entries |
|---|---|---|
| BOE-A-2004-21845 | 0 | 516 |
| BOE-A-2008-9915 | 2 | 27 |
| BOE-A-2016-5203 | 0 | 58 |
| BOE-A-2019-15683 | 0 | 1 |

## Aggregate

| metric | num/den | value |
|---|---|---|
| declared_modifier_recall | 33/33 | 1.0 |
| operation_parsing_rate | 286/286 | 1.0 |
| representation_binding | 24/286 | 0.0839 |
| chain_reconstruction | 3/45 | 0.0667 |
| applicability_extraction | 15/16 | 0.9375 |
| query_execution | 20/20 | 1.0 |
| false_positive_facts | — | 0 |
| false_binding_count | — | 0 |
| false_subject_attribution_count | — | 0 |
| false_locator_declaration_count | — | 0 |
| source_limitations | — | 0 |
| old_false_fact_reproduction_count | — | 0 |
| g1_four_case_reproduction_count | — | 0 |
