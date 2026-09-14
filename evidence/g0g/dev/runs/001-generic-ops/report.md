# G0-G DEV run 001-generic-ops

runtime_head: `51e9cdfc4fbc83d63723bb7283e29105cd6748e3`

## Aggregate

| metric | num/den | value |
|---|---|---|
| declared_modifier_recall | 19/19 | 1.0 |
| operation_parsing_rate | 49/49 | 1.0 |
| subject_locator_resolution | 26/49 | 0.5306 |
| representation_binding | 22/49 | 0.449 |
| chain_reconstruction | 0/0 | None |
| applicability_extraction | 2/2 | 1.0 |
| query_execution | 40/40 | 1.0 |
| false_positive_facts | — | 37 |
| source_limitations | — | 0 |

## Per target

| target | cell | rels | res(P/U) | recall | FF |
|---|---|---|---|---|---|
| BOE-A-2005-4749 | TEXTxCONSOLIDATED | 16 | 4/9/3 | 7/7 | 16 |
| BOE-A-2010-12488 | VISUALxCONSOLIDATED | 0 | 0/0/0 | 2/2 | 0 |
| BOE-A-2010-1824 | VISUALxCONSOLIDATED | 2 | 0/2/0 | 1/1 | 2 |
| BOE-A-2011-2378 | TEXTxNON_CONSOLIDATED | 11 | 10/1/0 | 5/5 | 11 |
| BOE-A-2012-3169 | VISUALxNON_CONSOLIDATED | 5 | 0/1/4 | 1/1 | 5 |
| BOE-A-2013-7467 | TEXTxNON_CONSOLIDATED | 3 | 2/1/0 | 1/1 | 3 |
| BOE-A-2016-4356 | VISUALxNON_CONSOLIDATED | 10 | 4/6/0 | 1/1 | 0 |
| BOE-A-2019-17286 | TEXTxCONSOLIDATED | 2 | 2/0/0 | 1/1 | 0 |

failures: 59 | audit rows: 49 | combined smoke ok: True
