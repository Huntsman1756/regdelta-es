"""G0-F representation-aware diff.

Answers: which explicitly published modification relations inside a
publication window have comparable representations, and what can be
demonstrated about each before→after. One modification_relation is one
representation-aware delta — never a synthesized net diff, never a
consolidated text, never OCR or pixel comparison.

Selection basis is publication_date only, ``from < pub <= to``
(AFTER_FROM_THROUGH_TO): --from is the comparison baseline, so a change
published that day already belongs to the initial side. Applicability
dates are deliberately not consulted.

Read-only projection over the persisted ledger: no network, no writes,
no schema changes.
"""

from __future__ import annotations

import difflib
import sqlite3
from datetime import date

from . import query

SEMANTICS = ("REPRESENTATION_DELTAS_FOR_RELATIONS_PUBLISHED_"
             "AFTER_FROM_THROUGH_TO")

VISUAL_KINDS = ("IMAGE", "PDF_PAGE")
TEXTUAL_KINDS = ("TEXT", "TABLE")

TEXT_LINE_DIFF = "TEXT_LINE_DIFF"
TABLE_ROW_DIFF = "TABLE_ROW_DIFF"
DECLARED_ADDITION = "DECLARED_ADDITION"
DECLARED_DELETION = "DECLARED_DELETION"
REPRESENTATION_KIND_CHANGE = "REPRESENTATION_KIND_CHANGE"
VISUAL_REPRESENTATION_CHANGE = "VISUAL_REPRESENTATION_CHANGE"
VISUAL_PREDECESSOR = "VISUAL_PREDECESSOR"
INSUFFICIENT = "INSUFFICIENT_REPRESENTATION_EVIDENCE"

_BASIS = {
    TEXT_LINE_DIFF: "persisted_text_lines",
    TABLE_ROW_DIFF: "persisted_table_rows",
    DECLARED_ADDITION: "declared_operation",
    DECLARED_DELETION: "declared_operation",
    REPRESENTATION_KIND_CHANGE: "representation_kinds",
    VISUAL_REPRESENTATION_CHANGE: "artifact_locators",
    VISUAL_PREDECESSOR: "artifact_locators",
    INSUFFICIENT: "resolution",
}

_DIFFABLE = (TEXT_LINE_DIFF, TABLE_ROW_DIFF)

# query._REL_SELECT plus the fields a delta needs: declared literals and
# the relation-level snapshot provenance
_REL_SELECT = query._REL_SELECT.replace(
    "mr.diff_levels,",
    "mr.diff_levels, mr.declared_literals, mr.source_snapshot_ids,")


# ---------------------------------------------------------------------------
# representation + evidence projection
# ---------------------------------------------------------------------------


def _artifact_hashes(locator: dict) -> list[str]:
    """True per-page artifact blob sha256s from the locator, in page
    order. Never confused with the locator-derived representation
    fingerprint."""
    out: list[str] = []
    for p in locator.get("pages") or []:
        h = p.get("blob_sha256") if isinstance(p, dict) else None
        if h and h not in out:
            out.append(h)
    return out


def _rep(conn, rep_id: str | None) -> dict | None:
    if rep_id is None:
        return None
    row = query._one(conn, """
        SELECT r.representation_id, r.representation_kind,
               r.content_sha256, r.text_content, r.artifact_locator,
               r.source_snapshot_id, r.binding, s.blob_sha256
        FROM representations r
        JOIN source_snapshots s
          ON s.snapshot_id = r.source_snapshot_id
        WHERE r.representation_id = ?""", (rep_id,))
    if row is None:
        return None
    locator = query._loads(row["artifact_locator"]) or {}
    return {
        "representation_id": row["representation_id"],
        "representation_kind": row["representation_kind"],
        "representation_fingerprint": row["content_sha256"],
        "binding": row["binding"],
        "source_snapshot_id": row["source_snapshot_id"],
        "artifact_locator": locator,
        "artifact_hashes": _artifact_hashes(locator),
        # internal fields, stripped before output
        "_text": row["text_content"],
        "_source_blob": row["blob_sha256"],
    }


def _evidence(side: dict | None) -> dict | None:
    if side is None:
        return None
    ev = {"source_snapshot_id": side["source_snapshot_id"],
          "source_blob_sha256": side["_source_blob"]}
    if side["artifact_hashes"]:
        ev["artifact_blob_sha256s"] = side["artifact_hashes"]
    return ev


# ---------------------------------------------------------------------------
# strategy + comparison
# ---------------------------------------------------------------------------


def _strategy(op: str, bk: str | None, ak: str | None) -> str:
    """before_kind x after_kind x operation_kind -> strategy.

    A missing side is a declared operation only when the operation kind
    says so; otherwise it is missing evidence, never an empty-string diff.
    """
    if bk is None and ak is None:
        return INSUFFICIENT
    if op == "ADD" and bk is None:
        return DECLARED_ADDITION
    if op == "DELETE" and ak is None:
        return DECLARED_DELETION
    if bk is None or ak is None:
        return INSUFFICIENT
    if bk == ak == "TEXT":
        return TEXT_LINE_DIFF
    if bk == ak == "TABLE":
        return TABLE_ROW_DIFF
    if bk in VISUAL_KINDS and ak in VISUAL_KINDS:
        return VISUAL_REPRESENTATION_CHANGE
    if bk in VISUAL_KINDS and ak in TEXTUAL_KINDS:
        return VISUAL_PREDECESSOR
    return REPRESENTATION_KIND_CHANGE


def _line_hunks(before_text: str, after_text: str) -> tuple[list, dict]:
    """Deterministic stdlib line diff over persisted representations.
    Ranges are 0-based half-open; 'equal' opcodes are never emitted."""
    bl = (before_text or "").splitlines()
    al = (after_text or "").splitlines()
    sm = difflib.SequenceMatcher(a=bl, b=al, autojunk=False)
    hunks = []
    stats = {"inserted_lines": 0, "deleted_lines": 0,
             "replaced_before_lines": 0, "replaced_after_lines": 0}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        hunks.append({"tag": tag,
                      "before_range": [i1, i2],
                      "after_range": [j1, j2],
                      "before_lines": bl[i1:i2],
                      "after_lines": al[j1:j2]})
        if tag == "insert":
            stats["inserted_lines"] += j2 - j1
        elif tag == "delete":
            stats["deleted_lines"] += i2 - i1
        else:
            stats["replaced_before_lines"] += i2 - i1
            stats["replaced_after_lines"] += j2 - j1
    stats["hunk_count"] = len(hunks)
    return hunks, stats


def _comparison(strategy: str, before: dict | None,
                after: dict | None) -> dict:
    cmp_ = {"strategy": strategy,
            "basis": _BASIS[strategy],
            "content_diff_available": strategy in _DIFFABLE,
            "content_changed": None,
            "stats": None,
            "hunks": []}
    if strategy in _DIFFABLE:
        hunks, stats = _line_hunks(before["_text"], after["_text"])
        cmp_["hunks"] = hunks
        cmp_["stats"] = stats
        cmp_["content_changed"] = bool(hunks)
    elif strategy == VISUAL_REPRESENTATION_CHANGE:
        cmp_["content_changed"] = (
            before["artifact_hashes"] != after["artifact_hashes"]
            or before["representation_fingerprint"]
            != after["representation_fingerprint"])
    return cmp_


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------


def diff(conn: sqlite3.Connection, *, target: str, from_date: date,
         to_date: date, subject: str | None = None) -> dict:
    """One representation-aware delta per modification_relation whose
    publication_date falls in (from_date, to_date]."""
    if to_date < from_date:
        raise query.InvalidDateRange(
            f"to {to_date} < from {from_date}")
    inst = query.resolve_instrument(conn, target)
    if subject is not None:
        query._resolve_subject(conn, inst["instrument_id"], subject)
    rows = query._q(conn, _REL_SELECT + """
        WHERE s.instrument_id = ?
          AND mr.publication_date > ?
          AND mr.publication_date <= ?
          AND (? IS NULL OR s.locator_key = ?)
        ORDER BY mr.publication_date, mi.boe_id,
                 s.locator_key, mr.relation_id""",
        (inst["instrument_id"], from_date.isoformat(),
         to_date.isoformat(), subject, subject))

    results = []
    by_strategy: dict[str, int] = {}
    by_resolution: dict[str, int] = {}
    for r in rows:
        rel = query._relation_payload(r)
        rel["declared_literals"] = query._loads(r["declared_literals"])
        before = _rep(conn, r["before_representation_id"])
        after = _rep(conn, r["after_representation_id"])
        strategy = _strategy(
            r["operation_kind"],
            before["representation_kind"] if before else None,
            after["representation_kind"] if after else None)
        rel["before"] = ({k: v for k, v in before.items()
                          if not k.startswith("_")}
                         if before else None)
        rel["after"] = ({k: v for k, v in after.items()
                         if not k.startswith("_")}
                        if after else None)
        rel["comparison"] = _comparison(strategy, before, after)
        rel["evidence"] = {
            "relation_source_snapshots": (
                query._loads(r["source_snapshot_ids"]) or []),
            "before": _evidence(before),
            "after": _evidence(after)}
        # _relation_payload's compact id/kind pair is superseded by the
        # full representation objects above
        del rel["before_representation"]
        del rel["after_representation"]
        by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
        by_resolution[r["resolution"]] = (
            by_resolution.get(r["resolution"], 0) + 1)
        results.append(rel)

    return {
        "schema": "regdelta.query.diff/v1",
        "semantics": SEMANTICS,
        "query": {"target": target,
                  "resolved_boe_id": inst["boe_id"],
                  "from": from_date.isoformat(),
                  "to": to_date.isoformat(),
                  "subject": subject},
        "summary": {"relation_count": len(results),
                    "subject_count": len(
                        {r["target"]["locator_key"] for r in results}),
                    "by_strategy": by_strategy,
                    "by_resolution": by_resolution},
        "results": results,
    }
