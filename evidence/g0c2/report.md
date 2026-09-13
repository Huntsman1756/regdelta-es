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
  * RESOLVED 168 / PARTIAL 93 / UNRESOLVED 17
    (operation-aware `resolution`, see §4a)
* representations: **315**
  * TEXT×215, TABLE×16, IMAGE×84 (ANCHORED_DERIVED 78 / UNANCHORED_DERIVED 6)
* subjects: 207; instruments: 20 (9 PARSED + 11 REFERENCED);
  instrument_relations: 30
* fetch errors: 0; anomalies persisted: 23 (see §6)

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

## 4a. G0-C.2R remediation

Three review findings fixed before formal freeze:

* **blob ≠ snapshot ≠ check restored for all runtime sources.**
  `source_checks.source_id` now admits `boe_diario`, `boe_doc`, `boe_pdf`,
  `boe_imagen` (in-place CHECK rebuild preserving rows). `FetchResult.via`
  distinguishes `LIVE_FETCH` from `EVIDENCE_IMPORT`; only a live fetch
  records a check. One live run over the corpus: 224 checks
  (`boe_diario`×9, `boe_doc`×2, `boe_pdf`×2, `boe_imagen`×211) = 224
  snapshots = 224 blobs; a second live run adds 224 more checks and zero
  new blobs/snapshots. A fixed transaction bug in the shipped
  `_ensure_source_ids` migration (`executescript` implicitly commits) was
  found and repaired while adding the `source_checks` rebuild.
* **`resolution` is operation-aware.** Required evidence: ADD → after;
  DELETE → before; SUBSTITUTE → before+after; MODIFY/CORRECT → before +
  (after or declared literals). New distribution vs. the naive rule
  (167/91/20): RESOLVED **168** / PARTIAL **93** / UNRESOLVED **17**.
  ADDs with a proven after and legitimately-NULL before moved to RESOLVED;
  DELETEs with only declared literals moved UNRESOLVED→PARTIAL (evidence
  exists but the required predecessor does not); SUBSTITUTEs supported
  only by declared literals moved RESOLVED→PARTIAL — the strict contract
  holds. `resolution_notes` names the missing required side.
* **Anomalies persist.** Every anomaly now carries `snapshot_id` when one
  exists plus `detail` with modifier/subject/operation_kind/relation_id
  where available; deterministic `anomaly_id` makes persistence
  idempotent. Reconstruction anomalies do not set snapshot
  `has_anomalies` (that flag marks source-parse anomalies only).

## 4. Invariants verified by `tests/g0c2/test_history.py` (29 tests)

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
* all 19 correction anchors match (ANCHORED_DERIVED stays earned);
* live fetches produce `source_checks`; evidence imports produce none;
* RESOLVED ⟺ the operation's required evidence is present; non-RESOLVED
  rows carry `resolution_notes` naming the missing side;
* anomalies persist across process completion and reruns insert zero.

## 5. Evidence added

`raw/` = 194 artifacts (~48 MB): the annex page images the parsed
operations actually bind (computed set, not a manual list), plus the
2025-26847 diario PDF needed for its annex map. `manifest.json` records
url + sha256 + retrieved_at; `evidence_import.import_manifest` reproduces
identical snapshot ids offline.

## 6. Honest limits

* UNRESOLVED×17: mostly `anejo:9.punto:*` deletes/modifies with no
  sub-page binding, and a few ops on subjects already deleted upstream
  (chain end) — recorded, not guessed.
* PARTIAL×93: a required side is genuinely missing (e.g. declared literal
  change with no after-artifact, or an unbound predecessor). Each row's
  `resolution_notes` says which.
* C.2/2018 partial early effectiveness (2018-12-31 for some operations)
  is stored only at instrument level (`fecha_vigencia`); per-operation
  exceptions belong to G0-D.
* `binding_evidence` records the mechanism + anchor counts, not a proof
  object per row.
* 23 anomalies persisted (UNBOUND_SUBJECT×17, OUT_OF_TARGET_OPS×3,
  ANNEX_REFERENCE_UNRESOLVED×3) with snapshot/relation linkage where
  available.

## 7. Reproduce

```text
python -m pytest tests/g0c2/test_history.py        # offline, 29 tests
python scripts/g0c2/capture.py                     # live fetch, rebuilds
                                                   # evidence/g0c2/raw
```

G0-A and G0-B remain frozen at `fb0dc67`; this phase only extends the
schema (`+5` tables, `source_id` CHECK widened via in-place rebuild on
both `source_snapshots` and `source_checks`) and adds modules — no
G0-A/B behavior changed.
