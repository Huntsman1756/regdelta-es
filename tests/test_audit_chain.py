from __future__ import annotations

from pathlib import Path

from regdelta.rawstore import blob_path
from regdelta.util import sha256_hex
from regdelta.watcher import run
from conftest import db, make_fetch


def test_audit_chain_offline_run(fresh_dir):
    summary = run("2025-12-29", fresh_dir, make_fetch("2025-12-29", "sum_20251229.xml"))
    assert summary["exit_code"] == 0
    conn = db(fresh_dir)

    placements = conn.execute(
        "SELECT p.item_uid, s.blob_sha256 FROM boe_item_placements p"
        " JOIN source_snapshots s ON s.snapshot_id = p.snapshot_id"
    ).fetchall()
    assert placements
    for item_uid, blob_sha in placements:
        raw_file = blob_path(Path(fresh_dir), blob_sha)
        assert raw_file.exists()
        raw = raw_file.read_bytes()
        assert sha256_hex(raw) == blob_sha
        text = raw.decode("utf-8")
        assert item_uid in text

    memberships = conn.execute(
        "SELECT m.title_raw, c.published_on, s.blob_sha256 FROM bde_snapshot_memberships m"
        " JOIN source_snapshots s ON s.snapshot_id = m.snapshot_id"
        " JOIN bde_consultations c ON c.consultation_uid = m.consultation_uid"
    ).fetchall()
    assert memberships
    for title_raw, published_on, blob_sha in memberships:
        raw_file = blob_path(Path(fresh_dir), blob_sha)
        assert raw_file.exists()
        raw = raw_file.read_bytes()
        assert sha256_hex(raw) == blob_sha
        text = raw.decode("utf-8")
        assert title_raw in text
        year, month, day = published_on.split("-")
        assert f"{day}/{month}/{year}" in text
