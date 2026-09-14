"""G0-C.2 preregistered acceptance tests: runtime historical reconstruction.

The suite runs ``history.reconstruct`` for Circular 4/2017
(BOE-A-2017-14334) over an offline fetch backed exclusively by the captured
evidence manifests (g0c, g0c1, g0c2). No network, no OCR, no LLM.

Preregistered expectations (frozen before persistence implementation):

* modifier discovery: 8 posteriores = 7 MODIFICATION + 1 CORRECTION, each
  cross-checked by the modifier's own <anteriores>;
* C1 norma 33: TEXT -> TEXT, TEXT_DIFF_PROVEN;
* S1 FI 102-2: CORRECTION + declared deletion + visual predecessor;
* S2 FI 131-2.2: CORRECTION + declared addition + visual predecessor;
* S3 FI 142-1.1: chained IMAGE -> TABLE -> TABLE, hop2 TEXT_DIFF_PROVEN and
  hop2.before == hop1.after (same representation_id);
* S4 FI 105: IMAGE -> TABLE;
* S5 FI 100-14: IMAGE -> IMAGE;
* S6 FI 106-1.1: declared change over an image region;
* determinism: identical raw bytes + parser version -> identical ids, and a
  rerun inserts zero new logical rows;
* provenance: every representation and relation resolves to
  snapshot -> blob -> sha256;
* IMAGE representations never carry text_content;
* UNANCHORED_DERIVED bindings are not silently promoted;
* CORRECTION is not MODIFICATION; a correction without an applicability
  date has instrument_effective_date NULL;
* no applicability clauses are produced.

G0-C.2R additions (provenance + resolution semantics):

* a fetch marked LIVE_FETCH records a source_checks row for every runtime
  source; two live fetches of the same bytes -> +0 blobs, +0 snapshots,
  +2 checks;
* a fetch marked EVIDENCE_IMPORT never fabricates a check;
* resolution is operation-aware: ADD needs the after side, DELETE the
  before side, SUBSTITUTE both, MODIFY both or declared literals;
  PARTIAL means required evidence is actually missing;
* reconstruction anomalies persist to the anomalies table, idempotently,
  with resolvable snapshot/relation references.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from regdelta import db as dbm, history, operations  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402
from regdelta.http import (  # noqa: E402
    EVIDENCE_IMPORT, LIVE_FETCH, FetchResult)

TARGET = "BOE-A-2017-14334"
MANIFESTS = [
    ROOT / "evidence" / "g0c" / "raw" / "manifest.json",
    ROOT / "evidence" / "g0c1" / "raw" / "manifest.json",
    ROOT / "evidence" / "g0c2" / "raw" / "manifest.json",
]

pytestmark = pytest.mark.skipif(
    not all(m.exists() for m in MANIFESTS),
    reason="G0-C.2 evidence not generated (run scripts/g0c2/capture.py)",
)


def _evidence_fetch(url: str, accept: str) -> FetchResult:
    entry = _BY_URL.get(url)
    if entry is None:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in captured evidence",
                           via=EVIDENCE_IMPORT)
    data = (ROOT / entry["path"]).read_bytes()
    return FetchResult(url, 200, "application/octet-stream", data, None,
                       None, via=EVIDENCE_IMPORT)


def _live_fetch(url: str, accept: str) -> FetchResult:
    """Same captured bytes, but declared as a live HTTP observation: this
    is how production fetches behave, and it must produce source_checks."""
    entry = _BY_URL.get(url)
    if entry is None:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in captured evidence")
    data = (ROOT / entry["path"]).read_bytes()
    return FetchResult(url, 200, "application/octet-stream", data, None,
                       None, via=LIVE_FETCH)


_BY_URL: dict[str, dict] = {}
if all(m.exists() for m in MANIFESTS):
    for mp in MANIFESTS:
        m = json.loads(mp.read_text(encoding="utf-8"))
        for e in m["entries"].values():
            _BY_URL[e["url"]] = e


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("g0c2")
    conn = dbm.connect(data_dir / "regdelta.sqlite")
    conn.row_factory = sqlite3.Row
    report = history.reconstruct(conn, data_dir, TARGET, _evidence_fetch)
    conn.commit()
    yield conn, report
    conn.close()


def _rels(conn, locator_key):
    return conn.execute(
        """SELECT m.*, s.locator_key AS key, i.boe_id AS modifier_boe,
                  rb.representation_kind AS bkind,
                  ra.representation_kind AS akind
           FROM modification_relations m
           JOIN subjects s ON s.subject_id = m.target_subject_id
           JOIN instruments i ON i.instrument_id = m.modifier_instrument_id
           LEFT JOIN representations rb
                  ON rb.representation_id = m.before_representation_id
           LEFT JOIN representations ra
                  ON ra.representation_id = m.after_representation_id
           WHERE s.locator_key = ?
           ORDER BY m.publication_date""",
        (locator_key,),
    ).fetchall()


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_modifier_discovery(built):
    conn, report = built
    post = conn.execute(
        """SELECT other_boe_id, palabra FROM instrument_relations
           WHERE direction='POSTERIOR' AND declaring_instrument_id=
             (SELECT instrument_id FROM instruments WHERE boe_id=?)""",
        (TARGET,)).fetchall()
    assert len(post) == 8
    mods = [p for p in post if "MODIFICA" in p[1].upper()]
    corr = [p for p in post if "CORREC" in p[1].upper()]
    assert len(mods) == 7 and len(corr) == 1


def test_modifier_cross_check(built):
    conn, _ = built
    # every modifier's own <anteriores> names the target back
    rows = conn.execute(
        """SELECT DISTINCT i.boe_id FROM instrument_relations r
           JOIN instruments i ON i.instrument_id=r.declaring_instrument_id
           WHERE r.direction='ANTERIOR' AND r.other_boe_id=?""",
        (TARGET,)).fetchall()
    cross_checked = {r[0] for r in rows}
    assert len(cross_checked) == 8


# ---------------------------------------------------------------------------
# acceptance cases
# ---------------------------------------------------------------------------


def test_c1_norma33_text_to_text(built):
    conn, _ = built
    rels = [r for r in _rels(conn, "norma:33")
            if r["modifier_boe"] == "BOE-A-2018-17880"]
    assert len(rels) == 1
    r = rels[0]
    assert r["bkind"] == "TEXT" and r["akind"] == "TEXT"
    assert "TEXT_DIFF_PROVEN" in json.loads(r["diff_levels"])
    assert r["resolution"] == "RESOLVED"
    before, after = conn.execute(
        "SELECT text_content FROM representations WHERE representation_id=?",
        (r["before_representation_id"],)).fetchone()[0], conn.execute(
        "SELECT text_content FROM representations WHERE representation_id=?",
        (r["after_representation_id"],)).fetchone()[0]
    assert before != after and "33" in before[:20]


def test_s1_correction_visual_predecessor(built):
    conn, _ = built
    rels = [r for r in _rels(conn, "estado:FI 102-2")
            if r["modifier_boe"] == "BOE-A-2018-2041"]
    assert rels and all(r["kind"] == "CORRECTION" for r in rels)
    r = rels[0]
    assert r["bkind"] == "IMAGE"
    assert r["after_representation_id"] is None
    levels = json.loads(r["diff_levels"])
    assert "DECLARED_CHANGE_PROVEN" in levels
    assert "VISUAL_PREDECESSOR_PROVEN" in levels


def test_s2_declared_text_visual_predecessor(built):
    # G1_INTENTIONAL_SEMANTIC_CHANGE (G1.1 §15.1):
    #   old expected: bkind == 'IMAGE' — the pre-binder runtime bound
    #     the target annex's image as the ADD's 'before'.
    #   why not provable: an ADD has no pre-existing subject; the annex
    #     page image is surrounding context, not a representation of
    #     the subject being added. G1 §15.1 mandates before =
    #     NOT_APPLICABLE for ADD, so VISUAL_PREDECESSOR_PROVEN is no
    #     longer emitted here.
    #   new fail-closed behavior: before abstains (NULL, proof
    #     NOT_APPLICABLE); the declared addition is proven by the
    #     operation-owned after representation instead.
    conn, _ = built
    rels = [r for r in _rels(conn, "estado:FI 131-2.2")
            if r["modifier_boe"] == "BOE-A-2018-2041"]
    assert rels
    r = rels[0]
    assert r["kind"] == "CORRECTION"
    assert r["operation_kind"] == "ADD"
    assert r["before_representation_id"] is None
    assert r["akind"] in ("TEXT", "TABLE")
    levels = json.loads(r["diff_levels"])
    assert "DECLARED_CHANGE_PROVEN" in levels or "TEXT_DIFF_PROVEN" \
        in levels or "SEMANTIC_DIFF_NOT_AVAILABLE" in levels


def test_s3_chained_image_table_table(built):
    conn, _ = built
    rels = _rels(conn, "estado:FI 142-1.1")
    assert len(rels) == 2
    hop1, hop2 = rels
    assert hop1["bkind"] == "IMAGE" and hop1["akind"] == "TABLE"
    assert hop2["bkind"] == "TABLE" and hop2["akind"] == "TABLE"
    assert "TEXT_DIFF_PROVEN" in json.loads(hop2["diff_levels"])
    assert (hop2["before_representation_id"]
            == hop1["after_representation_id"])


def test_s4_image_to_table(built):
    # G1_INTENTIONAL_SEMANTIC_CHANGE (G1.1 §27–28):
    #   old expected: before=IMAGE — the runtime bound the target
    #     annex's image for the SUBSTITUTE despite two earlier 'pasa a
    #     denominarse' renames of FI 105 in the same modifier.
    #   why not provable: those renames are proven operations whose new
    #     representations cannot be shown; per §28 the chain becomes
    #     UNKNOWN and the stale image must not be resurrected as the
    #     SUBSTITUTE's before.
    #   new fail-closed behavior: before abstains (NOT_PROVABLE,
    #     CHAIN_STATE); the after still binds the modifier annex table,
    #     so the relation is PARTIAL.
    conn, _ = built
    rels = [r for r in _rels(conn, "estado:FI 105")
            if r["operation_kind"] == "SUBSTITUTE"]
    assert len(rels) == 1
    r = rels[0]
    assert r["bkind"] is None and r["akind"] == "TABLE"
    proof = json.loads(r["binding_proof"])
    assert proof["before"]["status"] == "NOT_PROVABLE"
    assert proof["before"]["method"] == "CHAIN_STATE"
    assert r["resolution"] == "PARTIAL"


def test_s5_image_to_image(built):
    conn, _ = built
    rels = [r for r in _rels(conn, "estado:FI 100-14")
            if r["modifier_boe"] == "BOE-A-2020-6186"]
    assert rels
    r = rels[0]
    assert r["bkind"] == "IMAGE" and r["akind"] == "IMAGE"
    assert "VISUAL_PREDECESSOR_PROVEN" in json.loads(r["diff_levels"])


def test_s6_region_declared_change(built):
    conn, _ = built
    rels = [r for r in _rels(conn, "estado:FI 106-1.1")
            if r["modifier_boe"] == "BOE-A-2018-17880"]
    assert rels
    r = rels[0]
    assert r["bkind"] == "IMAGE"
    assert r["akind"] in ("TEXT", "TABLE")
    assert "nota" in r["locator_raw"].lower()


# ---------------------------------------------------------------------------
# determinism / provenance / invariants
# ---------------------------------------------------------------------------


def test_deterministic_rerun(built):
    conn, report = built
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("instruments", "subjects", "representations",
                  "instrument_relations", "modification_relations",
                  "source_blobs", "source_snapshots", "anomalies")
    }
    ids = {
        t: {r[0] for r in conn.execute(f"SELECT {c} FROM {t}")}
        for t, c in (("representations", "representation_id"),
                     ("modification_relations", "relation_id"),
                     ("subjects", "subject_id"))
    }
    data_dir = Path(conn.execute("PRAGMA database_list").fetchone()[2]).parent
    report2 = history.reconstruct(conn, data_dir, TARGET, _evidence_fetch)
    conn.commit()
    for t, n in counts.items():
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == n, t
    for t, c in (("representations", "representation_id"),
                 ("modification_relations", "relation_id"),
                 ("subjects", "subject_id")):
        assert {r[0] for r in conn.execute(f"SELECT {c} FROM {t}")} == ids[t]


def test_all_representations_resolve_to_blob(built):
    conn, _ = built
    rows = conn.execute(
        """SELECT r.representation_id FROM representations r
           LEFT JOIN source_snapshots s
                  ON s.snapshot_id = r.source_snapshot_id
           LEFT JOIN source_blobs b ON b.sha256 = s.blob_sha256
           WHERE s.snapshot_id IS NULL OR b.sha256 IS NULL""").fetchall()
    assert rows == []


def test_all_relations_resolve_to_snapshots(built):
    conn, _ = built
    for rid, snaps_json in conn.execute(
            "SELECT relation_id, source_snapshot_ids"
            " FROM modification_relations"):
        for snap in json.loads(snaps_json):
            row = conn.execute(
                """SELECT b.sha256 FROM source_snapshots s
                   JOIN source_blobs b ON b.sha256 = s.blob_sha256
                   WHERE s.snapshot_id=?""", (snap,)).fetchone()
            assert row is not None, rid


def test_image_reprs_have_no_text(built):
    conn, _ = built
    assert conn.execute(
        """SELECT COUNT(*) FROM representations
           WHERE representation_kind IN ('IMAGE','PDF_PAGE')
             AND text_content IS NOT NULL""").fetchone()[0] == 0


def test_unanchored_not_promoted(built):
    conn, _ = built
    # modifier annex images have no independent anchors: they must remain
    # UNANCHORED_DERIVED, never silently upgraded to ANCHORED_DERIVED
    rows = conn.execute(
        """SELECT binding, binding_evidence FROM representations
           WHERE representation_kind='IMAGE'""").fetchall()
    unanchored = [r for r in rows if r[0] == "UNANCHORED_DERIVED"]
    anchored = [r for r in rows if r[0] == "ANCHORED_DERIVED"]
    assert unanchored, "expected modifier-annex image representations"
    for _, ev in unanchored:
        assert json.loads(ev)["anchors"] == 0
    for _, ev in anchored:
        assert json.loads(ev)["anchors_matching"] > 0


def test_correction_is_not_modification(built):
    conn, _ = built
    rows = conn.execute(
        """SELECT m.kind, m.instrument_effective_date, i.fecha_vigencia
           FROM modification_relations m
           JOIN instruments i
             ON i.instrument_id = m.modifier_instrument_id
           WHERE i.boe_id='BOE-A-2018-2041'""").fetchall()
    assert rows and all(k == "CORRECTION" for k, _, _ in rows)
    # the correction instrument declares no applicability date -> NULL
    assert all(eff is None for _, eff, _ in rows)


def test_no_applicability_clauses(built):
    conn, _ = built
    # G0-D: the applicability tables exist in the schema, but reconstruct
    # alone never populates them — that is applicability.build's job
    for t in ("applicability_clauses", "applicability_effects",
              "applicability_targets"):
        assert conn.execute(
            f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
    # instrument_effective_date holds only the modifier's own general
    # entry-into-force date; it is never a granular applicability answer
    bad = conn.execute(
        """SELECT COUNT(*) FROM modification_relations m
           JOIN instruments i
             ON i.instrument_id = m.modifier_instrument_id
           WHERE m.instrument_effective_date IS NOT NULL
             AND m.instrument_effective_date != i.fecha_vigencia""").fetchone()[0]
    assert bad == 0


def test_anejo9_points_never_bind_to_original_images(built):
    conn, _ = built
    rows = conn.execute(
        """SELECT m.resolution, r.representation_kind, r.binding
           FROM modification_relations m
           JOIN subjects s ON s.subject_id = m.target_subject_id
           LEFT JOIN representations r
                  ON r.representation_id = m.before_representation_id
           WHERE s.locator_key LIKE 'anejo:9.punto:%'""").fetchall()
    assert rows
    # a before representation may only appear via the modification chain
    # (a DECLARED text/table repr from a previous modifier); the original
    # annex pages can never be resolved to sub-page point granularity
    for _res, kind, binding in rows:
        if kind is not None:
            assert kind in ("TEXT", "TABLE")
            assert binding == "DECLARED"


def test_report_summary(built):
    _, report = built
    assert report["target_annex_anchored"] is True
    assert report["anchors"] >= 10
    assert report["relations"] > 0
    assert report["fetch_errors"] == []


# ---------------------------------------------------------------------------
# G0-C.2R: blob != snapshot != check for every runtime source
# ---------------------------------------------------------------------------


def test_live_fetch_creates_source_checks(tmp_path):
    conn = dbm.connect(tmp_path / "r.sqlite")
    history.reconstruct(conn, tmp_path, TARGET, _live_fetch,
                        checked_at="2026-01-01T00:00:00Z")
    conn.commit()
    by_src = dict(conn.execute(
        "SELECT source_id, COUNT(*) FROM source_checks GROUP BY 1"))
    for src in ("boe_diario", "boe_doc", "boe_pdf", "boe_imagen"):
        assert by_src.get(src, 0) > 0, src
    # every non-error check points at an existing snapshot
    assert conn.execute(
        """SELECT COUNT(*) FROM source_checks c
           LEFT JOIN source_snapshots s ON s.snapshot_id = c.snapshot_id
           WHERE c.status != 'FETCH_ERROR' AND s.snapshot_id IS NULL"""
    ).fetchone()[0] == 0
    conn.close()


def test_same_bytes_two_live_fetches_two_checks(tmp_path):
    conn = dbm.connect(tmp_path / "r.sqlite")
    history.reconstruct(conn, tmp_path, TARGET, _live_fetch,
                        checked_at="2026-01-01T00:00:00Z")
    conn.commit()
    n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
         for t in ("source_blobs", "source_snapshots", "source_checks")}
    history.reconstruct(conn, tmp_path, TARGET, _live_fetch,
                        checked_at="2026-01-02T00:00:00Z")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM source_blobs").fetchone()[0] \
        == n["source_blobs"]
    assert conn.execute("SELECT COUNT(*) FROM source_snapshots"
                        ).fetchone()[0] == n["source_snapshots"]
    assert conn.execute("SELECT COUNT(*) FROM source_checks"
                        ).fetchone()[0] == 2 * n["source_checks"]
    conn.close()


def test_evidence_import_fabricates_no_checks(built):
    conn, _ = built
    assert conn.execute(
        "SELECT COUNT(*) FROM source_checks").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# G0-C.2R: resolution is operation-aware
# ---------------------------------------------------------------------------


def _required_met(op_kind, before_id, after_id, literals):
    has_lit = bool(literals)
    if op_kind == "ADD":
        return after_id is not None
    if op_kind == "DELETE":
        return before_id is not None
    if op_kind == "SUBSTITUTE":
        return before_id is not None and after_id is not None
    return before_id is not None and (after_id is not None or has_lit)


def test_add_with_proven_after_is_resolved(built):
    conn, _ = built
    rows = conn.execute(
        """SELECT COUNT(*) FROM modification_relations
           WHERE operation_kind='ADD' AND after_representation_id IS NOT NULL
             AND resolution != 'RESOLVED'""").fetchone()[0]
    assert rows == 0


def test_delete_with_proven_before_is_resolved(built):
    conn, _ = built
    rows = conn.execute(
        """SELECT COUNT(*) FROM modification_relations
           WHERE operation_kind='DELETE'
             AND before_representation_id IS NOT NULL
             AND resolution != 'RESOLVED'""").fetchone()[0]
    assert rows == 0


def test_substitute_missing_side_not_resolved(built):
    conn, _ = built
    rows = conn.execute(
        """SELECT COUNT(*) FROM modification_relations
           WHERE operation_kind='SUBSTITUTE' AND resolution='RESOLVED'
             AND (before_representation_id IS NULL
                  OR after_representation_id IS NULL)""").fetchone()[0]
    assert rows == 0


def test_partial_means_required_evidence_missing(built):
    conn, _ = built
    for r in conn.execute(
            """SELECT operation_kind, before_representation_id,
                      after_representation_id, declared_literals, resolution,
                      resolution_notes
               FROM modification_relations"""):
        req = _required_met(r[0], r[1], r[2], json.loads(r[3] or "null"))
        assert (r[4] == "RESOLVED") == req, tuple(r)
        if r[4] == "PARTIAL":
            # some evidence exists but a required side is missing
            assert r[1] is not None or r[2] is not None or r[3] is not None
        if r[4] != "RESOLVED":
            # G1: notes name the abstention status instead of the bare
            # word 'missing' (NOT_FOUND/AMBIGUOUS/NOT_PROVABLE)
            assert r[5] is not None and any(
                tok in r[5] for tok in
                ("NOT_FOUND", "AMBIGUOUS", "NOT_PROVABLE",
                 "literals_only"))


def test_legitimate_absence_not_partial(built):
    conn, _ = built
    # an ADD whose before is NULL by definition is not 'incomplete'
    rows = conn.execute(
        """SELECT resolution FROM modification_relations
           WHERE operation_kind='ADD'
             AND before_representation_id IS NULL
             AND after_representation_id IS NOT NULL""").fetchall()
    assert rows and all(r[0] == "RESOLVED" for r in rows)


# ---------------------------------------------------------------------------
# G0-C.2R: anomalies persist
# ---------------------------------------------------------------------------


def test_anomalies_persisted(built):
    conn, report = built
    n = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    assert n > 0
    assert n == len(report["anomalies"])
    kinds = dict(conn.execute(
        "SELECT kind, COUNT(*) FROM anomalies GROUP BY 1"))
    assert kinds  # distribution is reported, not empty


def test_anomaly_persistence_idempotent(built):
    conn, _ = built
    n0 = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    data_dir = Path(conn.execute("PRAGMA database_list").fetchone()[2]).parent
    history.reconstruct(conn, data_dir, TARGET, _evidence_fetch)
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM anomalies"
                        ).fetchone()[0] == n0


def test_anomaly_refs_resolve(built):
    conn, _ = built
    for aid, snap, detail in conn.execute(
            "SELECT anomaly_id, snapshot_id, detail FROM anomalies"):
        if snap is not None:
            assert conn.execute(
                "SELECT 1 FROM source_snapshots WHERE snapshot_id=?",
                (snap,)).fetchone() is not None, aid
        d = json.loads(detail)
        if "relation_id" in d:
            assert conn.execute(
                "SELECT 1 FROM modification_relations WHERE relation_id=?",
                (d["relation_id"],)).fetchone() is not None, aid


# ---------------------------------------------------------------------------
# G0-C.2R2: blockquote-wrapped locators + explicit numeric range expansion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clause,norma,expected", [
    ("Se modifican los apartados 17 a 20, que quedan redactados "
     "en los siguientes términos:", "22",
     {"norma:22.apartado:17", "norma:22.apartado:18",
      "norma:22.apartado:19", "norma:22.apartado:20"}),
    ("Se modifican los apartados 3, 6 y 7, que quedan redactados "
     "en los siguientes términos:", "31",
     {"norma:31.apartado:3", "norma:31.apartado:6",
      "norma:31.apartado:7"}),
    ("Se modifican los apartados 13, 18 y 19, que quedan redactados "
     "en los siguientes términos:", "22",
     {"norma:22.apartado:13", "norma:22.apartado:18",
      "norma:22.apartado:19"}),
])
def test_apartado_numlist_expansion(clause, norma, expected):
    """Explicit numeric enumerations expand to individual locators:
    '17 a 20' is a range, '3, 6 y 7' / '13, 18 y 19' are lists."""
    mentions = operations._extract_mentions(clause)
    keys = {s.locator_key for s in
            operations._compose_keys(mentions, {"norma": norma})}
    assert keys == expected


def test_blockquote_locator_materializes():
    """A marker+amend-verb clause wrapped in a <blockquote> node is still
    an operation: the locator clause is preserved and the quoted remainder
    stays available as inline content — not silently dropped."""
    nodes = [
        boe_diario.Node(0, "p", "articulo",
                        "Artículo único. Modificación de la Circular "
                        "4/2017, de 27 de noviembre."),
        boe_diario.Node(1, "p", "parrafo",
                        "a) En la norma 31, «Coberturas contables», "
                        "se realizan las siguientes modificaciones:"),
        boe_diario.Node(2, "blockquote", "sangrado",
                        "i) Se modifica el apartado 3, que queda "
                        "redactado en los siguientes términos: "
                        "«3. Únicamente podrán ser designados como "
                        "instrumentos de cobertura.»"),
        boe_diario.Node(3, "p", "parrafo",
                        "ii) Se modifican los apartados 6 y 7, que "
                        "quedan redactados en los siguientes términos:"),
        boe_diario.Node(4, "blockquote", "sangrado",
                        "«6. Podrán ser designados como partidas "
                        "cubiertas los activos.»"),
    ]
    doc = boe_diario.DiarioDoc(nodes=nodes)
    ops = operations.parse_operations(doc, (4, 2017)).operations
    leaf = {s.locator_key: o for o in ops if not o.is_container
            for s in o.subjects}
    op3 = leaf.get("norma:31.apartado:3")
    assert op3 is not None
    assert "«" not in op3.clause_text
    assert op3.inline_content.startswith("«")
    assert {"norma:31.apartado:6", "norma:31.apartado:7"} <= set(leaf)
    # the pure-content blockquote is not an operation
    assert all("Podrán" not in o.clause_text for o in ops)


def test_r2_repaired_locators_have_relations(built):
    """The G0-D audit targets materialize as real relations."""
    conn, _ = built
    for key in ("norma:31.apartado:3",
                "norma:22.apartado:17", "norma:22.apartado:18",
                "norma:22.apartado:19", "norma:22.apartado:20"):
        rels = [r for r in _rels(conn, key)
                if r["modifier_boe"] == "BOE-A-2025-26847"]
        assert rels, key
