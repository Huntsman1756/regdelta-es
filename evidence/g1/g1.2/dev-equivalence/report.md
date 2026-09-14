# G1.2 sealed evaluation — run dev-equivalence

## Per target (first table, §28)

| target | gold | rels emitted | rels audited | before bound | after bound | R/P/U | FF | FB |
|---|---|---|---|---|---|---|---|---|
| BOE-A-2005-4749 | 7 | 16 | 16 | 8 | 10 | 11/1/4 | 0 | 0 |
| BOE-A-2010-12488 | 2 | 1 | 1 | 1 | 1 | 1/0/0 | 0 | 0 |
| BOE-A-2010-1824 | 1 | 2 | 2 | 1 | 1 | 0/2/0 | 0 | 0 |
| BOE-A-2011-2378 | 5 | 11 | 11 | 8 | 7 | 7/1/3 | 0 | 0 |
| BOE-A-2012-3169 | 1 | 6 | 6 | 0 | 0 | 0/0/6 | 0 | 0 |
| BOE-A-2013-5720 | 13 | 137 | 137 | 25 | 33 | 26/27/84 | 0 | 0 |
| BOE-A-2013-7467 | 1 | 3 | 3 | 2 | 1 | 1/1/1 | 0 | 0 |
| BOE-A-2016-1238 | 5 | 31 | 31 | 14 | 15 | 16/0/15 | 0 | 0 |
| BOE-A-2016-4356 | 1 | 10 | 10 | 0 | 4 | 3/7/0 | 0 | 0 |
| BOE-A-2019-17286 | 1 | 2 | 2 | 2 | 0 | 2/0/0 | 0 | 0 |
| BOE-A-2021-19805 | 1 | 0 | 0 | 0 | 0 | 0/0/0 | 0 | 0 |
| BOE-A-2021-21220 | 1 | 0 | 0 | 0 | 0 | 0/0/0 | 0 | 0 |

## Aggregate

| metric | num/den | value |
|---|---|---|
| declared_modifier_recall | 39/39 | 1.0 |
| operation_parsing_rate | 219/219 | 1.0 |
| subject_locator_resolution | 192/219 | 0.8767 |
| representation_binding | 67/219 | 0.3059 |
| chain_reconstruction | 3/19 | 0.1579 |
| applicability_extraction | 11/11 | 1.0 |
| query_execution | 60/60 | 1.0 |
| false_positive_facts | — | 0 |
| false_binding_count | — | 0 |
| source_limitations | — | 0 |
| old_false_fact_reproduction_count | — | 0 |

abstentions:

```
{
  "by_reason": {
    "candidate_count>1": 2,
    "clause scopes below the recorded subject locator": 181,
    "declared literals; no full replacement representation": 3,
    "following content is governed by a different sub-clause": 15,
    "no annex candidates": 5,
    "no operation-owned content link": 11,
    "no_structural_candidate": 15,
    "subject state UNKNOWN; predecessor representation not provable": 9
  },
  "by_side": {
    "after": {
      "BOUND": 72,
      "NOT_APPLICABLE": 9,
      "NOT_FOUND": 5,
      "NOT_PROVABLE": 133
    },
    "before": {
      "AMBIGUOUS": 2,
      "BOUND": 61,
      "NOT_APPLICABLE": 55,
      "NOT_FOUND": 15,
      "NOT_PROVABLE": 86
    }
  }
}
```

B1-B6 FAIL counts:

```
{
  "B1": 0,
  "B2": 0,
  "B3": 0,
  "B4": 0,
  "B5": 0,
  "B6": 0
}
```

corpus-73:

```
{
  "ALREADY_CORRECT_G0_EVALUATOR_ERROR": 16,
  "ABSTAINED": 57
}
```
