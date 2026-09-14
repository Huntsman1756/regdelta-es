# G0-G DEV run 000-baseline

runtime_head: `3e8e27df8999307bf4cbce42f77891a5827b4d81`

## Aggregate

| metric | num/den | value |
|---|---|---|
| declared_modifier_recall | 19/19 | 1.0 |
| operation_parsing_rate | 12/12 | 1.0 |
| subject_locator_resolution | 10/12 | 0.8333 |
| representation_binding | 4/12 | 0.3333 |
| chain_reconstruction | 0/0 | None |
| applicability_extraction | 1/2 | 0.5 |
| query_execution | 40/40 | 1.0 |
| false_positive_facts | — | 2 |
| source_limitations | — | 0 |

## Per target

| target | cell | rels | res(P/U) | recall | FF |
|---|---|---|---|---|---|
| BOE-A-2005-4749 | TEXTxCONSOLIDATED | 0 | 0/0/0 | 7/7 | 0 |
| BOE-A-2010-12488 | VISUALxCONSOLIDATED | 0 | 0/0/0 | 2/2 | 0 |
| BOE-A-2010-1824 | VISUALxCONSOLIDATED | 0 | 0/0/0 | 1/1 | 0 |
| BOE-A-2011-2378 | TEXTxNON_CONSOLIDATED | 0 | 0/0/0 | 5/5 | 0 |
| BOE-A-2012-3169 | VISUALxNON_CONSOLIDATED | 0 | 0/0/0 | 1/1 | 0 |
| BOE-A-2013-7467 | TEXTxNON_CONSOLIDATED | 0 | 0/0/0 | 1/1 | 0 |
| BOE-A-2016-4356 | VISUALxNON_CONSOLIDATED | 12 | 4/8/0 | 1/1 | 2 |
| BOE-A-2019-17286 | TEXTxCONSOLIDATED | 0 | 0/0/0 | 1/1 | 0 |

failures: 9 | audit rows: 12 | combined smoke ok: True
