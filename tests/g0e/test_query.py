"""G0-E deterministic query surface tests.

The ledger is reconstructed offline from the captured evidence manifests
(G0-C) and the applicability build (G0-D), then queried exclusively
through a read-only connection. No network, no writes, no LLM.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from regdelta import applicability, cli, db as dbm, history, query  # noqa: E402
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
    """Fully built ledger on disk; connection closed — queries open RO."""
    d = tmp_path_factory.mktemp("g0e")
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


# ---------------------------------------------------------------------------
# read-only guarantees
# ---------------------------------------------------------------------------


def test_query_connection_is_readonly(data_dir):
    conn = query.connect_readonly(data_dir)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("CREATE TABLE _t (x)")
    with pytest.raises(sqlite3.OperationalError):
        conn.execute(
            "INSERT INTO anomalies (anomaly_id, kind, detail, detected_at)"
            " VALUES ('x','x','x','x')")
    conn.close()


def test_query_does_not_change_database(data_dir, ro):
    path = data_dir / "regdelta.sqlite"
    before_sha = _db_sha(path)
    before = {t: ro.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("subjects", "representations",
                        "modification_relations", "applicability_clauses",
                        "applicability_effects", "applicability_targets",
                        "anomalies", "source_checks")}
    query.changes(ro, since=date(2025, 1, 1))
    query.affects(ro, target="Circular 4/2017")
    query.upcoming(ro, from_date=date(2026, 3, 1), days=90)
    query.as_of(ro, target="Circular 4/2017", as_of_date=date(2026, 6, 30))
    after = {t: ro.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in before}
    assert after == before
    assert _db_sha(path) == before_sha


def test_missing_database_is_not_created(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(query.DatabaseNotFound):
        query.connect_readonly(d)
    assert not (d / "regdelta.sqlite").exists()


# ---------------------------------------------------------------------------
# instrument resolver
# ---------------------------------------------------------------------------


def test_resolve_exact_boe_id(ro):
    inst = query.resolve_instrument(ro, TARGET)
    assert inst["boe_id"] == TARGET


def test_resolve_exact_circular_number(ro):
    inst = query.resolve_instrument(ro, "Circular 4/2017")
    assert inst["boe_id"] == TARGET
    inst = query.resolve_instrument(ro, "Circular 1/2025")
    assert inst["boe_id"] == MODIFIER


def test_unknown_instrument_fails(ro):
    with pytest.raises(query.InstrumentNotFound):
        query.resolve_instrument(ro, "BOE-A-1900-1")
    with pytest.raises(query.InstrumentNotFound):
        query.resolve_instrument(ro, "Circular 99/1900")


def test_no_fuzzy_resolution(ro, tmp_path):
    with pytest.raises(query.InstrumentNotFound):
        query.resolve_instrument(ro, "circular 4 de 2017")
    with pytest.raises(query.InstrumentNotFound):
        query.resolve_instrument(ro, "4/2017")
    with pytest.raises(query.InstrumentNotFound):
        query.resolve_instrument(ro, "Circular 4/201")
    # ambiguity is an explicit error, not "closest match"
    path = tmp_path / "amb.sqlite"
    conn = dbm.connect(path)
    for i in ("a", "b"):
        conn.execute(
            "INSERT INTO instruments (instrument_id, boe_id, titulo, origin)"
            " VALUES (?,?,?,?)",
            (i * 64, f"BOE-X-{i}", "Circular 9/9999, de test", "PARSED"))
    conn.commit()
    with pytest.raises(query.InstrumentAmbiguous):
        query.resolve_instrument(conn, "Circular 9/9999")
    conn.close()


# ---------------------------------------------------------------------------
# changes
# ---------------------------------------------------------------------------


def test_changes_uses_publication_date(ro):
    """Window on publication_date only: Circular 1/2025 published
    2025-12-29 — all 69 relations land inside that single-day window."""
    out = query.changes(ro, since=date(2025, 12, 29),
                        until=date(2025, 12, 29), target="Circular 4/2017")
    assert out["summary"]["result_count"] == 69
    for r in out["results"]:
        assert r["publication_date"] == "2025-12-29"


def test_changes_since_2026_does_not_confuse_2026_applicability(ro):
    """Applicability effects in 2026 are not 'changes': publication basis
    only. Zero published changes in 2026 is correct."""
    out = query.changes(ro, since=date(2026, 1, 1),
                        target="Circular 4/2017")
    assert out["results"] == []


def test_changes_target_filter(ro):
    all_out = query.changes(ro, since=date(2017, 1, 1))
    tgt_out = query.changes(ro, since=date(2017, 1, 1),
                            target="Circular 4/2017")
    assert tgt_out["summary"]["result_count"] == 292
    assert all_out["summary"]["result_count"] >= 292
    for r in tgt_out["results"]:
        assert r["target"]["boe_id"] == TARGET


def test_changes_stable_order(ro):
    out = query.changes(ro, since=date(2025, 1, 1))
    keys = [(r["publication_date"], r["modifier"]["boe_id"],
             r["target"]["locator_key"], r["relation_id"])
            for r in out["results"]]
    assert keys == sorted(keys)


def test_changes_preserves_partial_and_unresolved(ro):
    out = query.changes(ro, since=date(2017, 1, 1))
    res = {r["resolution"] for r in out["results"]}
    assert {"RESOLVED", "PARTIAL", "UNRESOLVED"} <= res
    assert out["summary"]["result_count"] == 292 + len(other_relations(ro))


def other_relations(ro):
    return [r[0] for r in ro.execute(
        """SELECT mr.relation_id FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           JOIN instruments i ON i.instrument_id = s.instrument_id
           WHERE i.boe_id != ?""", (TARGET,))]


def test_changes_relation_payload(ro):
    out = query.changes(ro, since=date(2025, 12, 29),
                        until=date(2025, 12, 29), target="Circular 4/2017")
    r = out["results"][0]
    for k in ("relation_id", "kind", "operation_kind", "target",
              "modifier", "publication_date", "instrument_effective_date",
              "resolution", "resolution_notes", "diff_levels",
              "before_representation", "after_representation"):
        assert k in r
    assert r["target"]["boe_id"] == TARGET
    assert r["modifier"]["boe_id"] == MODIFIER
    assert r["instrument_effective_date"] == "2025-12-30"


# ---------------------------------------------------------------------------
# affects
# ---------------------------------------------------------------------------


def test_affects_c4_contains_292_relations(ro):
    out = query.affects(ro, target="Circular 4/2017")
    assert out["summary"]["relation_count"] == 292
    assert out["query"]["resolved_boe_id"] == TARGET


def test_affects_modifier_filter_c1_2025_contains_69(ro):
    out = query.affects(ro, target="Circular 4/2017", modifier=MODIFIER)
    assert out["summary"]["relation_count"] == 69
    assert len(out["results"]) == 1
    assert out["results"][0]["boe_id"] == MODIFIER


def test_affects_exact_subject(ro):
    out = query.affects(ro, target="Circular 4/2017",
                        subject="norma:31.apartado:3")
    rels = [r for m in out["results"] for r in m["relations"]]
    assert len(rels) == 1
    assert rels[0]["target"]["locator_key"] == "norma:31.apartado:3"
    with pytest.raises(query.SubjectNotFound):
        query.affects(ro, target="Circular 4/2017",
                      subject="norma:999.apartado:1")


def test_affects_includes_resolution(ro):
    out = query.affects(ro, target="Circular 4/2017")
    res = {r["resolution"] for m in out["results"] for r in m["relations"]}
    assert {"RESOLVED", "PARTIAL", "UNRESOLVED"} <= res


def test_affects_includes_applicability_classification(ro):
    out = query.affects(ro, target="Circular 4/2017", modifier=MODIFIER)
    cls = {r["applicability"]["classification"]
           for m in out["results"] for r in m["relations"]}
    assert "SPECIFIC_BOUND" in cls and "GENERAL_ONLY" in cls
    sample = next(r for m in out["results"] for r in m["relations"]
                  if r["applicability"]["classification"] == "SPECIFIC_BOUND")
    effs = sample["applicability"]["effects"]
    assert effs and all("temporal_effect" in e and "date_value" in e
                        for e in effs)
    assert "has_conditional_structure" in sample["applicability"]


# ---------------------------------------------------------------------------
# upcoming
# ---------------------------------------------------------------------------


def test_upcoming_march_2026(ro):
    out = query.upcoming(ro, from_date=date(2026, 3, 1), days=31)
    dates = {r["date_value"] for r in out["results"]}
    assert "2026-03-31" in dates
    assert "2026-06-30" not in dates
    first = [r for r in out["results"]
             if r["date_value"] == "2026-03-31"]
    assert all(r["temporal_effect"] == "FIRST_REFERENCE_DATE"
               for r in first)


def test_upcoming_june_2026_contains_first_and_last(ro):
    out = query.upcoming(ro, from_date=date(2026, 6, 1), days=29)
    at_0630 = [r for r in out["results"] if r["date_value"] == "2026-06-30"]
    kinds = {r["temporal_effect"] for r in at_0630}
    assert "FIRST_REFERENCE_DATE" in kinds
    assert "LAST_REFERENCE_DATE" in kinds


def test_upcoming_window_is_inclusive(ro):
    out = query.upcoming(ro, from_date=date(2026, 1, 1), days=0)
    assert any(r["date_value"] == "2026-01-01" for r in out["results"])
    out = query.upcoming(ro, from_date=date(2025, 12, 30), days=0)
    assert any(r["temporal_effect"] == "INSTRUMENT_EFFECTIVE_FROM"
               for r in out["results"])


def test_upcoming_dedupes_effect_not_targets(ro):
    """One row per effect; a clause bound to N relations still emits a
    single result whose effective_targets lists them."""
    out = query.upcoming(ro, from_date=date(2026, 3, 1), days=31)
    ids = [r["effect_id"] for r in out["results"]]
    assert len(ids) == len(set(ids))
    multi = [r for r in out["results"] if r["target_count"] > 1]
    assert multi
    for r in multi:
        assert r["target_count"] == (
            len(r["effective_targets"]["modification_relations"])
            + len(r["effective_targets"]["instruments"]))


def test_upcoming_preserves_effect_type(ro):
    out = query.upcoming(ro, from_date=date(2026, 6, 1), days=29)
    kinds = {r["temporal_effect"] for r in out["results"]}
    assert "LAST_REFERENCE_DATE" in kinds  # never renamed to expiry/end


def test_upcoming_effective_targets_follow_scoped_applicability(ro):
    """dfu:e's frequency-conditioned FIRST_REFERENCE_DATE applies to the
    states bound through dfu:e — never to siblings' relations (dfu:a)."""
    conn = ro
    rid_a = conn.execute(
        """SELECT mr.relation_id FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           WHERE s.locator_key='norma:22.apartado:2'""").fetchone()[0]
    out = query.upcoming(conn, from_date=date(2026, 3, 1), days=31)
    for r in out["results"]:
        if "2026-03-31" == r["date_value"]:
            assert rid_a not in r["effective_targets"]["modification_relations"]


# ---------------------------------------------------------------------------
# as-of
# ---------------------------------------------------------------------------


def test_as_of_declares_semantics(ro):
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2026, 6, 30))
    assert out["semantics"] == \
        "LEGAL_TIME_FACTS_NOT_SYNTHETIC_CONSOLIDATED_VERSION"


def test_as_of_filters_future_publications(ro):
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2025, 12, 28))
    mod_boes = {r["modifier"]["boe_id"] for r in out["results"]}
    assert MODIFIER not in mod_boes  # published 2025-12-29
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2025, 12, 29))
    mod_boes = {r["modifier"]["boe_id"] for r in out["results"]}
    assert MODIFIER in mod_boes


def test_as_of_2025_12_29_publication_vs_effective(ro):
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2025, 12, 29))
    r = next(r for r in out["results"]
             if r["modifier"]["boe_id"] == MODIFIER)
    assert r["publication_relative"] == "ON"
    assert r["instrument_effective_relative"] == "AFTER"  # 2025-12-30


def test_as_of_2025_12_30_specific_apply_from_still_future(ro):
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2025, 12, 30))
    # norma:22.apartado:2 is bound to dfu:b (APPLY_FROM 2026-01-01)
    r = next(r for r in out["results"]
             if r["target"]["locator_key"] == "norma:22.apartado:2"
             and r["modifier"]["boe_id"] == MODIFIER)
    assert r["instrument_effective_relative"] == "ON"
    effs = _annotated_effects(r["applicability"])
    apply = [e for e in effs if e["temporal_effect"] == "APPLY_FROM"]
    assert apply and all(e["relative_to_as_of"] == "AFTER" for e in apply)


def test_as_of_does_not_return_scalar_effective_date(ro):
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2026, 6, 30))
    blob = json.dumps(out)
    assert '"effective_date"' not in blob


def test_as_of_fi131_first_and_last_coexist(ro):
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2026, 6, 30),
                      subject="estado:FI 131")
    r = out["results"][0]
    effs = _annotated_effects(r["applicability"])
    kinds = {e["temporal_effect"] for e in effs}
    assert "FIRST_REFERENCE_DATE" in kinds
    assert "LAST_REFERENCE_DATE" in kinds
    last = [e for e in effs
            if e["temporal_effect"] == "LAST_REFERENCE_DATE"]
    assert any(e["relative_to_as_of"] == "ON" for e in last)


def test_as_of_preserves_conditional_tree(ro):
    out = query.as_of(ro, target="Circular 4/2017",
                      as_of_date=date(2026, 6, 30),
                      subject="norma:31.apartado:3")
    r = out["results"][0]
    keys = {n["clause"]["clause_key"]
            for tr in r["applicability"]["specific_clause_trees"]
            for n in _walk(tr)}
    assert "dt1:2:s1" in keys and "dt1:2:s2" in keys


def _walk(node):
    yield node
    for ch in node["children"]:
        yield from _walk(ch)


def _annotated_effects(app):
    out = []
    for tr in app["instrument_rules"] + app["specific_clause_trees"]:
        for n in _walk(tr):
            out.extend(n["effects"])
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(argv, capsys):
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_cli_changes_json(data_dir, capsys):
    code, out = _cli(["changes", "--since", "2025-12-29",
                      "--until", "2025-12-29", "--target",
                      "Circular 4/2017", "--data-dir", str(data_dir)],
                     capsys)
    assert code == 0
    assert out["schema"] == "regdelta.query.changes/v1"
    assert out["summary"]["result_count"] == 69


def test_cli_affects_json(data_dir, capsys):
    code, out = _cli(["affects", "Circular 4/2017",
                      "--modifier", MODIFIER, "--data-dir", str(data_dir)],
                     capsys)
    assert code == 0
    assert out["schema"] == "regdelta.query.affects/v1"
    assert out["summary"]["relation_count"] == 69


def test_cli_upcoming_json(data_dir, capsys):
    code, out = _cli(["upcoming", "--from", "2026-03-01", "--days", "31",
                      "--data-dir", str(data_dir)], capsys)
    assert code == 0
    assert out["schema"] == "regdelta.query.upcoming/v1"
    assert any(r["date_value"] == "2026-03-31" for r in out["results"])


def test_cli_as_of_json(data_dir, capsys):
    code, out = _cli(["as-of", "Circular 4/2017", "--date", "2026-06-30",
                      "--data-dir", str(data_dir)], capsys)
    assert code == 0
    assert out["schema"] == "regdelta.query.as_of/v1"
    assert out["semantics"].startswith("LEGAL_TIME_FACTS")


def test_cli_error_json(data_dir, capsys):
    code = cli.main(["affects", "Circular 99/1900",
                     "--data-dir", str(data_dir)])
    err = capsys.readouterr().out
    assert code == 2
    assert json.loads(err)["error"]["code"] == "INSTRUMENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# frozen invariants
# ---------------------------------------------------------------------------


def test_g0c_g0d_invariants(ro):
    assert ro.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 221
    assert ro.execute(
        "SELECT COUNT(*) FROM representations").fetchone()[0] == 335
    assert ro.execute(
        "SELECT COUNT(*) FROM modification_relations").fetchone()[0] == 292
    assert dict(ro.execute(
        "SELECT resolution, COUNT(*) FROM modification_relations"
        " GROUP BY resolution").fetchall()) == {
        "RESOLVED": 182, "PARTIAL": 93, "UNRESOLVED": 17}
    assert ro.execute(
        "SELECT COUNT(*) FROM applicability_clauses").fetchone()[0] == 26
    assert ro.execute(
        "SELECT COUNT(*) FROM applicability_effects").fetchone()[0] == 16
    assert ro.execute(
        "SELECT COUNT(*) FROM applicability_targets").fetchone()[0] == 98
    assert ro.execute(
        "SELECT COUNT(*) FROM anomalies").fetchone()[0] == 23
