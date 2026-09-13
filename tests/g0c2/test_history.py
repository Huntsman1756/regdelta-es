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
  date has effective_date NULL;
* no applicability clauses are produced.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from regdelta import db as dbm, history  # noqa: E402
from regdelta.http import FetchResult  # noqa: E402

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
                           "url not in captured evidence")
    data = (ROOT / entry["path"]).read_bytes()
    return FetchResult(url, 200, "application/octet-stream", data, None, None)


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
    conn, _ = built
    rels = [r for r in _rels(conn, "estado:FI 131-2.2")
            if r["modifier_boe"] == "BOE-A-2018-2041"]
    assert rels
    r = rels[0]
    assert r["kind"] == "CORRECTION"
    assert r["bkind"] == "IMAGE"
    assert r["akind"] in ("TEXT", "TABLE")
    assert "VISUAL_PREDECESSOR_PROVEN" in json.loads(r["diff_levels"])


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
    conn, _ = built
    rels = [r for r in _rels(conn, "estado:FI 105")
            if r["operation_kind"] == "SUBSTITUTE"]
    assert len(rels) == 1
    r = rels[0]
    assert r["bkind"] == "IMAGE" and r["akind"] == "TABLE"
    assert "VISUAL_PREDECESSOR_PROVEN" in json.loads(r["diff_levels"])
    assert r["resolution"] == "RESOLVED"


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
                  "source_blobs", "source_snapshots")
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
        """SELECT m.kind, m.effective_date, i.fecha_vigencia
           FROM modification_relations m
           JOIN instruments i
             ON i.instrument_id = m.modifier_instrument_id
           WHERE i.boe_id='BOE-A-2018-2041'""").fetchall()
    assert rows and all(k == "CORRECTION" for k, _, _ in rows)
    # the correction instrument declares no applicability date -> NULL
    assert all(eff is None for _, eff, _ in rows)


def test_no_applicability_clauses(built):
    conn, _ = built
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any("applicab" in t or "vigencia_cond" in t for t in tables)
    # every non-NULL effective_date equals the modifier's own fecha_vigencia
    bad = conn.execute(
        """SELECT COUNT(*) FROM modification_relations m
           JOIN instruments i
             ON i.instrument_id = m.modifier_instrument_id
           WHERE m.effective_date IS NOT NULL
             AND m.effective_date != i.fecha_vigencia""").fetchone()[0]
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
