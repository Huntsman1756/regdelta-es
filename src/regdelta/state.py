from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .util import madrid_local_date

BOE_SUMARIO = "boe_sumario"
BDE_CONSULTAS = "bde_consultas"


def latest_complete_snapshot_id(conn: sqlite3.Connection, source_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT s.snapshot_id
        FROM source_checks c
        JOIN source_snapshots s ON s.snapshot_id = c.snapshot_id
        WHERE c.source_id = ? AND s.parse_status = 'COMPLETE' AND s.has_anomalies = 0
        ORDER BY c.checked_at DESC
        LIMIT 1
        """,
        (source_id,),
    ).fetchone()
    return row[0] if row else None


def bde_window_statuses(
    conn: sqlite3.Connection, as_of_date_iso: str | None = None
) -> dict[str, str]:
    if as_of_date_iso is None:
        as_of_date_iso = madrid_local_date(datetime.now(timezone.utc)).isoformat()
    snapshot_id = latest_complete_snapshot_id(conn, BDE_CONSULTAS)
    if snapshot_id is None:
        return {}
    statuses: dict[str, str] = {}
    rows = conn.execute(
        "SELECT consultation_uid, consultation_end_on FROM bde_snapshot_memberships WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchall()
    for uid, consultation_end_on in rows:
        if consultation_end_on is None:
            statuses[uid] = "UNKNOWN"
        elif as_of_date_iso <= consultation_end_on:
            statuses[uid] = "OPEN"
        else:
            statuses[uid] = "ENDED"
    return statuses


def bde_listing_removed(conn: sqlite3.Connection) -> list[str]:
    snapshot_id = latest_complete_snapshot_id(conn, BDE_CONSULTAS)
    if snapshot_id is None:
        return []
    latest_uids = {
        row[0]
        for row in conn.execute(
            "SELECT consultation_uid FROM bde_snapshot_memberships WHERE snapshot_id = ?",
            (snapshot_id,),
        )
    }
    return [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT consultation_uid FROM bde_snapshot_memberships"
        )
        if row[0] not in latest_uids
    ]
