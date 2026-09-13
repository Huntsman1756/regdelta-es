# G0-C.2 — Runtime historical reconstruction (Circular 4/2017)

Status: **mechanism PROVEN on the preregistered corpus** — the pipeline
converts the G0-C/G0-C.1 discovery into deterministic, auditable runtime
code inside `src/regdelta`. This is not a validated exhaustive backfill:
coverage numbers below measure what the parsed corpus produced, nothing
more.

## 1. What runs

```text
BOE-A-2017-14334 diario XML
  -> instrument + <posteriores> -> 8 modifiers (7 SE MODIFICA + 1 CORRECCIÓN)
  -> each modifier XML -> operations (scoped to the "Circular 4/2017" section)
  -> target doc.php image inventory + diario PDF embedded text layer
  -> annex map (anchored by the correction's own page+estado citations)
  -> subjects / representations / modification_relations
```

Modules: `sources/boe_diario.py` (ordered nodes), `sources/boe_doc.py`
(image inventory), `sources/boe_pdf.py` (`/Pages`-order embedded text),
`operations.py` (nested locator + verb parsing), `annexmap.py`
(page/state/image binding), `history.py` (orchestration + persistence),
`evidence_import.py` (manifest -> rawstore + snapshots).

## 2. Run on the real corpus (offline evidence)

* modifiers discovered: **8** — `SE MODIFICA` ×7, `CORRECCIÓN de errores` ×1
* cross-check: all 8 declare `BOE-A-2017-14334` in their own `<anteriores>`
* target annex map: **anchored** — 19/19 correction citations match
* relations persisted: **278** (259 MODIFICATION + 19 CORRECTION)
  * RESOLVED 167 / PARTIAL 91 / UNRESOLVED 20
* representations: **315**
  * TEXT×215, TABLE×16, IMAGE×84 (ANCHORED_DERIVED 78 / UNANCHORED_DERIVED 6)
* subjects: 207; instruments: 20 (9 PARSED + 11 REFERENCED);
  instrument_relations: 30
* fetch errors: 0

## 3. Preregistered cases — all reconstructed

| case | relation | result |
|---|---|---|
| C1 | norma:33 ← 2018-17880 SUBSTITUTE | TEXT→TEXT, TEXT_DIFF_PROVEN, RESOLVED |
| S1 | estado:FI 102-2 ← 2018-2041 CORRECTION DELETE | IMAGE→∅, DECLARED+VISUAL_PREDECESSOR |
| S2 | estado:FI 131-2.2 ← 2018-2041 CORRECTION ADD | IMAGE→TEXT, VISUAL_PREDECESSOR |
| S3 | estado:FI 142-1.1 ← 2018-17880 then 2025-26847 | IMAGE→TABLE→TABLE; hop2 TEXT_DIFF_PROVEN; hop2.before == hop1.after |
| S4 | estado:FI 105 ← 2025-26847 SUBSTITUTE | IMAGE→TABLE |
| S5 | estado:FI 100-14 ← 2020-6186 SUBSTITUTE | IMAGE→IMAGE (modifier annex is itself images) |
| S6 | estado:FI 106-1.1 ← 2018-17880 MODIFY (nota a) | IMAGE→TEXT, VISUAL_PREDECESSOR |

## 4. Invariants verified by `tests/g0c2/test_history.py` (18 tests)

* deterministic rerun: identical ids, zero new logical rows;
* every representation joins to `source_snapshots → source_blobs → sha256`;
* every relation's `source_snapshot_ids` resolve to snapshot+blob;
* `IMAGE`/`PDF_PAGE` never carry `text_content` (schema CHECK + test);
* `UNANCHORED_DERIVED` modifier-annex images are never promoted;
* `CORRECTION` relations never carry `effective_date` (no applicability
  invented); every non-NULL `effective_date` equals the modifier's own
  `fecha_vigencia`;
* `anejo:9.punto:*` before-representations can only come from the
  modification chain (DECLARED TEXT/TABLE of a previous modifier), never
  from the original image pages (sub-page granularity is not boundable);
* all 19 correction anchors match (ANCHORED_DERIVED stays earned).

## 5. Evidence added

`raw/` = 194 artifacts (~48 MB): the annex page images the parsed
operations actually bind (computed set, not a manual list), plus the
2025-26847 diario PDF needed for its annex map. `manifest.json` records
url + sha256 + retrieved_at; `evidence_import.import_manifest` reproduces
identical snapshot ids offline.

## 6. Honest limits

* UNRESOLVED×20: mostly `anejo:9.punto:*` deletes/modifies with no
  sub-page binding, and a few ops on subjects already deleted upstream
  (chain end) — recorded, not guessed.
* PARTIAL×91: one side bound (e.g. declared literal change with no
  after-artifact, or new-state adds whose before is legitimately absent).
* C.2/2018 partial early effectiveness (2018-12-31 for some operations)
  is stored only at instrument level (`fecha_vigencia`); per-operation
  exceptions belong to G0-D.
* `binding_evidence` records the mechanism + anchor counts, not a proof
  object per row.
* 26 anomalies were recorded during the run (OUT_OF_TARGET_OPS counts on
  sections targeting other instruments, UNBOUND_SUBJECT, ANNEX_REFERENCE
  misses). They are returned in the report dict, not persisted to the
  `anomalies` table — a deliberate minimal choice; persistence of the
  anomaly rows is the obvious next refinement.

## 7. Reproduce

```text
python -m pytest tests/g0c2/test_history.py        # offline, 18 tests
python scripts/g0c2/capture.py                     # live fetch, rebuilds
                                                   # evidence/g0c2/raw
```

G0-A and G0-B remain frozen at `fb0dc67`; this phase only extends the
schema (`+5` tables, `source_id` CHECK widened via in-place rebuild) and
adds modules — no G0-A/B behavior changed.
