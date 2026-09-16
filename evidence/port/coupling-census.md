# PORT-0 — coupling census map

Runtime `ebbfdde`. Machine-readable detail: `coupling-census.json`.
45 items: 17 PROFILE_MATERIAL, 21 PROFILE_INPUT_CORE_POLICY,
2 CORE singletons, 5 confirmed-core modules.

## The load-bearing seams

| seam | what moves | what stays |
|---|---|---|
| C-033 `DiarioDoc` node stream | concrete producer + cls/kind vocabulary (`articulo`, `anexo`, `p`, `table`…) | the node-stream contract — every enumerator's input interface |
| C-029 marker grammar | `_NUMERIC/_LETRA/_SIBLING/_LEVEL_BOUNDARY`, `_sub_pattern` | enumerate-all + level-aware boundary policy (F2) |
| C-019 locator-declaration grammar | `_PATTERNS`, enum separators, kind words | tokenizing policy: dotted id = one value; enumeration declares each value |
| C-010 verb grammar | `_AMEND_VERB_*`, `_INCLU_OBJ_RE`, verb lists | op-kind taxonomy + operative-position rule + nearest-verb derivation |
| C-016 state-code families | `FI|FC|PI|PC|PA|UEM|AVE` — duplicated across operations/annexmap/binding/applicability | anchor-vs-subject adjudication |
| C-042 source registry | `boe_*`/`bde_*` ids, URLs, parsers | snapshot/check/membership loop — but `db.py` CHECK constraints embed source ids, so the schema must become profile-extensible |
| C-009 identity derivation | `boe_id` token form | hash-of-identity-parts policy — ids are emitted values; byte-identity forbids any derivation change |

## Module view

```text
sources/*            PROFILE_MATERIAL        (bytes -> model, parser names emitted)
config.py            PROFILE_MATERIAL        (urls, source ids)
evidence_import.py   PROFILE_MATERIAL        (capture-layout naming)
util.py              core + C-038 date vocab
db.py                core schema; C-042 embeds source ids in CHECK constraints
watcher.py / state.py C-042 seam             (loop core; source pair profile)
operations.py        densest coupling        (verbs, locator grammar, ordinals,
                                              state codes, context families)
ownership.py         C-035 grammar + CORE adjudication
binding.py           C-028/C-029/C-030/C-032/C-033 seams around CORE enumeration
history.py           C-001..C-009 seams      (urls, target-ref, modifier discovery,
                                              coverage oracle vocab, locators)
annexmap.py          C-034
applicability_parser.py  C-037..C-040        (heaviest per-line vocabulary)
query.py             core + C-041 ref forms
diffing.py           confirmed core
```

## Observations for PORT-1

1. **The seam is vocabulary-vs-policy, not module-vs-module.** Almost
   every grammar constant sits inside a function whose adjudication
   policy is core. The profile interface is therefore *data*:
   grammar objects (patterns, vocab tables, kind maps, boundary
   tables) injected into core enumeration/adjudication engines —
   not callbacks, and never decision authority.
2. **Emitted vocabulary is frozen.** `locator_key` spellings,
   parser_name strings, source ids, status taxonomies all appear in
   byte-identical artifacts. The profile owns their *meaning*; it
   cannot rename them.
3. **Duplicated vocabulary is the smell.** State-code families live
   in four modules; ordinal tables in three; fichero connectors in
   three. Consolidation into one profile-owned vocabulary removes
   drift surface without touching policy.
4. **`db.py` is the surprise coupling.** `SOURCE_IDS` and
   `CHECK (source_id IN (...))` put the profile's source registry
   inside core DDL — PORT-1 must decide whether the schema takes a
   profile-provided registry or the constraint relaxes into a
   registry table.
5. **No item required moving a factual decision.** Every
   binding-relevant item splits as (profile vocabulary) → (core
   enumerate/adjudicate/abstain). The census found zero cases where
   byte-equivalence would force the profile to decide an outcome.

Status: PORT-0 DONE — awaiting review before PORT-1.
