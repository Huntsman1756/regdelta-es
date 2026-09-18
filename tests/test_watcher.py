from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from regdelta import state, watcher
from regdelta.http import EVIDENCE_IMPORT
from regdelta.rawstore import blob_path
from regdelta.util import madrid_local_date, normalize_title, sha256_hex, sha256_hex_text
from regdelta.watcher import EXIT_OK, consultation_uid, run
from conftest import counts, db, load, make_fetch


def _sumario_result(summary: dict) -> dict:
    return [s for s in summary["sources"] if s["source_id"] == "boe_sumario"][0]


def _consultas_result(summary: dict) -> dict:
    return [s for s in summary["sources"] if s["source_id"] == "bde_consultas"][0]


def test_26847_official_from_sumario(fresh_dir):
    summary = run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    assert summary["exit_code"] == EXIT_OK
    conn = db(fresh_dir)
    row = conn.execute(
        "SELECT p.seccion_codigo, p.departamento_codigo, p.fecha_sumario, s.source_date,"
        " s.source_updated_at FROM boe_item_placements p JOIN source_snapshots s"
        " ON s.snapshot_id = p.snapshot_id WHERE p.item_uid = 'BOE-A-2025-26847'"
    ).fetchone()
    assert row is not None
    seccion, departamento, fecha, source_date, source_updated_at = row
    assert seccion == "1"
    assert departamento == "1020"
    assert fecha == "2025-12-29"
    assert source_date == "2025-12-29"
    assert source_updated_at is None


def test_no_consolidated_dependency_in_g0ab():
    import regdelta
    from pathlib import Path
    src = Path(regdelta.__file__).parent
    for py in src.rglob("*.py"):
        assert "legislacion-consolidada" not in py.read_text(encoding="utf-8")
    evidence = load("consolidada_404_26847.xml").decode("latin-1")
    assert "<code>404</code>" in evidence


def test_invalid_sumario_structure_is_rejected(fresh_dir):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch.set_url("boe/sumario/20251229", b"<response><data/></response>")
    summary = run("2025-12-29", fresh_dir, fetch)
    result = _sumario_result(summary)
    assert result["status"] == "PARSE_INVALID"
    assert result["parse_status"] == "INVALID_STRUCTURE"
    assert summary["exit_code"] == 3
    conn = db(fresh_dir)
    assert conn.execute("SELECT count(*) FROM boe_item_placements").fetchone()[0] == 0
    status, parse_status = conn.execute(
        "SELECT c.status, s.parse_status FROM source_checks c JOIN source_snapshots s"
        " ON s.snapshot_id = c.snapshot_id WHERE c.source_id = 'boe_sumario'"
    ).fetchone()
    assert status == "PARSE_INVALID"
    assert parse_status == "INVALID_STRUCTURE"


def test_date_mismatched_sumario_is_rejected(fresh_dir):
    summary = run("2026-01-02", fresh_dir, make_fetch("2026-01-02", "sum_20251229.xml"))
    assert _sumario_result(summary)["status"] == "PARSE_INVALID"


def test_same_bytes_no_new_blobs_snapshots_entities_but_new_check(fresh_dir):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    run("2025-12-29", fresh_dir, fetch)
    first = counts(db(fresh_dir))
    run("2025-12-29", fresh_dir, fetch)
    second = counts(db(fresh_dir))
    for table in ["source_blobs", "source_snapshots", "boe_items",
                  "boe_item_placements", "bde_consultations", "bde_snapshot_memberships"]:
        assert second[table] == first[table], table
    assert second["source_checks"] == first["source_checks"] + 2


def test_same_blob_can_be_checked_multiple_times(fresh_dir):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    run("2025-12-29", fresh_dir, fetch)
    run("2025-12-29", fresh_dir, fetch)
    conn = db(fresh_dir)
    blobs = conn.execute(
        "SELECT count(*) FROM source_blobs WHERE sha256 = ?",
        (sha256_hex(load("sum_20251229.xml")),),
    ).fetchone()[0]
    snapshots = conn.execute(
        "SELECT count(*) FROM source_snapshots WHERE source_id = 'boe_sumario'"
    ).fetchone()[0]
    checks = conn.execute(
        "SELECT count(*) FROM source_checks WHERE source_id = 'boe_sumario'"
    ).fetchone()[0]
    assert blobs == 1
    assert snapshots == 1
    assert checks == 2


def test_rapid_checks_are_all_recorded_without_collision(fresh_dir):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    for _ in range(5):
        run("2025-12-29", fresh_dir, fetch)
    conn = db(fresh_dir)
    assert conn.execute(
        "SELECT count(*) FROM source_checks WHERE source_id = 'boe_sumario'"
    ).fetchone()[0] == 5
    assert conn.execute(
        "SELECT count(*) FROM source_checks WHERE source_id = 'bde_consultas'"
    ).fetchone()[0] == 5
    assert conn.execute(
        "SELECT count(DISTINCT check_id) FROM source_checks"
    ).fetchone()[0] == 10


def test_snapshot_sequence_a_b_a_preserved(fresh_dir):
    body = load("bde_pi.html")
    mutated = body.replace(b"29/06/2026", b"31/12/2026", 1)
    assert mutated != body
    fetch_a = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b.set_url("consultas-publicas", mutated, "text/html; charset=utf-8")
    run("2025-12-29", fresh_dir, fetch_a)
    run("2025-12-29", fresh_dir, fetch_b)
    run("2025-12-29", fresh_dir, fetch_a)
    conn = db(fresh_dir)
    consultas_checks = conn.execute(
        "SELECT count(*) FROM source_checks WHERE source_id = 'bde_consultas'"
    ).fetchone()[0]
    consultas_snapshots = conn.execute(
        "SELECT count(*) FROM source_snapshots WHERE source_id = 'bde_consultas'"
    ).fetchone()[0]
    consultas_blobs = conn.execute(
        "SELECT count(DISTINCT s.blob_sha256) FROM source_snapshots s"
        " WHERE s.source_id = 'bde_consultas'"
    ).fetchone()[0]
    assert (consultas_checks, consultas_snapshots, consultas_blobs) == (3, 2, 2)
    assert conn.execute("SELECT count(*) FROM bde_snapshot_memberships").fetchone()[0] == 6
    assert conn.execute("SELECT count(*) FROM bde_consultations").fetchone()[0] == 3


def test_db_rollback_leaves_no_partial_db_state(fresh_dir, monkeypatch):
    import regdelta.watcher as watcher_mod

    def injected(*args, **kwargs):
        raise RuntimeError("injected db failure")

    monkeypatch.setattr(watcher_mod, "_insert_boe_derived", injected)
    with pytest.raises(RuntimeError, match="injected db failure"):
        run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    monkeypatch.undo()
    conn = db(fresh_dir)
    assert set(counts(conn).values()) == {0}


def test_orphan_blob_after_db_failure_is_unreferenced_and_safe(fresh_dir, monkeypatch):
    import regdelta.watcher as watcher_mod

    def injected(*args, **kwargs):
        raise RuntimeError("injected db failure")

    monkeypatch.setattr(watcher_mod, "_insert_boe_derived", injected)
    with pytest.raises(RuntimeError):
        run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    monkeypatch.undo()

    sha = sha256_hex(load("sum_20251229.xml"))
    raw_file = blob_path(fresh_dir, sha)
    assert raw_file.exists()
    conn = db(fresh_dir)
    assert conn.execute(
        "SELECT count(*) FROM source_blobs WHERE sha256 = ?", (sha,)
    ).fetchone()[0] == 0

    summary = run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    assert summary["exit_code"] == EXIT_OK
    assert conn.execute(
        "SELECT count(*) FROM source_blobs WHERE sha256 = ?", (sha,)
    ).fetchone()[0] == 1
    raw_files = list((fresh_dir / "raw" / "sha256").rglob("*"))
    raw_files = [p for p in raw_files if p.is_file()]
    blob_rows = conn.execute("SELECT count(*) FROM source_blobs").fetchone()[0]
    assert len(raw_files) == blob_rows


def test_fetch_runs_outside_sqlite_write_transaction(fresh_dir):
    inner = make_fetch("2025-12-29", "sum_20251229.xml")
    probe_ok = []

    def probing_fetch(url, accept):
        probe = sqlite3.connect(fresh_dir / "regdelta.sqlite", timeout=0)
        probe.isolation_level = None
        try:
            probe.execute("BEGIN IMMEDIATE")
            probe.execute("ROLLBACK")
            probe_ok.append(url)
        finally:
            probe.close()
        return inner(url, accept)

    summary = run("2025-12-29", fresh_dir, probing_fetch)
    assert summary["exit_code"] == EXIT_OK
    assert len(probe_ok) == 2


def test_snapshot_records_parser_provenance(fresh_dir):
    run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    conn = db(fresh_dir)
    rows = dict(
        conn.execute(
            "SELECT source_id, parser_name || '/' || parser_version FROM source_snapshots"
        )
    )
    assert rows == {
        "boe_sumario": "boe_sumario/v1",
        "bde_consultas": "bde_consultas/v1",
    }


def test_consultation_identity_includes_published_on():
    title = normalize_title("Audiencia pública sobre el Proyecto de Circular (CIR)")
    uid_a = consultation_uid(title, "2026-06-08")
    uid_b = consultation_uid(title, "2027-06-08")
    assert uid_a != uid_b
    assert len(uid_a) == 64 and len(uid_b) == 64


def test_consultation_identity_preserves_diacritics():
    normalized = normalize_title("Audiencia pública — información financiera")
    assert "pública" in normalized
    assert "información" in normalized


def test_same_title_different_publication_dates_are_distinct(fresh_dir):
    body = load("bde_pi.html")
    mutated = body.replace(b"08/06/2026", b"09/06/2026", 1)
    fetch_a = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b.set_url("consultas-publicas", mutated, "text/html; charset=utf-8")
    run("2025-12-29", fresh_dir, fetch_a)
    run("2025-12-29", fresh_dir, fetch_b)
    conn = db(fresh_dir)
    assert conn.execute("SELECT count(*) FROM bde_consultations").fetchone()[0] == 4
    assert conn.execute(
        "SELECT count(DISTINCT title_normalized) FROM bde_consultations"
    ).fetchone()[0] == 3


def test_snapshot_keeps_changed_pdf_url(fresh_dir):
    body = load("bde_pi.html")
    mutated = body.replace(b"Proyecto_0426.pdf", b"Proyecto_9999.pdf", 1)
    fetch_a = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b.set_url("consultas-publicas", mutated, "text/html; charset=utf-8")
    run("2025-12-29", fresh_dir, fetch_a)
    run("2025-12-29", fresh_dir, fetch_b)
    conn = db(fresh_dir)
    assert conn.execute("SELECT count(*) FROM bde_consultations").fetchone()[0] == 3
    urls = {
        old_new for old_new in conn.execute(
            "SELECT m.project_pdf_urls FROM bde_snapshot_memberships m"
            " JOIN bde_consultations c ON c.consultation_uid = m.consultation_uid"
            " WHERE c.published_on = '2026-09-04'"
        )
    }
    joined = " ".join(row[0] for row in urls)
    assert "Proyecto_0426.pdf" in joined
    assert "Proyecto_9999.pdf" in joined


def test_snapshot_keeps_changed_boe_title(fresh_dir):
    body = load("sum_20251229.xml")
    mutated = body.replace(b"por la que se modifican", b"TITULO CAMBIADO", 1)
    assert mutated != body
    fetch_a = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b.set_url("boe/sumario/20251229", mutated)
    run("2025-12-29", fresh_dir, fetch_a)
    run("2025-12-29", fresh_dir, fetch_b)
    conn = db(fresh_dir)
    assert conn.execute(
        "SELECT count(*) FROM boe_items WHERE item_uid = 'BOE-A-2025-26847'"
    ).fetchone()[0] == 1
    titulos = [row[0] for row in conn.execute(
        "SELECT titulo FROM boe_item_placements WHERE item_uid = 'BOE-A-2025-26847'"
        " ORDER BY rowid"
    )]
    assert len(titulos) == 2
    assert titulos[0] != titulos[1]
    assert "TITULO CAMBIADO" in titulos[1]


def test_latest_snapshot_end_date_wins_not_max(fresh_dir):
    body = load("bde_pi.html")
    extended = body.replace(b"29/06/2026", b"31/12/2026", 1)
    fetch_a = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b.set_url("consultas-publicas", extended, "text/html; charset=utf-8")
    run("2025-12-29", fresh_dir, fetch_a)
    run("2025-12-29", fresh_dir, fetch_b)
    run("2025-12-29", fresh_dir, fetch_a)
    conn = db(fresh_dir)
    statuses = state.bde_window_statuses(conn, "2026-09-13")
    cir_uid = conn.execute(
        "SELECT consultation_uid FROM bde_consultations WHERE title_normalized LIKE '%(cir)%'"
    ).fetchone()[0]
    assert statuses[cir_uid] == "ENDED"


def test_ended_consultation_still_listed(fresh_dir):
    run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    conn = db(fresh_dir)
    statuses = state.bde_window_statuses(conn, "2026-09-13")
    assert len(statuses) == 3
    assert set(statuses.values()) == {"OPEN", "ENDED"}
    cir_uid = conn.execute(
        "SELECT consultation_uid FROM bde_consultations WHERE title_normalized LIKE '%(cir)%'"
    ).fetchone()[0]
    assert statuses[cir_uid] == "ENDED"
    membership = conn.execute(
        "SELECT count(*) FROM bde_snapshot_memberships WHERE consultation_uid = ?", (cir_uid,)
    ).fetchone()[0]
    assert membership >= 1


def test_invalid_bde_structure_cannot_remove_all_consultations(fresh_dir):
    fetch_a = make_fetch("2025-12-29", "sum_20251229.xml")
    run("2025-12-29", fresh_dir, fetch_a)
    conn = db(fresh_dir)
    assert conn.execute("SELECT count(*) FROM bde_consultations").fetchone()[0] == 3

    fetch_b = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch_b.set_url("consultas-publicas", b"<html><body>challenge shell</body></html>",
                    "text/html; charset=utf-8")
    summary = run("2025-12-29", fresh_dir, fetch_b)
    assert _consultas_result(summary)["status"] == "PARSE_INVALID"

    statuses = state.bde_window_statuses(conn, "2026-09-13")
    assert len(statuses) == 3
    assert state.bde_listing_removed(conn) == []
    assert conn.execute("SELECT count(*) FROM bde_snapshot_memberships").fetchone()[0] == 3


def test_http_200_shell_is_not_complete_snapshot(fresh_dir):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch.set_url("consultas-publicas", b"<html><body>shell 200 ok</body></html>",
                  "text/html; charset=utf-8")
    summary = run("2025-12-29", fresh_dir, fetch)
    result = _consultas_result(summary)
    assert result["status"] == "PARSE_INVALID"
    assert result["http_status"] == 200
    conn = db(fresh_dir)
    assert conn.execute(
        "SELECT parse_status FROM source_snapshots WHERE source_id = 'bde_consultas'"
    ).fetchone()[0] == "INVALID_STRUCTURE"
    assert conn.execute("SELECT count(*) FROM bde_snapshot_memberships").fetchone()[0] == 0


def test_fetch_error_creates_check_without_snapshot(fresh_dir):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch.set_url("consultas-publicas", None, error_class="NetworkError")
    summary = run("2025-12-29", fresh_dir, fetch)
    result = _consultas_result(summary)
    assert result["status"] == "FETCH_ERROR"
    conn = db(fresh_dir)
    row = conn.execute(
        "SELECT snapshot_id, error_class FROM source_checks WHERE source_id = 'bde_consultas'"
    ).fetchone()
    assert row[0] is None
    assert row[1] == "NetworkError"
    assert summary["exit_code"] == 3


def test_ids_full_hex_and_deterministic(fresh_dir):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    first = run("2025-12-29", fresh_dir, fetch)
    second = run("2025-12-29", fresh_dir, fetch)
    for s1, s2 in zip(first["sources"], second["sources"]):
        assert s1["snapshot_id"] == s2["snapshot_id"]
        assert len(s1["snapshot_id"]) == 64
        int(s1["snapshot_id"], 16)


def test_no_event_emission(fresh_dir):
    import regdelta.db as dbm
    assert "change_event" not in dbm.SCHEMA
    summary = run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    assert "events" not in summary
    assert all("events" not in s for s in summary["sources"])


def test_madrid_date_boundaries():
    from datetime import datetime, timezone
    assert madrid_local_date(datetime(2026, 1, 13, 10, 45, tzinfo=timezone.utc)).isoformat() == "2026-01-13"
    assert madrid_local_date(datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)).isoformat() == "2026-07-01"
    assert madrid_local_date(datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc)).isoformat() == "2026-03-29"
    assert madrid_local_date(datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)).isoformat() == "2026-03-29"
    assert madrid_local_date(datetime(2026, 10, 25, 0, 59, tzinfo=timezone.utc)).isoformat() == "2026-10-25"
    assert madrid_local_date(datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)).isoformat() == "2026-10-25"


def test_duplicate_consultation_in_snapshot_becomes_anomaly(fresh_dir):
    import re

    text = load("bde_pi.html").decode("utf-8")
    cir_title = re.search(r"<strong>(Audiencia p[^<]*\(CIR\)\.)", text).group(1)
    cont_title = re.search(r"<strong>(Audiencia e[^<]*contables\.)", text).group(1)
    mutated_text = text.replace(cont_title, cir_title, 1).replace("04/09/2026", "08/06/2026", 1)
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch.set_url("consultas-publicas", mutated_text.encode("utf-8"), "text/html; charset=utf-8")
    summary = run("2025-12-29", fresh_dir, fetch)
    result = _consultas_result(summary)
    assert result["status"] == "OK_WITH_ANOMALIES"
    assert len(result["anomalies"]) == 1
    assert summary["exit_code"] == 2
    conn = db(fresh_dir)
    assert conn.execute(
        "SELECT has_anomalies FROM source_snapshots WHERE snapshot_id = ?",
        (result["snapshot_id"],),
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT count(*) FROM bde_snapshot_memberships WHERE snapshot_id = ?",
        (result["snapshot_id"],),
    ).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM bde_consultations").fetchone()[0] == 0


@pytest.fixture(params=["boe_sumario", "bde_consultas"])
def anomalous_source(request):
    if request.param == "boe_sumario":
        root = ET.fromstring(load("sum_20251229.xml"))
        department = root.find(".//departamento[@codigo='1020']")
        item = next(department.iter("item"))
        department.append(item)
        return "boe/sumario/20251229", ET.tostring(root), "application/xml", _sumario_result
    text = load("bde_pi.html").decode("utf-8")
    cir_title = re.search(r"<strong>(Audiencia p[^<]*\(CIR\)\.)", text).group(1)
    cont_title = re.search(r"<strong>(Audiencia e[^<]*contables\.)", text).group(1)
    text = text.replace(cont_title, cir_title, 1).replace("04/09/2026", "08/06/2026", 1)
    return "consultas-publicas", text.encode("utf-8"), "text/html; charset=utf-8", _consultas_result


def test_repeated_anomalous_snapshot_still_exits_2_without_rewriting(fresh_dir, anomalous_source):
    needle, body, media_type, result_for = anomalous_source
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch.set_url(needle, body, media_type)
    first = run("2025-12-29", fresh_dir, fetch)
    conn = db(fresh_dir)
    before = counts(conn)
    anomalies = conn.execute("SELECT * FROM anomalies ORDER BY anomaly_id").fetchall()
    snapshots = conn.execute("SELECT * FROM source_snapshots ORDER BY snapshot_id").fetchall()
    for _ in range(2):
        repeated = run("2025-12-29", fresh_dir, fetch)
        result = result_for(repeated)
        assert repeated["exit_code"] == first["exit_code"] == 2
        assert result["status"] == "OK_WITH_ANOMALIES"
        assert result["anomalies"] == result_for(first)["anomalies"]
        assert result["snapshot_id"] == result_for(first)["snapshot_id"]
        assert result["snapshot_new"] is False
        assert result["entities_new"] == 0
    after = counts(conn)
    assert after.pop("source_checks") == before.pop("source_checks") + 4
    assert after == before
    assert conn.execute("SELECT * FROM anomalies ORDER BY anomaly_id").fetchall() == anomalies
    assert conn.execute("SELECT * FROM source_snapshots ORDER BY snapshot_id").fetchall() == snapshots


def test_same_anomaly_different_bytes_has_snapshot_scoped_ids(fresh_dir, anomalous_source):
    needle, body, media_type, result_for = anomalous_source
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    results = []
    for variant in (body, body + b"\n"):
        fetch.set_url(needle, variant, media_type)
        summary = run("2025-12-29", fresh_dir, fetch)
        assert summary["exit_code"] == 2
        result = result_for(summary)
        assert result["status"] == "OK_WITH_ANOMALIES"
        assert result["snapshot_new"] is True
        assert result["entities_new"] == 0
        assert len(result["anomalies"]) == 1
        results.append(result)
    assert results[0]["snapshot_id"] != results[1]["snapshot_id"]
    assert results[0]["anomalies"] != results[1]["anomalies"]
    conn = db(fresh_dir)
    rows = conn.execute("SELECT anomaly_id, snapshot_id, detail FROM anomalies").fetchall()
    assert len(rows) == 2
    assert rows[0][2] == rows[1][2]
    assert {(row[0], row[1]) for row in rows} == {
        (result["anomalies"][0], result["snapshot_id"]) for result in results
    }


@pytest.mark.parametrize("missing_anomaly_row", [False, True])
def test_legacy_anomaly_flag_remains_non_ok_without_history_rewrite(
    fresh_dir, anomalous_source, missing_anomaly_row
):
    needle, body, media_type, result_for = anomalous_source
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch.set_url(needle, body, media_type)
    run("2025-12-29", fresh_dir, fetch)
    conn = db(fresh_dir)
    kind, detail = conn.execute("SELECT kind, detail FROM anomalies").fetchone()
    legacy_id = sha256_hex_text(f"anomaly|{kind}|{detail}")
    if missing_anomaly_row:
        conn.execute("DELETE FROM anomalies")
    else:
        conn.execute("UPDATE anomalies SET anomaly_id = ?", (legacy_id,))
    conn.commit()
    before = conn.execute("SELECT * FROM anomalies").fetchall()
    snapshots = conn.execute("SELECT * FROM source_snapshots ORDER BY snapshot_id").fetchall()
    summary = run("2025-12-29", fresh_dir, fetch)
    assert summary["exit_code"] == 2
    assert result_for(summary)["status"] == "OK_WITH_ANOMALIES"
    assert result_for(summary)["anomalies"] == ([] if missing_anomaly_row else [legacy_id])
    assert conn.execute("SELECT * FROM anomalies").fetchall() == before
    assert conn.execute("SELECT * FROM source_snapshots ORDER BY snapshot_id").fetchall() == snapshots


@pytest.mark.parametrize("problem", ["FETCH_ERROR", "PARSE_INVALID"])
def test_source_error_exit_3_takes_precedence_over_anomaly_exit_2(
    fresh_dir, anomalous_source, problem
):
    needle, body, media_type, result_for = anomalous_source
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    fetch.set_url(needle, body, media_type)
    other = "consultas-publicas" if needle.startswith("boe/") else "boe/sumario/20251229"
    if problem == "FETCH_ERROR":
        fetch.set_url(other, None, error_class="NetworkError")
    else:
        fetch.set_url(other, b"invalid structure")
    for _ in range(2):
        summary = run("2025-12-29", fresh_dir, fetch)
        assert summary["exit_code"] == 3
        assert result_for(summary)["status"] == "OK_WITH_ANOMALIES"
        assert result_for(summary)["anomalies"]
        assert {result["status"] for result in summary["sources"]} == {problem, "OK_WITH_ANOMALIES"}


@pytest.mark.parametrize("needle", ["boe/sumario/20251229", "consultas-publicas"])
@pytest.mark.parametrize("response", ["success", "network_error", "http_error"])
@pytest.mark.parametrize("via", [EVIDENCE_IMPORT, "UNKNOWN", ""])
def test_non_live_fetch_rejected_before_raw_or_check_writes(
    fresh_dir, monkeypatch, needle, response, via
):
    fetch = make_fetch("2025-12-29", "sum_20251229.xml")
    if response == "network_error":
        fetch.set_url(needle, None, error_class="NetworkError")
    elif response == "http_error":
        fetch.set_url(needle, None, http_status=503)
    rejected_bodies = []
    stored_bodies = []
    store_blob = watcher.store_blob

    def guarded_store(data_dir, body):
        stored_bodies.append(body)
        return store_blob(data_dir, body)

    def replay_fetch(url, accept):
        result = fetch(url, accept)
        if needle in url:
            rejected_bodies.append(result.body)
            return replace(result, via=via)
        return result

    monkeypatch.setattr(watcher, "store_blob", guarded_store)
    with pytest.raises(ValueError, match="LIVE_FETCH"):
        run("2025-12-29", fresh_dir, replay_fetch)
    assert len(rejected_bodies) == 1
    assert rejected_bodies[0] not in stored_bodies
    if rejected_bodies[0] is not None:
        assert not blob_path(fresh_dir, sha256_hex(rejected_bodies[0])).exists()
    assert set(counts(db(fresh_dir)).values()) == {0}


@pytest.mark.parametrize("date_iso", [
    "", "20251229", "2025-1-02", "2025-01-2", "2025-W01-1",
    "2025-12-29T00:00:00", " 2025-12-29", "2025-12-29\n",
    "２０２５-１２-２９", "2025-02-29", "2024-02-30", "2025-13-01",
    "2025-01-00", "0000-01-01", "../../2025-12-29",
])
def test_invalid_date_has_no_directory_database_or_network_effects(tmp_path, monkeypatch, date_iso):
    data_dir = tmp_path / "not-created"
    fetch = Mock(side_effect=AssertionError("network effect"))
    connect = Mock(side_effect=AssertionError("database effect"))
    mkdir = Mock(side_effect=AssertionError("directory effect"))
    monkeypatch.setattr(watcher.dbm, "connect", connect)
    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(ValueError):
        run(date_iso, data_dir, fetch)
    fetch.assert_not_called()
    connect.assert_not_called()
    mkdir.assert_not_called()
    assert not data_dir.exists()
