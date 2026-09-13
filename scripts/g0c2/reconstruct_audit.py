#!/usr/bin/env python
"""G0-C.2 reconstruction audit: rebuild the Circular 4/2017 history from
captured evidence and dump deterministic stats to JSON.

Usage:
  uv run python -X utf8 scripts/g0c2/reconstruct_audit.py OUT.json
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from regdelta import db as dbm, history  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402

TARGET = "BOE-A-2017-14334"
MANIFESTS = [
    REPO / "evidence" / "g0c" / "raw" / "manifest.json",
    REPO / "evidence" / "g0c1" / "raw" / "manifest.json",
    REPO / "evidence" / "g0c2" / "raw" / "manifest.json",
]

_BY_URL: dict[str, dict] = {}
for mp in MANIFESTS:
    if mp.exists():
        for e in json.loads(mp.read_text(encoding="utf-8"))[
                "entries"].values():
            _BY_URL[e["url"]] = e


def _evidence_fetch(url: str, accept: str) -> FetchResult:
    entry = _BY_URL.get(url)
    if entry is None:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in captured evidence",
                           via=EVIDENCE_IMPORT)
    return FetchResult(url, 200, "application/octet-stream",
                       (REPO / entry["path"]).read_bytes(), None, None,
                       via=EVIDENCE_IMPORT)


def run() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        conn = dbm.connect(Path(tmp) / "regdelta.sqlite")
        conn.row_factory = sqlite3.Row
        report = history.reconstruct(conn, Path(tmp), TARGET,
                                     _evidence_fetch)
        conn.commit()

        def rows(sql, *a):
            return conn.execute(sql, a).fetchall()

        relations = [dict(r) for r in rows(
            """SELECT m.relation_id, m.kind, m.operation_kind, m.resolution,
                      s.locator_key, i.boe_id AS modifier_boe
               FROM modification_relations m
               JOIN subjects s ON s.subject_id = m.target_subject_id
               JOIN instruments i
                    ON i.instrument_id = m.modifier_instrument_id""")]
        out = {
            "report": {k: v for k, v in report.items()
                       if k != "anomalies"},
            "anomaly_count": len(report.get("anomalies") or []),
            "counts": {
                t: rows(f"SELECT COUNT(*) FROM {t}")[0][0]
                for t in ("instruments", "subjects", "representations",
                          "modification_relations", "anomalies")
            },
            "resolution": dict(rows(
                "SELECT resolution, COUNT(*) FROM modification_relations"
                " GROUP BY 1")),
            "op_x_res": [list(r) for r in rows(
                "SELECT operation_kind, resolution, COUNT(*)"
                " FROM modification_relations GROUP BY 1, 2")],
            "anomaly_kinds": dict(rows(
                "SELECT kind, COUNT(*) FROM anomalies GROUP BY 1")),
            "relations": relations,
            "subjects": sorted(r[0] for r in rows(
                "SELECT locator_key FROM subjects")),
        }
        conn.close()
        return out


def main() -> int:
    out = run()
    Path(sys.argv[1]).write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps({k: out[k] for k in
                      ("counts", "resolution", "anomaly_kinds")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
