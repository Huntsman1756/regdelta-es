"""COV-2 F1: sub-scoped operations still bind the `before` side.

A clause acting below the recorded locator's granularity ("el fichero
X en su apartado «Y»", "la nota (b) del estado FI 132") cannot prove
the `after` of the whole subject, but the subject's representation
immediately before the operation is ordinary subject state — provable
through the normal before paths (unique structural candidate or chain
predecessor).  The `after` side and the chain state stay fail-closed.

Each test reconstructs a DEV target purely from the frozen evidence
manifest.  Target/locator literals are test data (permitted); runtime
code must stay free of them.
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
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402

MANIFEST = ROOT / "evidence" / "g2" / "dev" / "manifest.json"

pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(), reason="G2 dev evidence not captured")

_BY_URL: dict[str, dict] = {}
if MANIFEST.exists():
    _m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for e in _m["entries"].values():
        _BY_URL[e["url"]] = e


def _fetch(url: str, accept: str) -> FetchResult:
    e = _BY_URL.get(url)
    if e is None or "path" not in e:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in dev evidence", via=EVIDENCE_IMPORT)
    return FetchResult(url, 200, "application/octet-stream",
                       (ROOT / e["path"]).read_bytes(), None, None,
                       via=EVIDENCE_IMPORT)


def _build(tmp_path: Path, target: str) -> sqlite3.Connection:
    conn = dbm.connect(tmp_path / "r.sqlite")
    conn.row_factory = sqlite3.Row
    report = history.reconstruct(conn, tmp_path, target, _fetch)
    conn.commit()
    assert "error" not in report, report.get("error")
    return conn


def _rels(conn) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT mr.*, s.locator_key FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           ORDER BY mr.publication_date, mr.relation_id""").fetchall()


def _proof(r: sqlite3.Row) -> dict:
    return json.loads(r["binding_proof"])


def _scope_failed(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Relations whose operative clause scopes below the recorded
    locator: the runtime marks the gated `after` side with
    method=SUBJECT_SCOPE."""
    return [r for r in rows
            if _proof(r).get("after", {}).get("method")
            == "SUBJECT_SCOPE"]


def test_subscoped_before_side_is_not_scope_gated(tmp_path):
    """The before side must go through the normal binding paths for a
    scope-failed operation: structural enumeration or chain, never an
    upfront SUBJECT_SCOPE abstention."""
    conn = _build(tmp_path, "BOE-A-2005-4749")
    failed = _scope_failed(_rels(conn))
    assert failed, "expected sub-scoped operations in this target"
    for r in failed:
        before = _proof(r)["before"]
        assert before.get("method") != "SUBJECT_SCOPE", (
            r["locator_key"], before)
    conn.close()


def test_subscoped_fichero_before_binds(tmp_path):
    """'Se modifica el fichero «X» en su apartado «Y»': the fichero
    description block in the target annex is the subject's
    before-representation and binds under B1/B2."""
    conn = _build(tmp_path, "BOE-A-2005-4749")
    rows = [r for r in _scope_failed(_rels(conn))
            if r["locator_key"].startswith("fichero:")]
    assert rows
    bound = [r for r in rows
             if _proof(r)["before"].get("status") == "BOUND"]
    assert bound, "no sub-scoped fichero bound its before side"
    for r in bound:
        before = _proof(r)["before"]
        assert before.get("candidate_count") == 1
    conn.close()


def test_subscoped_after_stays_gated(tmp_path):
    """The after side of a scope-failed operation remains
    NOT_PROVABLE: operation-owned content must be attributable to the
    recorded subject scope (B3)."""
    conn = _build(tmp_path, "BOE-A-2005-4749")
    for r in _scope_failed(_rels(conn)):
        after = _proof(r)["after"]
        assert after.get("status") in (
            "NOT_PROVABLE", "NOT_FOUND", "AMBIGUOUS",
            "NOT_APPLICABLE"), (r["locator_key"], after)
    conn.close()


def test_subscoped_chain_does_not_fabricate_present(tmp_path):
    """A scope-failed hop must not mark the chain PRESENT: later hops
    on the same key keep abstaining CHAIN_STATE instead of resurrecting
    a representation the runtime cannot prove."""
    conn = _build(tmp_path, "BOE-A-2017-14334")
    rows = [r for r in _rels(conn) if r["locator_key"] == "estado:FI 132"]
    assert len(rows) > 1, "expected a multi-hop chain for the subject"
    # at most one hop may bind before (the first-processed one, via a
    # structural/annex path); every later hop must see chain UNKNOWN
    # and abstain CHAIN_STATE — the scope-failed hop must not have
    # fabricated a PRESENT state
    bound = [_proof(r)["before"] for r in rows
             if _proof(r)["before"].get("status") == "BOUND"]
    assert len(bound) <= 1, bound
    for b in bound:
        assert b.get("method") != "CHAIN_PREDECESSOR"
    others = [_proof(r)["before"] for r in rows
              if _proof(r)["before"].get("status") != "BOUND"]
    assert all(b.get("method") == "CHAIN_STATE" for b in others), others
    conn.close()


def test_subscoped_delete_binds_before_but_not_deleted_state(tmp_path):
    """norma:11 is substituted (bound) then partially deleted by a
    sub-scoped clause: the DELETE may bind before through the proven
    chain predecessor, but the chain must become UNKNOWN — never
    DELETED — because the subject itself was not deleted."""
    conn = _build(tmp_path, "BOE-A-2014-1183")
    rows = [r for r in _rels(conn) if r["locator_key"] == "norma:11"]
    delete = [r for r in rows if r["operation_kind"] == "DELETE"]
    assert delete
    sub_rid = next(r["relation_id"] for r in rows
                   if r["operation_kind"] == "SUBSTITUTE")
    chain_bound = [r for r in rows
                   if _proof(r)["before"].get("method")
                   == "CHAIN_PREDECESSOR"]
    assert chain_bound, "no hop bound before via chain predecessor"
    for r in chain_bound:
        assert _proof(r)["before"].get(
            "predecessor_relation_id") == sub_rid
    # every later hop that cannot chain must report UNKNOWN, never
    # DELETED — the sub-scoped delete did not delete the subject
    for r in rows:
        before = _proof(r)["before"]
        if before.get("method") == "CHAIN_STATE":
            assert "DELETED" not in (before.get("reason") or ""), before
    conn.close()


def test_every_newly_bound_before_is_unique(tmp_path):
    """B1 guard: any before BOUND under a scope-failed operation comes
    from a unique candidate or a proven chain predecessor — never a
    first-match."""
    conn = _build(tmp_path, "BOE-A-2017-14334")
    for r in _scope_failed(_rels(conn)):
        before = _proof(r)["before"]
        if before.get("status") == "BOUND":
            assert before.get("candidate_count") == 1 or (
                before.get("method") == "CHAIN_PREDECESSOR"
                and before.get("predecessor_relation_id")), (
                r["locator_key"], before)
    conn.close()
