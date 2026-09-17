"""G1 §47: modification_relations.binding_proof migration."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from regdelta import db as dbm


def _legacy_db(path: Path) -> None:
    """A pre-G1 database: same tables, no binding_proof column."""
    sql = dbm.SCHEMA.replace(
        "  binding_proof          TEXT NOT NULL DEFAULT '{}',\n", "")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(sql)
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(modification_relations)")}
        assert "binding_proof" not in cols
        conn.execute(
            "INSERT INTO source_blobs (sha256, size_bytes, stored_at)"
            " VALUES (?, 1, 't')", ("a" * 64,))
        conn.execute(
            "INSERT INTO source_snapshots (snapshot_id, source_id,"
            " source_url, blob_sha256, parse_status, parser_name,"
            " parser_version, has_anomalies, first_checked_at)"
            " VALUES (?, 'boe_diario', 'u', ?, 'COMPLETE', 'p', 'v', 0,"
            " 't')", ("b" * 64, "a" * 64))
        conn.execute(
            "INSERT INTO instruments (instrument_id, boe_id, titulo,"
            " origin, snapshot_id) VALUES (?, 'BOE-A-X', 't', 'PARSED',"
            " ?)", ("c" * 64, "b" * 64))
        conn.execute(
            "INSERT INTO subjects (subject_id, instrument_id,"
            " locator_key, label, subject_kind) VALUES (?, ?,"
            " 'norma:1', 'n', 'NORMA')", ("d" * 64, "c" * 64))
        conn.execute(
            "INSERT INTO modification_relations (relation_id, kind,"
            " operation_kind, target_subject_id,"
            " modifier_instrument_id, locator_raw, publication_date,"
            " diff_levels, resolution, source_snapshot_ids,"
            " parser_name, parser_version)"
            " VALUES (?, 'MODIFICATION', 'MODIFY', ?, ?, 'c',"
            " '2020-01-01', '[]', 'UNRESOLVED', '[]', 'history', 'v2')",
            ("e" * 64, "d" * 64, "c" * 64))
        conn.commit()
    finally:
        conn.close()


def test_old_db_migrates_and_preserves_rows(tmp_path):
    p = tmp_path / "r.sqlite"
    _legacy_db(p)
    conn = dbm.connect(p)
    try:
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(modification_relations)")}
        assert "binding_proof" in cols
        rows = conn.execute(
            "SELECT relation_id, binding_proof"
            " FROM modification_relations").fetchall()
        assert rows == [("e" * 64, "{}")]
        assert conn.execute(
            "PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    # reopen repeatedly: idempotent
    conn = dbm.connect(p)
    try:
        assert conn.execute(
            "SELECT binding_proof FROM modification_relations"
            ).fetchone()[0] == "{}"
    finally:
        conn.close()


def test_fresh_db_has_column(tmp_path):
    conn = dbm.connect(tmp_path / "r.sqlite")
    try:
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(modification_relations)")}
        assert "binding_proof" in cols
    finally:
        conn.close()
