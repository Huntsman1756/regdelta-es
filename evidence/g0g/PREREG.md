# G0-G — Multi-instrument Generalization & Holdout (Preregistration)

Base HEAD at freeze: `ef58530f5ba8787879ab897fecfc2dd9c424ce69`

## Preregistered question

> ¿Funciona RegDelta fuera de Circular 4/2017 sin reglas específicas
> por BOE-ID, número de circular, código de estado o página?

This question is fixed here. No later result may redefine it.

## Candidate pool

Enumerated mechanically from the official Banco de España chronological
circular index (captured, hashed — `evidence/g0g/raw/`):

- 85 index entries
- eligibility: diario XML fetches + `<analisis><posteriores>` contains
  at least one explicit MODIFICA/CORRECCIÓN-family relation
- seen-set exclusion: `evidence/g0g/seen-set.json` — every BdE circular
  whose normative content was already captured under `evidence/**` or
  `tests/fixtures/**` before G0-G.0 (9 BOE ids, the C4/2017 corpus).
  A mere textual reference to a norm does not exclude it.
- result: 32 eligible candidates → `evidence/g0g/candidates.json`

## Stratification (two orthogonal dimensions, four cells)

Classification uses only structural properties captured before reading
normative content.

- **R (representation profile)**: `VISUAL` iff the diario XML contains
  ≥1 `<img src="/datos/imagenes/...">` node; else `TEXT`.
- **C (consolidated availability)**: `CONSOLIDATED` iff
  `datosabiertos/api/legislacion-consolidada/id/{boe}/metadatos`
  returns HTTP 200; `NON_CONSOLIDATED` on documented 404.

## Selection (fixed, zero human choice)

12 targets, 3 per cell. Rank = lexicographic ascending
`sha256("regdelta-g0g-v1|" + boe_id)`; rank 1–2 → `GENERALIZATION_DEV`,
rank 3 → `SEALED_HOLDOUT`. Frozen in `evidence/g0g/selection.json`.

| cell | DEV | HOLDOUT |
|---|---|---|
| TEXT×CONSOLIDATED | BOE-A-2019-17286 (C 4/2019), BOE-A-2005-4749 (C 2/2005) | BOE-A-2013-5720 (C 1/2013) |
| TEXT×NON_CONSOLIDATED | BOE-A-2011-2378 (C 1/2011), BOE-A-2013-7467 (C 2/2013) | BOE-A-2021-19805 (C 4/2021) |
| VISUAL×CONSOLIDATED | BOE-A-2010-1824 (C 1/2010), BOE-A-2010-12488 (C 4/2010) | BOE-A-2016-1238 (C 2/2016) |
| VISUAL×NON_CONSOLIDATED | BOE-A-2012-3169 (C 2/2012), BOE-A-2016-4356 (C 4/2016) | BOE-A-2021-21220 (C 5/2021) |

Had any cell yielded <3 eligible candidates, the gate was to STOP —
no shrinking, merging, or manual substitution.

## Holdout seal

`evidence/g0g/holdout/` contains the complete mechanical capture set
(target + declared modifiers: diario XML, txt/doc HTML, PDF,
consolidada endpoints, all enumerable `<img>` artifacts). The capture
is content-agnostic: `scripts/g0g/capture.py` enumerates artifacts only
from official markup; it never invokes `history.reconstruct`,
`operations.parse_operations`, `applicability.build`, or any query.

`holdout/SEAL` commits: target ids, `manifest_sha256`,
`artifact_count`, `aggregate_bytes`, `aggregate_sha256`,
`capture_script_sha256`, base HEAD.

Whitelist: only this document, the SEAL verifier
(`tests/g0g/test_holdout_sealed.py`), and the future G0-G.2 evaluator
may reference the holdout evidence directory. G0-G.1 must not open or
parse holdout manifests/artifacts.

## Declared-modifier gold

`evidence/g0g/gold/declared_modifiers.json` — produced by an
independent extractor (`capture.py::declared_modifiers`, direct
ElementTree over `<posteriores>`), frozen before the first run. Every
declared modifier is reverse-checked: the modifier's own `<anteriores>`
must reference the target (all 12 targets: 100 % reverse-confirmed).

## Metrics (frozen in protocol.md)

`declared_modifier_recall`, `operation_parsing_rate`,
`subject_locator_resolution`, `representation_binding`,
`chain_reconstruction`, `applicability_extraction` (only where the
norm declares its own DFU/DT), `query_execution`,
`false_positive_facts`, `source_limitations`.

`declared_modifier_recall` measures agreement with explicit BOE
relationships; it is **not** proof of complete legal amendment recall.

## Hard gates

```text
FALSE_FACT_COUNT = 0   per holdout target — no averaging across targets
PARTIAL/UNRESOLVED honest — preferred over a wrong binding
```

## Fix-admission rule (G0-G.1)

REJECTED: any fix introducing a new BOE id, circular number, estado
code, concrete locator_key, or concrete BOE page into `src/regdelta`.
PERMITTED: such literals only under `tests/**` / `evidence/**`.
Mechanical guard: `tests/g0g/test_no_target_specific_code.py` enforces
`current_literals − baseline_literals = ∅` against
`evidence/g0g/runtime-literals-baseline.json` (11 pre-existing literals
in `annexmap.py`, `history.py`, `operations.py` are baseline-absorbed).

Every G0-G.1 fix is logged in `evidence/g0g/fixes.jsonl` with
`failure_class`, `root_cause`, `generic_rule` (verifiable without
naming the target), `files_changed`, `targets_fixed`,
`targets_regressed`.

## Failure taxonomy (closed)

`SOURCE_LIMITATION` — only when inspection of the captured official
source proves the needed datum is not explicitly present.
`ACQUISITION_FAILURE` — a needed artifact could not be fetched/parsed
into evidence. `PARSER_FAILURE` — present datum not parsed.
`SCHEMA_FAILURE` — parsed datum cannot be persisted in the frozen
schema. `EVALUATION_FAILURE` — persisted datum not correctly surfaced
by the query layer. Every classification keeps an evidence
locator/quote. A datum present in the source but missed by RegDelta is
never `SOURCE_LIMITATION`.

## Audit (protocol.md §Audit)

HOLDOUT: 100 % of emitted `modification_relations` — including PARTIAL
and UNRESOLVED — audited against the factual claims they actually emit
(modifier identity, operation_kind, target locator, before/after
bindings, resolution). UNRESOLVED is not a failure; a false positive
claim is. Doubtful → FALSE_FACT (conservative).

## Scope of G0-G.0

Zero changes under `src/regdelta/`. Guards live exclusively in
`tests/g0g/`. No schema changes. No CNMV/EUR-Lex/LLM/OCR/frontend.
G0-A–F stay frozen.
