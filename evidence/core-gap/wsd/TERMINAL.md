# CORE-GAP — WS-D terminal evidence: image / representation evidence

**Terminal: `REPRESENTATION_ASSOCIATION_ONLY`.**

The preregistered EXP-D1 experiment falsified byte equality between
the authentic signed PDF and the served `/datos/imagenes/disp` PNG
assets: the signed PDF embeds the annex figures as **vector content**,
not as raster streams — there is nothing byte-comparable inside the
PDF. The deterministic association between the authentic document and
the served asset is provable and is now recorded explicitly as binding
evidence. No byte identity is claimed between channels.

## EXP-D1 — pypdf byte-equality experiment

Ledger: `evidence/core-gap/wsd/exp-d1/run{1,2}/exp-d1-ledger.json`
(two fresh runs, byte-identical ledgers).

| field | value |
|---|---|
| source PDF | `boe_dias_pdf__BOE-A-2017-14334.pdf` |
| pdf sha256 | `0923cc0a16241a23e7d4237443d29fdf14a8dce37818c4c00278ab00b14bf16e` |
| size / pages | 39,355,759 B / 588 pages (whole-issue PDF served at the doc URL) |
| library | pypdf 6.14.2 (raw object access; no decode-for-evidence, no rasterization, no OCR) |
| `/Image` XObjects | 2 unique (refs 68/69, shared header logos, `/CCITTFaxDecode`) |
| image XObjects on annex pages | 0 |
| inline `BI…ID…EI` images | 0 |
| official PNG assets | 204 captured (326 declared identically by XML and doc.php) |
| raw-stream byte matches | **0** |
| decoded-derivative matches | **0** |
| masks / transforms | none present (no `/SMask`); moot — no streams to match |
| page ordering | stable; diario index ↔ printed `Pág. N` mapping extracted for all 588 pages |

Outcome per the preregistered vocabulary:
`REPRESENTATION_ASSOCIATION_ONLY` — deterministic page/object/asset
association provable; byte-faithful binding impossible because the
publisher does not embed the asset bytes in the signed PDF.

## Avenues exhausted

| avenue | result |
|---|---|
| BOE diario XML `<img>` refs | declares the same 326 `/datos/imagenes/disp` URLs as doc.php — independent official corroboration of the served-asset channel (implemented: `boe_diario` `img` nodes) |
| doc.php `alt="N"` strip | page↔asset ordering (implemented: `boe_doc.parse_doc_images` → `annexmap.img_by_page`) |
| signed PDF `/Image` streams | **falsified** — figures are vector content (EXP-D1) |
| page/object mapping | diario index ↔ boe page ↔ img_alt ↔ PNG url+sha256 — deterministic, recorded |
| metadata URLs | API exposes `url_pdf`/`url_html` only; no image URLs (recon) |
| ePUB image bundle | `OFFICIAL_BYTES_UNAVAILABLE` — documented endpoint, not part of the frozen corpus; not fetched (frozen evidence discipline) |

## Implementation (as shipped)

`history._image_representation` now records `pdf_anchor` inside
`binding_evidence` for every IMAGE representation:

```json
"pdf_anchor": {
  "sha256": "<blob sha256 of the signed diario PDF>",
  "page_indexes": [<diario /Pages index per bound boe_page>],
  "relation": "ASSOCIATION_ONLY"
}
```

Semantics: corroborating evidence of a deterministic association —
the IMAGE locator identity (`boe_page`, `img_alt`, `url`,
`blob_sha256`) and `representation_id` are unchanged, so the workstream
introduces **zero ledger deltas**. The PNG bytes remain the factual
representation evidence (official informative-grade, declared by two
independent official channels); the signed-PDF anchor closes the
provenance loop to the authentic document without claiming byte
equality.

## Dependency decision

**pypdf NOT adopted.** The preregistered positive-gain condition
(≥1 byte-equal stream) did not hold; ObjStm/XObject access adds no
provable evidence for this corpus. Stdlib `boe_pdf` remains the only
PDF parser. No new dependency enters the project.

## Coverage vs prereg terminals

| case | terminal |
|---|---|
| `EXACT_OFFICIAL_ASSET_MATCH` | falsified — no embedded raster streams exist |
| `EXACT_EMBEDDED_STREAM_MATCH` | falsified — same reason |
| `DETERMINISTIC_DERIVATIVE_ONLY` | not reached — decoded streams recorded but matching is moot |
| `REPRESENTATION_ASSOCIATION_ONLY` | **reached — terminal** |
| `OFFICIAL_BYTES_UNAVAILABLE` | sub-result for the ePUB avenue only |
| `NO_DETERMINISTIC_BINDING` | not reached — association is deterministic |

## Test evidence

```text
tests/coregap/test_ws_d_representation.py  3 passed
tests/coregap/ (all)                       65 passed
```

## Invariants

```text
FALSE_FACT                = 0
FALSE_BINDING             = 0  (no byte-equality claim between channels;
                                PNG remains informative-grade evidence)
FALSE_LOCATOR_DECLARATION = 0
FALSE_CONTINUITY          = 0
unexpected deltas         = 0  (binding_evidence-only change;
                                representation ids unchanged)
holdout                   sealed
no OCR / no rasterization as identity evidence / no LLM-vision fallback
```
