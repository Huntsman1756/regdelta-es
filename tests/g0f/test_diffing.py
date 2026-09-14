"""G0-F representation-aware diff tests.

Same offline ledger as G0-E: reconstructed from the captured evidence
manifests (G0-C) plus the applicability build (G0-D); every query runs
through a read-only connection. No network, no writes, no OCR.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from regdelta import applicability, cli, db as dbm, diffing, history, query  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402

MODIFIER = "BOE-A-2025-26847"
TARGET = "BOE-A-2017-14334"
MANIFESTS = [
    ROOT / "evidence" / "g0c" / "raw" / "manifest.json",
    ROOT / "evidence" / "g0c1" / "raw" / "manifest.json",
    ROOT / "evidence" / "g0c2" / "raw" / "manifest.json",
]

pytestmark = pytest.mark.skipif(
    not all(m.exists() for m in MANIFESTS),
    reason="G0-C evidence not generated",
)

_BY_URL: dict[str, dict] = {}
if all(m.exists() for m in MANIFESTS):
    for mp in MANIFESTS:
        for e in json.loads(mp.read_text(encoding="utf-8"))["entries"].values():
            _BY_URL[e["url"]] = e


def _fetch(url: str, accept: str) -> FetchResult:
    e = _BY_URL.get(url)
    if e is None:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in captured evidence",
                           via=EVIDENCE_IMPORT)
    return FetchResult(url, 200, "application/octet-stream",
                       (ROOT / e["path"]).read_bytes(), None, None,
                       via=EVIDENCE_IMPORT)


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("g0f")
    conn = dbm.connect(d / "regdelta.sqlite")
    history.reconstruct(conn, d, TARGET, _fetch)
    conn.commit()
    applicability.build(conn, d, MODIFIER, TARGET)
    conn.commit()
    conn.close()
    return d


@pytest.fixture(scope="module")
def ro(data_dir):
    conn = query.connect_readonly(data_dir)
    yield conn
    conn.close()


def _db_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _diff_subject(ro, subject, frm, to):
    return diffing.diff(ro, target="Circular 4/2017",
                        from_date=frm, to_date=to, subject=subject)


# ---------------------------------------------------------------------------
# window semantics — publication_date only, from exclusive / to inclusive
# ---------------------------------------------------------------------------


def test_diff_window_from_exclusive_to_inclusive(ro):
    """W1: the 69 relations published 2025-12-29 by Circular 1/2025 are
    inside (2025-12-28, 2025-12-29]. W2: (2025-12-29, 2025-12-30]
    excludes them — `from` is exclusive."""
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2025, 12, 28),
                       to_date=date(2025, 12, 29))
    assert out["summary"]["relation_count"] == 69
    assert all(r["publication_date"] == "2025-12-29"
               for r in out["results"])
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2025, 12, 29),
                       to_date=date(2025, 12, 30))
    assert out["summary"]["relation_count"] == 0


def test_diff_same_day_empty(ro):
    """to == from is valid and necessarily empty under
    from < publication_date <= to — not an error."""
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2025, 12, 29),
                       to_date=date(2025, 12, 29))
    assert out["results"] == []
    assert out["summary"]["relation_count"] == 0


def test_diff_to_before_from_fails(ro):
    with pytest.raises(query.InvalidDateRange):
        diffing.diff(ro, target="Circular 4/2017",
                     from_date=date(2025, 12, 30),
                     to_date=date(2025, 12, 29))


def test_diff_original_pitch_window_is_zero_but_upcoming_not_zero(ro):
    """W3: publication window (2025-12-31, 2026-09-13] holds zero
    relations even though dated applicability exists inside 2026 —
    publication time and applicability time stay separate."""
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2025, 12, 31),
                       to_date=date(2026, 9, 13))
    assert out["summary"]["relation_count"] == 0
    up = query.upcoming(ro, from_date=date(2026, 3, 1), days=31)
    assert up["summary"]["result_count"] > 0


def test_diff_semantics_declared(ro):
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2025, 12, 28),
                       to_date=date(2025, 12, 29))
    assert out["semantics"] == (
        "REPRESENTATION_DELTAS_FOR_RELATIONS_PUBLISHED_"
        "AFTER_FROM_THROUGH_TO")


# ---------------------------------------------------------------------------
# strategy fixtures F1–F8
# ---------------------------------------------------------------------------


def test_diff_text_to_text(ro):
    """F1 — norma:33, Circular 2/2018: TEXT→TEXT produces a real line
    diff with at least one hunk."""
    out = _diff_subject(ro, "norma:33", date(2018, 12, 27),
                        date(2018, 12, 29))
    assert out["summary"]["relation_count"] == 1
    r = out["results"][0]
    assert r["comparison"]["strategy"] == "TEXT_LINE_DIFF"
    assert r["comparison"]["content_diff_available"] is True
    assert r["comparison"]["content_changed"] is True
    assert len(r["comparison"]["hunks"]) > 0
    assert r["comparison"]["stats"]["hunk_count"] == len(
        r["comparison"]["hunks"])
    for h in r["comparison"]["hunks"]:
        assert h["tag"] in ("replace", "delete", "insert")
        assert len(h["before_range"]) == 2
        assert len(h["after_range"]) == 2


def test_diff_table_to_table(ro):
    """F2 — estado:FI 142-1.1 Circular 1/2025 hop: TABLE→TABLE produces
    TABLE_ROW_DIFF over persisted table rows, never VISUAL_PREDECESSOR."""
    out = _diff_subject(ro, "estado:FI 142-1.1", date(2025, 12, 28),
                        date(2025, 12, 29))
    assert out["summary"]["relation_count"] == 1
    r = out["results"][0]
    assert r["comparison"]["strategy"] == "TABLE_ROW_DIFF"
    assert r["comparison"]["basis"] == "persisted_table_rows"
    assert r["comparison"]["content_diff_available"] is True
    assert len(r["comparison"]["hunks"]) > 0


def test_diff_image_to_table(ro):
    """F3 — estado:FI 105 SUBSTITUTE (Circular 1/2025): IMAGE→TABLE is
    VISUAL_PREDECESSOR; no pretended semantic comparison."""
    out = _diff_subject(ro, "estado:FI 105", date(2025, 12, 28),
                        date(2025, 12, 29))
    sub = [r for r in out["results"] if r["operation_kind"] == "SUBSTITUTE"]
    assert len(sub) == 1
    cmp_ = sub[0]["comparison"]
    assert cmp_["strategy"] == "VISUAL_PREDECESSOR"
    assert cmp_["content_diff_available"] is False
    assert cmp_["hunks"] == []
    assert sub[0]["before"]["representation_kind"] == "IMAGE"
    assert sub[0]["after"]["representation_kind"] == "TABLE"


def test_diff_image_to_image(ro):
    """F4 — estado:FI 100-14 (Circular 2/2020): IMAGE→IMAGE is
    VISUAL_REPRESENTATION_CHANGE with real artifact blob hashes on both
    sides, no pixel/OCR pretence."""
    out = _diff_subject(ro, "estado:FI 100-14", date(2020, 6, 15),
                        date(2020, 6, 17))
    assert out["summary"]["relation_count"] == 1
    r = out["results"][0]
    cmp_ = r["comparison"]
    assert cmp_["strategy"] == "VISUAL_REPRESENTATION_CHANGE"
    assert cmp_["content_diff_available"] is False
    assert cmp_["hunks"] == []
    assert r["before"]["artifact_hashes"]
    assert r["after"]["artifact_hashes"]
    assert cmp_["content_changed"] is True


def test_diff_correction_delete(ro):
    """F5 — estado:FI 102-2: CORRECTION + DELETE stays a declared
    deletion with the visual predecessor preserved as evidence."""
    out = _diff_subject(ro, "estado:FI 102-2", date(2018, 2, 14),
                        date(2018, 2, 16))
    assert out["summary"]["relation_count"] == 1
    r = out["results"][0]
    assert r["kind"] == "CORRECTION"
    assert r["comparison"]["strategy"] == "DECLARED_DELETION"
    assert r["comparison"]["hunks"] == []
    assert r["before"]["representation_kind"] == "IMAGE"
    assert r["after"] is None


def test_diff_correction_image_to_text(ro):
    """F6 — estado:FI 131-2.2: CORRECTION keeps declared literals;
    IMAGE→TEXT is VISUAL_PREDECESSOR (kind-pair wins over the ADD
    operation shape since before is present)."""
    out = _diff_subject(ro, "estado:FI 131-2.2", date(2018, 2, 14),
                        date(2018, 2, 16))
    assert out["summary"]["relation_count"] == 1
    r = out["results"][0]
    assert r["kind"] == "CORRECTION"
    assert r["comparison"]["strategy"] == "VISUAL_PREDECESSOR"
    assert r["comparison"]["content_diff_available"] is False
    assert r["before"]["representation_kind"] == "IMAGE"
    assert r["after"]["representation_kind"] == "TEXT"


def test_diff_partial_is_not_invented(ro):
    """F7 — estado:FI 105 MODIFY PARTIAL: missing after rep is
    INSUFFICIENT_REPRESENTATION_EVIDENCE, not a fabricated diff."""
    out = _diff_subject(ro, "estado:FI 105", date(2025, 12, 28),
                        date(2025, 12, 29))
    partial = [r for r in out["results"] if r["resolution"] == "PARTIAL"]
    assert len(partial) == 2
    for r in partial:
        assert r["comparison"]["strategy"] == (
            "INSUFFICIENT_REPRESENTATION_EVIDENCE")
        assert r["comparison"]["hunks"] == []
        assert r["comparison"]["content_diff_available"] is False
        assert r["resolution_notes"]


def test_diff_unresolved_is_not_invented(ro):
    """F8 — estado:FI 140-3 UNRESOLVED correction: result returned
    without exception, comparison is INSUFFICIENT_REPRESENTATION_EVIDENCE."""
    out = _diff_subject(ro, "estado:FI 140-3", date(2018, 2, 14),
                        date(2018, 2, 16))
    unres = [r for r in out["results"] if r["resolution"] == "UNRESOLVED"]
    assert len(unres) == 1
    r = unres[0]
    assert r["comparison"]["strategy"] == (
        "INSUFFICIENT_REPRESENTATION_EVIDENCE")
    assert r["comparison"]["content_diff_available"] is False
    assert r["before"] is None and r["after"] is None


def test_diff_declared_addition(ro):
    """ADD with after present and before absent is DECLARED_ADDITION —
    never a fabricated diff against empty text."""
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2025, 12, 28),
                       to_date=date(2025, 12, 29))
    adds = [r for r in out["results"] if r["operation_kind"] == "ADD"]
    assert adds
    for r in adds:
        if r["before"] is None and r["after"] is not None:
            assert r["comparison"]["strategy"] == "DECLARED_ADDITION"
            assert r["comparison"]["hunks"] == []


# ---------------------------------------------------------------------------
# fingerprints and artifact hashes
# ---------------------------------------------------------------------------


def test_image_uses_artifact_blob_hashes_not_locator_fingerprint(ro):
    """IMAGE fingerprint is the persisted locator fingerprint — the
    artifact_hashes come from artifact_locator.pages[].blob_sha256 and
    are distinct values."""
    out = _diff_subject(ro, "estado:FI 100-14", date(2020, 6, 15),
                        date(2020, 6, 17))
    r = out["results"][0]
    for side in ("before", "after"):
        rep = r[side]
        loc_pages = rep["artifact_locator"]["pages"]
        expected = [p["blob_sha256"] for p in loc_pages]
        assert rep["artifact_hashes"] == expected
        assert rep["representation_fingerprint"] not in expected
        assert len(rep["representation_fingerprint"]) == 64


def test_text_representation_fingerprint_matches_persisted_content(ro):
    """TEXT fingerprint is the persisted content_sha256 — verified
    against sha256(text_content) straight from the DB."""
    out = _diff_subject(ro, "norma:33", date(2018, 12, 27),
                        date(2018, 12, 29))
    r = out["results"][0]
    for side in ("before", "after"):
        rep = r[side]
        row = ro.execute(
            "SELECT text_content, content_sha256 FROM representations"
            " WHERE representation_id=?",
            (rep["representation_id"],)).fetchone()
        assert rep["representation_fingerprint"] == row[1]
        assert row[1] == hashlib.sha256(
            row[0].encode("utf-8")).hexdigest()
        assert rep["artifact_hashes"] == []


# ---------------------------------------------------------------------------
# filters, ordering, determinism
# ---------------------------------------------------------------------------


def test_diff_exact_subject_filter(ro):
    out = _diff_subject(ro, "norma:22.apartado:2",
                        date(2025, 12, 28), date(2025, 12, 29))
    assert out["summary"]["relation_count"] == 1
    assert out["results"][0]["target"]["locator_key"] == (
        "norma:22.apartado:2")
    assert out["summary"]["subject_count"] == 1


def test_diff_unknown_subject_fails(ro):
    with pytest.raises(query.SubjectNotFound):
        _diff_subject(ro, "norma:99999", date(2025, 12, 28),
                      date(2025, 12, 29))


def test_diff_stable_order(ro):
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2017, 1, 1), to_date=date(2026, 1, 1))
    keys = [(r["publication_date"], r["modifier"]["boe_id"],
             r["target"]["locator_key"], r["relation_id"])
            for r in out["results"]]
    assert keys == sorted(keys)
    assert out["summary"]["subject_count"] == len(
        {r["target"]["locator_key"] for r in out["results"]})


def test_diff_stable_hunks(ro):
    a = _diff_subject(ro, "norma:33", date(2018, 12, 27),
                      date(2018, 12, 29))
    b = _diff_subject(ro, "norma:33", date(2018, 12, 27),
                      date(2018, 12, 29))
    assert a["results"][0]["comparison"]["hunks"] == \
        b["results"][0]["comparison"]["hunks"]


def test_diff_rerun_identical_json(ro):
    kw = dict(target="Circular 4/2017", from_date=date(2025, 12, 28),
              to_date=date(2025, 12, 29))
    a = json.dumps(diffing.diff(ro, **kw), sort_keys=True)
    b = json.dumps(diffing.diff(ro, **kw), sort_keys=True)
    assert a == b


# ---------------------------------------------------------------------------
# provenance + read-only + no network
# ---------------------------------------------------------------------------


def test_diff_provenance_resolves(ro):
    """Every emitted snapshot id resolves to a source_snapshots row with
    a real blob sha256; multi-page IMAGEs expose artifact blobs."""
    out = diffing.diff(ro, target="Circular 4/2017",
                       from_date=date(2017, 1, 1), to_date=date(2026, 1, 1))
    known = {r[0] for r in ro.execute(
        "SELECT snapshot_id FROM source_snapshots")}
    for r in out["results"]:
        ev = r["evidence"]
        assert ev["relation_source_snapshots"]
        assert set(ev["relation_source_snapshots"]) <= known
        for side in ("before", "after"):
            if r[side] is None:
                assert ev[side] is None
                continue
            assert ev[side]["source_snapshot_id"] in known
            assert ev[side]["source_blob_sha256"]
            assert len(ev[side]["source_blob_sha256"]) == 64
            assert ev[side]["source_snapshot_id"] == \
                r[side]["source_snapshot_id"]


def test_diff_readonly(data_dir, ro):
    path = data_dir / "regdelta.sqlite"
    before_sha = _db_sha(path)
    diffing.diff(ro, target="Circular 4/2017",
                 from_date=date(2017, 1, 1), to_date=date(2026, 1, 1))
    assert _db_sha(path) == before_sha
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO anomalies (anomaly_id, kind, detail,"
                   " detected_at) VALUES ('x','x','x','x')")


def test_diff_no_network():
    """diffing.py must not import http/watcher/requests/urllib."""
    src = (ROOT / "src" / "regdelta" / "diffing.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    forbidden_first = {"http", "requests", "urllib", "socket"}
    forbidden_last = {"http", "watcher"}
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    for m in mods:
        parts = m.split(".")
        assert parts[0] not in forbidden_first, m
        assert parts[-1] not in forbidden_last, m


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_diff_json(data_dir, capsys):
    rc = cli.main(["diff", "Circular 4/2017", "--from", "2025-12-28",
                   "--to", "2025-12-29", "--data-dir", str(data_dir)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "regdelta.query.diff/v1"
    assert out["summary"]["relation_count"] == 69


def test_cli_diff_error_json(data_dir, capsys):
    rc = cli.main(["diff", "Circular 4/2017", "--from", "2025-12-30",
                   "--to", "2025-12-29", "--data-dir", str(data_dir)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "INVALID_DATE_RANGE"


# ---------------------------------------------------------------------------
# frozen invariants
# ---------------------------------------------------------------------------


def test_g0c_g0d_g0e_invariants_unchanged(ro):
    counts = {t: ro.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("subjects", "representations",
                        "modification_relations", "applicability_clauses",
                        "applicability_effects", "applicability_targets",
                        "anomalies")}
    assert counts == {
        "subjects": 221, "representations": 335,
        "modification_relations": 292, "applicability_clauses": 26,
        "applicability_effects": 16, "applicability_targets": 98,
        "anomalies": 23}
    res = dict(ro.execute(
        "SELECT resolution, COUNT(*) FROM modification_relations"
        " GROUP BY resolution"))
    assert res == {"RESOLVED": 182, "PARTIAL": 93, "UNRESOLVED": 17}
