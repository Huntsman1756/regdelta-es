# PORT-0 — coupling census map

Runtime `ebbfdde`. Machine-readable detail: `coupling-census.json`.
45 items: 14 PROFILE_MATERIAL, 27 PROFILE_INPUT_CORE_POLICY,
4 CORE items (C-023, C-027, C-031, C-036), 4 confirmed-core modules.

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
2. **Ownership split (frozen for PORT-1).** The profile does *not*
   own the meaning of canonical tokens — that would re-introduce
   factual authority through the back door:

   ```text
   profile owns:
     source lexemes
     regex/pattern data
     vocabularies
     source identifier syntax
     mappings from source forms -> core semantic kinds
   core owns:
     semantic kinds/taxonomies and their meaning
     canonical emitted spelling
     enumeration/adjudication policy
     ambiguity/abstention policy
   ```

   The profile maps `"apartado"` and its source variants to
   `LocatorKind.APARTADO`; the core decides what the kind means in
   the hierarchy and serializes `apartado:` back out. Same for
   verbs → `ADD/DELETE/MODIFY/SUBSTITUTE`. Emitted vocabulary
   (`locator_key` spellings, parser_names, source ids, status
   taxonomies) appears in byte-identical artifacts and cannot be
   renamed.
3. **Duplicated vocabulary is the smell.** State-code families live
   in four modules; ordinal tables in three; fichero connectors in
   three. Consolidation into one profile-owned vocabulary removes
   drift surface without touching policy.
4. **`db.py` is the surprise coupling.** `SOURCE_IDS` and
   `CHECK (source_id IN (...))` put the profile's source registry
   inside core DDL. Frozen direction for PORT-1: a **core registry
   fed by profile-supplied descriptors** — never profile-injected
   DDL. The profile declares `source_id`, parser identity and
   capabilities; the core keeps referential integrity. A registry
   table + FK is conceptually sounder than
   `CHECK(source_id IN profile-values)` because the latter varies
   core schema per profile.
5. **No item required moving a factual decision.** Every
   binding-relevant item splits as (profile vocabulary) → (core
   enumerate/adjudicate/abstain). The census found zero cases where
   byte-equivalence would force the profile to decide an outcome.
6. **C-009 consequence.** PORT-1 introduces a profile-supplied
   `canonical_instrument_token`; the core hashing policy operates
   on it. For BdE the token must remain byte-for-byte today's
   `boe_id` — no id migration is permitted.

## Architecture boundary (frozen for PORT-1)

C-033/C-042/C-044 jointly imply three layers — not one
`SourceProfile` object:

```text
Profile package (source-specific boundary)
    raw-byte adapters/parsers
    acquisition descriptors
    SourceProfile data

SourceProfile (immutable data only — no functions/callbacks)
    locator vocabulary
    marker grammar
    verb lexicon
    ordinal vocabulary
    state-code families
    identifier grammar
    document-class mappings
    source descriptors

Core
    canonical node-stream contract
    operation/ownership/binding policies
    lifecycle
    proof
    persistence semantics
```

The outer composition converts official bytes → node stream; from
that point the core works on a typed contract plus profile *data*.
Data in, adjudication stays core.

## PORT-1 directive

Do not transcribe the 27 PROFILE_INPUT_CORE_POLICY seams into 27
methods. Compress them into ~5–7 typed data facets feeding the
existing core engines: document-model vocabulary, locator grammar,
operative grammar, identity/reference grammar, annex/state
grammar, applicability language, source descriptors. A callback
surface would mean this census found a list of constants, not a
boundary.

```text
PORT-0 = DONE (PASS_WITH_AMENDMENTS applied)
finding: BdE coupling separable as PROFILE DATA -> CORE POLICY
factual decisions transferred to profile: 0
architecture hypothesis: SURVIVES
PORT-1: AUTHORIZED
```
