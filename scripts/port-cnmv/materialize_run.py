"""Materialize a dev-run envelope + persisted DBs into the prereg's
§10 run-directory layout:

    runs/<NNN>-<slug>/
      run.json          frozen run envelope (identity, env, adapter)
      metrics.json      per-target census (accounting, dispositions)
      operations.jsonl  one line per target: leaf-op inventory
      attribution.jsonl one line per relation: O1 attribution claim
      bindings.jsonl    one line per relation: before/after status
      audit.jsonl       anomalies (abstention register entries)
      failures.jsonl    evaluator findings for this run (may be empty)
      report.md         human-readable per-target summary

Deterministic: derives only from the run envelope JSON, the persisted
per-target sqlite DBs and the evaluator output — no re-parse.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _j(x):
    return json.dumps(x, ensure_ascii=False)


def materialize(run_json: Path, db_dir: Path, eval_json: Path | None,
                out_dir: Path) -> None:
    env = json.loads(run_json.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "run.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), "utf-8")

    metrics = {}
    ops_f = open(out_dir / "operations.jsonl", "w", encoding="utf-8")
    att_f = open(out_dir / "attribution.jsonl", "w", encoding="utf-8")
    bind_f = open(out_dir / "bindings.jsonl", "w", encoding="utf-8")
    audit_f = open(out_dir / "audit.jsonl", "w", encoding="utf-8")

    report_md = ["# PORT-CNMV-1 run " + env["run_id"], "",
                 "| target | modifiers | leaf ops | relations | "
                 "RESOLVED | PARTIAL | UNRESOLVED | anomalies |",
                 "|---|---|---|---|---|---|---|---|"]
    for t in env["targets"]:
        tgt = t["target"]
        rep = t.get("report") or {}
        cen = t.get("census") or {}
        if "error" in t:
            report_md.append(f"| {tgt} | ERROR | | | | | | |")
            continue
        res = cen.get("resolution_counts", {})
        redesignations = t.get("profile_limit_redesignations", [])
        metrics[tgt] = {
            "modifiers": rep.get("modifiers"),
            "leaf_operations": rep.get("operation_inventory", {})
                                  .get("leaf_operations_parsed"),
            # accounting identity (journal #17): operative candidates
            # = leaf ops emitted + redesignation spans excluded by the
            # profile abstention
            "operative_candidates":
                (rep.get("operation_inventory", {})
                 .get("leaf_operations_parsed") or 0)
                + len(redesignations),
            "profile_limit_redesignations": len(redesignations),
            "dispositions": rep.get("operation_inventory"),
            "relations": rep.get("relations"),
            "resolution_counts": res,
            "subjects": rep.get("subjects"),
            "representations": rep.get("representations"),
            "anomaly_count": rep.get("anomaly_count"),
            "fetch_errors": rep.get("fetch_errors"),
            "op_kind_counts": cen.get("op_kind_counts"),
            "subject_kinds": cen.get("subject_kinds"),
            "anomalies_by_kind": cen.get("anomalies_by_kind"),
        }
        ops_f.write(_j({"target": tgt,
                        "operation_inventory":
                            rep.get("operation_inventory"),
                        "op_kind_counts": cen.get("op_kind_counts"),
                        "subject_kinds": cen.get("subject_kinds")}) + "\n")
        report_md.append(
            f"| {tgt} | {rep.get('modifiers')} | "
            f"{rep.get('operation_inventory', {}).get('leaf_operations_parsed')} | "
            f"{rep.get('relations')} | {res.get('RESOLVED', 0)} | "
            f"{res.get('PARTIAL', 0)} | {res.get('UNRESOLVED', 0)} | "
            f"{rep.get('anomaly_count')} |")

        db_path = db_dir / tgt / "regdelta.sqlite"
        if not db_path.exists():
            continue
        conn = sqlite3.connect(db_path)
        for r in conn.execute(
                "SELECT m.relation_id, m.operation_kind, s.locator_key,"
                " m.resolution, m.subject_proof, m.binding_proof,"
                " i.boe_id FROM modification_relations m"
                " JOIN subjects s ON s.subject_id=m.target_subject_id"
                " JOIN instruments i"
                " ON i.instrument_id=m.modifier_instrument_id"):
            rid, opk, key, resol, sproof, bproof, mboe = r
            sp = json.loads(sproof or "{}")
            bp = json.loads(bproof or "{}")
            att_f.write(_j({
                "relation_id": rid, "target": tgt, "modifier": mboe,
                "subject": key, "operation_kind": opk,
                "attribution": sp.get("target_attribution", {})
                               .get("status"),
                "attribution_method": sp.get("target_attribution", {})
                                        .get("method")}) + "\n")
            bind_f.write(_j({
                "relation_id": rid, "target": tgt, "subject": key,
                "operation_kind": opk, "resolution": resol,
                "before": (bp.get("before") or {}).get("status")
                          or (bp.get("before") or {}).get("chosen", {})
                              .get("kind"),
                "after": (bp.get("after") or {}).get("status")
                         or (bp.get("after") or {}).get("chosen", {})
                             .get("kind"),
                "existence_before": (sp.get("existence_before") or {})
                                    .get("status")}) + "\n")
        for r in conn.execute(
                "SELECT kind, detail FROM anomalies"):
            audit_f.write(_j({"target": tgt, "kind": r[0],
                              "detail": json.loads(r[1] or "{}")}) + "\n")
        conn.close()
        for span in redesignations:
            audit_f.write(_j({"target": tgt,
                              "kind": "PROFILE_LIMIT_REDESIGNATION",
                              "detail": span}) + "\n")

    for f in (ops_f, att_f, bind_f, audit_f):
        f.close()

    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")

    failures = []
    if eval_json is not None and eval_json.exists():
        ev = json.loads(eval_json.read_text(encoding="utf-8"))
        failures = ev.get("findings", [])
        (out_dir / "evaluator.json").write_text(
            json.dumps(ev.get("totals", {}), ensure_ascii=False, indent=2)
            + "\n", "utf-8")
        with open(out_dir / "verdicts.jsonl", "w", encoding="utf-8") as f:
            for x in ev.get("relation_verdicts", []):
                f.write(_j(x) + "\n")
    with open(out_dir / "failures.jsonl", "w", encoding="utf-8") as f:
        for x in failures:
            f.write(_j(x) + "\n")

    (out_dir / "report.md").write_text("\n".join(report_md) + "\n",
                                     "utf-8")
    print(f"materialized {out_dir}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--db-dir", type=Path, required=True)
    ap.add_argument("--eval", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    materialize(a.run, a.db_dir, a.eval, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
