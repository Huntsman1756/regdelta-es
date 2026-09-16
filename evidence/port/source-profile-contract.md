# PORT-1 — SourceProfile contract

Status: DRAFT for review. Defines the interface the PORT-2
extraction must satisfy. No code moves under this document.

Basis: `evidence/port/coupling-census.json` (45 items), the frozen
rules in `PREREG.md` §PORT-1, and the akn-pt artifact shape
(profile = spec + data + fixtures + validator over an untouched
core).

## 1. Layers

```text
Profile package          (code at the boundary; per source)
    raw-byte adapters/parsers        sources/boe_*.py, bde_*.py
    acquisition descriptors          fetch plans, media types
    SourceProfile data               the object this contract defines
    profile fixtures + validator     real captured corpus + self-check

Core                     (source-independent)
    node-stream contract             what a parsed document IS
    operation / ownership / binding / lifecycle / proof / persistence
```

A run composes: `profile package` turns official bytes into the
core's node stream + metadata; the core engines consume the node
stream plus `SourceProfile` **data**. Nothing in `SourceProfile`
is callable.

## 2. Ownership split (binding on every facet)

```text
profile owns                              core owns
  source lexemes                            semantic kinds/taxonomies
  regex/pattern data                        meaning of those kinds
  vocabularies                              canonical emitted spelling
  source identifier syntax                  enumeration/adjudication
  mappings source form -> core kind         ambiguity/abstention
  normalization parameters                  normalize/compare policy
```

Emitted vocabulary is frozen by byte-identity: `locator_key`
spellings, `parser_name`/`parser_version` strings, `source_id`
tokens, status taxonomies and artifact_locator types appear in
sealed artifacts. A profile defines how source text *maps to*
these canonical values; it never renames them.

## 3. Facets

`SourceProfile` = eight immutable data facets. Each lists the
census items it absorbs and the core consumer.

### F1 `document_model` — node-stream vocabulary

```text
node_classes        { articulo, anexo, capitulo_num, capitulo_tit,
                      centro_*, parrafo, ... }
node_kinds          { p, table, ... }
locator_classes     classes that may carry locator content (C-026)
signature_boundary  'madrid,' tail form
head_boundary       { 'anejo' -> [next anejo head, articulo,
                     signature], ... }
```

Absorbs: C-026, C-033 vocabulary side, C-028 boundary words.
Consumed by: candidate enumerators (`articulo_spans`,
`anejo_spans`, `fichero_spans`, `disp_spans`, `annex_code_regions`).

The *enumeration* (all hits, span-to-next-boundary, duplicates
surface, child markers never truncate a parent — C-029 policy
side, C-031) is core.

### F2 `text_normalization` — comparison parameters

```text
unicode_form        'NFKD' + strip combining marks
case                casefold/lower
whitespace          collapse + strip + NBSP->space
quoting_marks       '«', '»'   (masked from structural matching)
connectors          stopword list for name tokenization
```

Absorbs: C-021 parameters, C-005 lexical side, C-045 vocabulary.
Consumed by: `_norm`, `_fichero_*`, `_span_covers_subject`,
masking paths.

The deterministic normalize-then-compare policy and the masking
policy (quoted text never grounds structure) are core.

### F3 `locator_grammar` — the `kind:value` vocabulary

```text
kinds               canonical kind tokens + emitted spellings
                    (norma, anejo, apartado, punto, letra, numeral,
                     nota, disp, estado, fichero, indice, pagina,
                     seccion, ...)
head_patterns       per-kind head grammar (C-028 pattern side)
marker_patterns     numeric / letra / sibling / compound-code forms
level_boundary      kind -> same-or-outer-level boundary map
ordinals            word <-> number, feminine forms, 'única',
                    roman forms (C-015)
value_continuation  bare-segment continuation alphabet + rule data
head_forms          mention-expansion alternates (C-022 vocab)
```

Absorbs: C-015, C-028/C-029/C-030 vocabulary sides, C-022 vocab.
Consumed by: `text_region_candidates`, `_locator_parts`,
`_sub_pattern`, `sub_region_candidates`, `_locator_mentions`.

Core retains: the `kind:value` dotted format itself, bare-segment
continuation *policy*, level-aware boundary *policy*, B1/B2
adjudication.

### F4 `operative_grammar` — clause vocabulary

```text
amend_verbs         active/passive verb lexicon, per-op-kind
                    mapping data (verb -> ADD|DELETE|MODIFY|
                    SUBSTITUTE)
verb_exclusions     'desglosa'-class exclusions
structural_objects  'incluir' object whitelist
subordinators       subordinator inventory
subject_openers     'En la norma…', bare-subject forms
content_pointers    'donde dice', 'queda redactado', annex-ref
                    phrases, literal-pair forms
non_op_tail         'sin que/perjuicio'
enum_separators     a/al/,/y/e + mention patterns per kind
seg_separators      sub-clause split set
qualifiers          bis/ter/quáter…, '.x' suffix forms,
                    sub-scope word list
root_families       context root names (norma/anejo/disposicion)
ordinal_items       unmarked ordinal-item forms ('Cinco.')
kind_words          per-kind plural/singular mention words
```

Absorbs: C-010–C-014 vocab, C-017–C-020, C-024/C-025 vocab,
C-003's `palabra` values (CORREG/CORREC), marker strip `_MARKER_RE`.
Consumed by: `parse_all_operations`, `_has_operative_verb`,
`_clause_op_kind`, `subject_operation_kind`, context walkers,
`_has_unmodelled_qualifier`.

Core retains: the op-kind taxonomy, operative-position rule,
earliest/nearest-verb derivations, enumeration-tokenizing policy,
root-displacement policy, unmodelled-qualifier → coarser-locator
policy, and CONTENT_LINK_METHODS taxonomy (C-027).

### F5 `identity_reference` — identifier grammar

```text
canonical_instrument_token   syntax for the instrument token;
                             BdE instance = literal boe_id form
instrument_ref_forms         'BOE-A-YYYY-N', 'circular N/YYYY'
target_ref_forms             'Circular N/AAAA' incl.
                             'del Banco de España' word order
owner_ref_forms              'anejo de la Circular N/AAAA'
eli_pattern                  '/cir/YYYY/MM/DD/N'
modifier_discovery           metadata field ('posteriores') +
                             kind vocabulary
```

Absorbs: C-002, C-003 vocab side, C-009 token side, C-014 vocab,
C-041. Consumed by: `reconstruct` target-ref derivation, modifier
discovery, `ownership.attribute_operation`, query ref resolution.

Core retains: id-hashing policy over the canonical token (no id
migration — BdE token is byte-for-byte today's `boe_id`),
owner-construction-wins attribution policy, declared-modifier
graph policy.

### F6 `annex_state` — annex & state-code grammar

```text
state_code_families     { FI, FC, PI, PC, PA, UEM, AVE }
code_forms              code-header, quoted-code, paren-code,
                        anchor-phrase patterns
code_normalization    _norm_code parameters
fichero_vocabulary    'fichero «name»' forms, owner forms
annex_markers         'ANEJO' head, 'Pág. N', annex node classes
index_threshold       INDEX_CODE_THRESHOLD
```

Absorbs: C-016 (all four duplicated copies collapse here), C-032
vocab, C-034 vocab, C-005 fichero concept vocabulary.
Consumed by: `annexmap`, `annex_code_regions`, anchor-vs-subject
paths, `_target_annex_map` inputs.

Core retains: anchor-vs-subject adjudication, page-mapping
algorithm, duplicate-code → separate-candidates policy.

### F7 `applicability_language` — scope/declarative vocabulary

```text
dates                 MONTHS, date forms, DDMMYYYY, compact forms
frequencies           freq words -> canonical frequency kinds
disposicion_heads     transitoria/final/adicional/derogatoria +
                      prefixes + ordinal words
temporal_markers      phrase -> temporal semantic category
modality_markers      phrase -> modality semantic category
conditional_openers   'Si', 'Cuando' forms
signature_form        'Madrid, …'
scope_reference_forms apartado-de-norma, estados, letras,
                      numerales, sin-perjuicio, especificidades
```

Absorbs: C-037, C-038, C-039 vocab, C-040 vocab.
Consumed by: `applicability_parser`.

Core retains: the semantic category taxonomies (APPLY_FROM,
OBLIGATION, …) and scope-resolution policy.

### F8 `source_descriptors` — registry inputs

```text
sources[]             per source:
                        source_id            (emitted; frozen)
                        url_templates        acquisition addressing
                        media_types
                        parser_identity      {name, version} —
                                             emitted in snapshot rows
                        artifact_roles       diario_xml / doc_html /
                                             annex_pdf / image /
                                             sumario / consultas
capture_layout        filename->source_id conventions
```

Absorbs: C-001, C-042 profile side, C-043, C-044 (declared — the
parsers themselves live in the package, not here).
Consumed by: `watcher` loop, `reconstruct` acquisition,
`evidence_import`, `db` registry.

Core retains: snapshot/check/membership schema, the registry
table, referential integrity, anomaly policy. The profile never
injects DDL; `SOURCE_IDS`/CHECK constraints are replaced by the
core registry populated from descriptors.

## 4. What the profile may NOT decide

Explicit non-authority list (enforced by PORT-2 review):

1. No binding outcome — BOUND/AMBIGUOUS/NOT_* are core decisions.
2. No ambiguity resolution — a profile can narrow the candidate
   vocabulary, never choose among surviving candidates.
3. No emitted-value change — no spelling, id, status, locator or
   taxonomy value may differ from the frozen artifacts.
4. No lifecycle/chain state — PRESENT/DELETED/UNKNOWN derivations
   are core.
5. No factual provenance — profile identity/version appears only
   in the run envelope / registry / diagnostics (PREREG §PORT-2).
6. No DDL — descriptors only.
7. No code — `SourceProfile` is data; parsers live in the package.

## 5. Profile self-validation (akn-pt checklist shape)

A conforming profile package ships:

```text
SourceProfile data      the facets above
spec note               what each vocabulary means in the source
fixtures                real captured artifacts (never synthetic)
validator               profile-local check: every pattern compiles,
                        every mapping targets a declared core kind,
                        fixture corpus parses to the declared node
                        classes, no facet field is empty
```

The validator checks profile *well-formedness* only; it cannot
weaken core adjudication.

## 6. Instantiation statement

The BdE instance (`SourceProfile` populated from the census
vocabularies) must, under PORT-2, reproduce every frozen artifact
byte-identically per the SEMANTIC_ARTIFACTS/RUN_ENVELOPE split.
C-016 is the designated validation case: one profile-owned
`state_code_families` grammar replaces four scattered copies with
zero drift, or the abstraction is defective.

## 7. Open questions for review

1. `estado:`/`fichero:` subjects are BdE-specific *kinds* (not just
   vocabulary). Does the kind set itself belong to the core
   contract or to F3? Current position: kind tokens are emitted
   spelling → core contract; their *recognition grammar* → profile.
2. `pagina` locators are an errata-correction form; keep in F3 or
   under F5's ref grammar? Currently F3.
3. Whether `document_model` also owns the *metadata* vocabulary
   (`titulo`, `fecha_publicacion`, `posteriores`) or whether that
   belongs to F5's modifier-discovery descriptor. Currently split:
   field names → F5, node classes → F1.
