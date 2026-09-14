# G0-G DEV run 002-evaluator-fixes

runtime_head: `51e9cdfc4fbc83d63723bb7283e29105cd6748e3`

## Aggregate

| metric | num/den | value |
|---|---|---|
| declared_modifier_recall | 19/19 | 1.0 |
| operation_parsing_rate | 50/50 | 1.0 |
| subject_locator_resolution | 37/50 | 0.74 |
| representation_binding | 32/50 | 0.64 |
| chain_reconstruction | 0/0 | None |
| applicability_extraction | 2/2 | 1.0 |
| query_execution | 40/40 | 1.0 |
| false_positive_facts | — | 12 |
| source_limitations | — | 0 |

## Per target

| target | cell | rels | res(P/U) | recall | FF |
|---|---|---|---|---|---|
| BOE-A-2005-4749 | TEXTxCONSOLIDATED | 16 | 14/1/1 | 7/7 | 2 |
| BOE-A-2010-12488 | VISUALxCONSOLIDATED | 0 | 0/0/0 | 2/2 | 0 |
| BOE-A-2010-1824 | VISUALxCONSOLIDATED | 2 | 0/2/0 | 1/1 | 2 |
| BOE-A-2011-2378 | TEXTxNON_CONSOLIDATED | 11 | 10/1/0 | 5/5 | 2 |
| BOE-A-2012-3169 | VISUALxNON_CONSOLIDATED | 6 | 0/0/6 | 1/1 | 0 |
| BOE-A-2013-7467 | TEXTxNON_CONSOLIDATED | 3 | 2/1/0 | 1/1 | 2 |
| BOE-A-2016-4356 | VISUALxNON_CONSOLIDATED | 10 | 4/6/0 | 1/1 | 4 |
| BOE-A-2019-17286 | TEXTxCONSOLIDATED | 2 | 2/0/0 | 1/1 | 0 |

failures: 35 | audit rows: 50 | combined smoke ok: True
