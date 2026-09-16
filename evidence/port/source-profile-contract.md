# PORT-1 — SourceProfile contract

Status: DONE (APPROVE_WITH_AMENDMENTS applied — see §7). Defines
the interface the PORT-2 extraction must satisfy. No code moved
under this document.

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
enabled_kinds       which core LocatorKinds this source recognizes
kind_lexemes        core kind -> source lexemes ('apartado',
                    'apartados', ...)
head_patterns       per-kind head grammar (C-028 pattern side)
marker_patterns     numeric / letra / sibling / compound-code forms
level_boundary      kind -> same-or-outer-level boundary map
ordinals            word <-> number, feminine forms, 'única',
                    roman forms (C-015)
value_continuation  bare-segment continuation alphabet + rule data
head_forms          mention-expansion alternates (C-022 vocab)
```

The core — not this facet — owns the `LocatorKind` registry, its
canonical spellings (`norma`, `anejo`, `apartado`, …, `estado`,
`fichero`), and each kind's meaning/hierarchy. The core is a
semantic superset; a profile uses a subset. `estado` is a core kind
even if only BdE ever enables it.

```text
profile may reference a core kind
profile may NOT mint a new core kind
```

A source needing a genuinely new category fails its profile
validation (`UNKNOWN_CORE_KIND`) — evidence that the core must
evolve through a gate, not permission to silently extend the
ontology.

Absorbs: C-015, C-028/C-029/C-030 vocabulary sides, C-022 vocab.
Consumed by: `text_region_candidates`, `_locator_parts`,
`_sub_pattern`, `sub_region_candidates`, `_locator_mentions`.

Core retains: the `kind:value` dotted format itself, bare-segment
continuation *policy*, level-aware boundary *policy*, B1/B2
adjudication.

### F4 `operative_grammar` — clause vocabulary

```text
amend_verbs         active/passive verb lexicon, per-op-kind
                    mapping data ('modifica' -> MODIFY, 'suprime'
                    -> DELETE); ADD/DELETE/MODIFY/SUBSTITUTE
                    themselves are core enums, never profile-minted
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
relation_classification      vocabulary that classifies
                             already-parsed declared relations
                             (CORREG/CORREC -> CORRECTION)
```

Raw metadata *field names* are not here — see F8
`metadata_mapping`/`relation_mapping`. The core consumes a
canonical document contract (`titulo`, `fecha_publicacion`,
`posteriores` remain today's canonical compatibility names); a
future CNMV parser produces the same contract without the core
ever knowing the source tag names. The core never asks for a BOE
XML tag.

Absorbs: C-002, C-003 classification-vocab side, C-009 token side,
C-014 vocab, C-041. Consumed by: `reconstruct` target-ref
derivation, relation classification, `ownership.attribute_operation`,
query ref resolution.

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
index_threshold       the calibrated value (BdE = 10); the
                      *decision* 'count >= threshold -> INDEX' and
                      the mapping algorithm stay core (amended
                      C-034 split)
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
metadata_mapping      raw source field -> canonical contract field
                      ('<fecha_publicacion>' -> 'fecha_publicacion')
relation_mapping      raw relation container -> canonical
                      direction ('<posteriores>' -> declared
                      modifications)
capture_layout        filename->source_id conventions
```

Registry invariants (core-enforced, profile cannot alter):

```text
source_id unique
descriptor required before source use
unknown source_id fails closed
existing BdE source_id values remain byte-identical
profile descriptors cannot alter registry integrity policy
```

The profile contributes rows; the core controls what a valid
registry means.

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

## 7. Review resolutions (2026-09-16 — APPROVE_WITH_AMENDMENTS)

1. **Kinds**: resolved — core owns the `LocatorKind` registry,
   canonical spellings, meaning and hierarchy; the profile
   enables/recognizes core kinds and supplies lexemes + patterns
   per kind (F3 amended). `estado`/`fichero` are core kinds that
   only BdE currently enables. A profile may reference a core kind
   but never mint one — `UNKNOWN_CORE_KIND` on violation. Same
   rule for op-kinds: verb→kind mapping is profile data, the kind
   enum is core.
2. **`pagina`**: stays in F3 — it locates *within* the document,
   not *which* instrument. F3 answers "where inside", F5 answers
   "which work".
3. **Metadata**: raw source field/container names belong to the
   profile package via F8 `metadata_mapping`/`relation_mapping`;
   F5 holds only canonical parsed relation-classification
   vocabulary. The core consumes the canonical document contract
   (`titulo`/`fecha_publicacion`/`posteriores` kept as
   compatibility names for PORT-2 — renaming adds risk without
   benefit) and never sees a BOE XML tag.

Additional amendment (A4): C-034 refined — `index_threshold`
value is a calibrated profile parameter; the threshold *decision*
and mapping algorithm are core. Census C-034 amended accordingly.

A5: F8 registry invariants frozen above.

```text
PORT-1 = DONE
PORT-2 = AUTHORIZED
```

PORT-2 does not need to prove the core is agnostic to all possible
law — only that existing BdE semantics express as a restrictive
profile over a stable core contract without altering any fact. The
decisive test is C-016: one profile-owned `state_code_families`
grammar feeding `operations`, `annexmap`, `binding` and
`applicability_parser` with byte-identical semantic artifacts.
