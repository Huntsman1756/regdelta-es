# G1.2 sealed evaluation — run g1.2-official

## Per target (first table, §28)

| target | gold | rels emitted | rels audited | before bound | after bound | R/P/U | FF | FB |
|---|---|---|---|---|---|---|---|---|
| BOE-A-2010-15521 | 2 | 1 | 1 | 0 | 0 | 0/0/1 | 0 | 0 |
| BOE-A-2012-9058 | 8 | 31 | 31 | 3 | 5 | 4/3/24 | 4 | 0 |
| BOE-A-2014-1183 | 4 | 19 | 19 | 9 | 3 | 9/0/10 | 0 | 0 |

## Aggregate

| metric | num/den | value |
|---|---|---|
| declared_modifier_recall | 14/14 | 1.0 |
| operation_parsing_rate | 51/51 | 1.0 |
| subject_locator_resolution | 44/51 | 0.8627 |
| representation_binding | 13/51 | 0.2549 |
| chain_reconstruction | 0/9 | 0.0 |
| applicability_extraction | 6/6 | 1.0 |
| query_execution | 15/15 | 1.0 |
| false_positive_facts | — | 4 |
| false_binding_count | — | 0 |
| source_limitations | — | 0 |

abstentions:

```
{
  "by_reason": {
    "clause scopes below the recorded subject locator": 58,
    "following content is governed by a different sub-clause": 1,
    "no annex candidates": 1,
    "no operation-owned content link": 2,
    "no_structural_candidate": 2,
    "subject state UNKNOWN; predecessor representation not provable": 1
  },
  "by_side": {
    "after": {
      "BOUND": 8,
      "NOT_APPLICABLE": 7,
      "NOT_FOUND": 1,
      "NOT_PROVABLE": 35
    },
    "before": {
      "BOUND": 12,
      "NOT_APPLICABLE": 10,
      "NOT_FOUND": 2,
      "NOT_PROVABLE": 27
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
