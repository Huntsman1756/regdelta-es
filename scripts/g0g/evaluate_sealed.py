"""G0-G.2 sealed-split evaluation runner.

One runner, one frozen evaluator contract: this entry point reuses the
frozen G0-G.1 machinery (evaluate_dev) unchanged and only
parameterizes the evidence source — the manifest path, the selection
split, and the output directory all arrive via CLI arguments. The code
never names the sealed corpus location.

Usage (conceptual):
    evaluate_sealed.py --selection evidence/g0g/selection.json \
        --manifest <manifest> --split GENERALIZATION_DEV --output <dir>
    evaluate_sealed.py --selection evidence/g0g/selection.json \
        --manifest <manifest> --split SEALED_HOLDOUT --output <dir>

All evidence bytes are served as FetchResult(..., via=EVIDENCE_IMPORT);
a URL absent from the manifest returns error_class="MISSING". Zero
network. Nothing outside --output / --audit / --attempts-log is
written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "g0g"))

import evaluate_dev as ev  # noqa: E402

METRIC_KEYS = (
    "declared_modifier_recall", "operation_parsing_rate",
    "subject_locator_resolution", "representation_binding",
    "chain_reconstruction", "applicability_extraction",
    "query_execution",
)
FAILURE_CLASSES = {
    "SOURCE_LIMITATION", "ACQUISITION_FAILURE", "PARSER_FAILURE",
    "SCHEMA_FAILURE", "EVALUATION_FAILURE",
}


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_manifest(path: Path) -> dict[str, dict]:
    m = json.loads(path.read_text(encoding="utf-8"))
    return {e["url"]: e for e in m["entries"].values()}


def split_allowlist(sel: dict, split: str) -> dict[str, str]:
    """boe_id -> cell for the requested selection split."""
    return {b: cell for cell, c in sel["cells"].items()
            for b in c.get(split, [])}


def other_splits(sel: dict, split: str) -> set[str]:
    """boe_ids assigned to any split other than the requested one.
    Only list-valued cell entries are splits; dict-valued entries
    ('ranked') are selection metadata, not assignments."""
    out: set[str] = set()
    for c in sel["cells"].values():
        for name, ids in c.items():
            if name != split and isinstance(ids, list):
                out.update(ids)
    return out


def evidence_fetch(by_url: dict[str, dict], root: Path):
    from regdelta.http import EVIDENCE_IMPORT, FetchResult

    def fetch(url: str, accept: str) -> FetchResult:
        e = by_url.get(url)
        if e is None or "path" not in e:
            return FetchResult(url, None, None, None, "MISSING",
                               "url not in evidence manifest",
                               via=EVIDENCE_IMPORT)
        p = Path(e["path"])
        body = (p if p.is_absolute() else root / p).read_bytes()
        return FetchResult(url, 200, "application/octet-stream",
                           body, None, None, via=EVIDENCE_IMPORT)
    return fetch


def run_split(targets: dict[str, str], by_url: dict[str, dict],
              gold: dict, run_id: str, out_dir: Path,
              audit_path: Path) -> dict:
    """Run the frozen pipeline + audit over every target of the split.

    Fresh DB per target; one combined smoke DB afterwards. Returns the
    aggregate metrics dict."""
    per_target: dict[str, dict] = {}
    all_audit: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        for t in sorted(targets):
            print(f"evaluating {t} ({targets[t]})")
            res = ev.evaluate_target(t, targets[t], by_url, gold,
                                     run_id, tmp_root)
            per_target[t] = res
            all_audit.extend(res.get("audit", []))
        print("combined smoke")
        combined = ev.combined_smoke(targets, by_url, gold, tmp_root)

    def pool(key):
        nums = sum(v["metrics"][key]["num"] for v in per_target.values()
                   if "metrics" in v
                   and isinstance(v["metrics"][key], dict))
        dens = sum(v["metrics"][key]["den"] for v in per_target.values()
                   if "metrics" in v
                   and isinstance(v["metrics"][key], dict))
        return {"num": nums, "den": dens,
                "value": nums / dens if dens else None}

    metrics = {k: pool(k) for k in METRIC_KEYS}
    metrics["false_positive_facts"] = sum(
        v["metrics"]["false_positive_facts"]
        for v in per_target.values() if "metrics" in v)
    metrics["source_limitations"] = sum(
        v["metrics"]["source_limitations"]
        for v in per_target.values() if "metrics" in v)
    by_cell: dict[str, dict] = {}
    for t, v in per_target.items():
        c = by_cell.setdefault(v["cell"], {"targets": []})
        c["targets"].append(t)
        c.setdefault("metrics", v.get("metrics"))

    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        for a in all_audit:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    (out_dir / "metrics.json").write_text(json.dumps(
        {"aggregate": metrics, "by_cell": by_cell,
         "per_target": {t: v.get("metrics")
                        for t, v in per_target.items()}},
        indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (out_dir / "targets.json").write_text(json.dumps(
        {t: {k: v[k] for k in ("cell", "report", "inventory",
                               "query_execution", "app_eligible",
                               "NON_GATE_DIAGNOSTIC")
             if k in v}
         for t, v in per_target.items()},
        indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    with (out_dir / "failures.jsonl").open("w", encoding="utf-8") as fh:
        for v in per_target.values():
            for f in v.get("failures", []):
                assert f["failure_class"] in FAILURE_CLASSES, f
                fh.write(json.dumps(
                    {"failure_id": _sha256(json.dumps(
                        f, sort_keys=True,
                        ensure_ascii=False).encode())[:16],
                     **f}, ensure_ascii=False) + "\n")
    with (out_dir / "relations.jsonl").open("w", encoding="utf-8") as fh:
        for t, v in per_target.items():
            for r in v.get("relations", []):
                slim = {k: r[k] for k in (
                    "relation_id", "kind", "operation_kind",
                    "locator_key", "modifier_boe", "publication_date",
                    "resolution", "before_kind", "after_kind")}
                slim["target"] = t
                fh.write(json.dumps(slim, ensure_ascii=False) + "\n")
    (out_dir / "combined-smoke.json").write_text(json.dumps(
        combined, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    lines = [f"# sealed evaluation run {run_id}", "",
             "## Aggregate", "", "| metric | num/den | value |",
             "|---|---|---|"]
    for k, v in metrics.items():
        if isinstance(v, dict):
            val = v["value"]
            lines.append(f"| {k} | {v['num']}/{v['den']} | "
                         f"{val if val is None else round(val, 4)} |")
        else:
            lines.append(f"| {k} | — | {v} |")
    lines += ["", "## Per target", "",
              "| target | cell | rels | res(R/P/U) | recall | FF |",
              "|---|---|---|---|---|---|"]
    for t, v in sorted(per_target.items()):
        if "metrics" not in v:
            lines.append(f"| {t} | {v['cell']} | ERROR | — | — | — |")
            continue
        r = v["inventory"]["resolution"]
        lines.append(
            f"| {t} | {v['cell']} | {v['inventory']['relations']} | "
            f"{r.get('RESOLVED', 0)}/{r.get('PARTIAL', 0)}/"
            f"{r.get('UNRESOLVED', 0)} | "
            f"{v['metrics']['declared_modifier_recall']['num']}/"
            f"{v['metrics']['declared_modifier_recall']['den']} | "
            f"{v['metrics']['false_positive_facts']} |")
    (out_dir / "report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return {"metrics": metrics, "by_cell": by_cell,
            "per_target": per_target, "combined": combined,
            "audit_rows": len(all_audit)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument("--split", required=True)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--evidence-root", type=Path, default=ROOT)
    ap.add_argument("--audit", type=Path, default=None,
                    help="audit register path (default <output>/"
                         "audit.jsonl)")
    ap.add_argument("--attempts-log", type=Path, default=None,
                    help="append one attempt record per invocation")
    ap.add_argument("--run-id", default="sealed")
    ap.add_argument("--targets", nargs="*", default=None,
                    help="restrict to a subset of the split's targets")
    args = ap.parse_args()

    sel = json.loads(args.selection.read_text(encoding="utf-8"))
    allow = split_allowlist(sel, args.split)
    if not allow:
        print(f"FAIL CLOSED: split {args.split!r} not in selection")
        return 2
    # fail closed: a target must belong to exactly the chosen split
    overlap = set(allow) & other_splits(sel, args.split)
    if overlap:
        print(f"FAIL CLOSED: target in another split: {sorted(overlap)}")
        return 2
    if args.targets is not None:
        for t in args.targets:
            if t not in allow:
                print(f"FAIL CLOSED: {t} not in split {args.split}")
                return 2
        allow = {t: allow[t] for t in args.targets}

    by_url = load_manifest(args.manifest)
    gold_all = json.loads(args.gold.read_text(encoding="utf-8"))
    gold = {k: v for k, v in gold_all.items() if k in allow}

    started = datetime.now(timezone.utc).isoformat()
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    src_tree = subprocess.run(["git", "rev-parse", "HEAD:src/regdelta"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()

    # evaluate_target resolves evidence_fetch from its own module
    # namespace; bind the CLI-parameterized fetch there so every byte
    # served is EVIDENCE_IMPORT from the chosen manifest.
    ev.evidence_fetch = lambda urls: evidence_fetch(  # noqa: E731
        urls, args.evidence_root)

    audit_path = args.audit or (args.output / "audit.jsonl")
    result = run_split(allow, by_url, gold, args.run_id,
                       args.output, audit_path)
    finished = datetime.now(timezone.utc).isoformat()

    run = {
        "run_id": args.run_id, "split": args.split,
        "runtime_head": head, "src_tree_sha": src_tree,
        "runner_sha256": _sha256(Path(__file__).read_bytes()),
        "evaluator_sha256": _sha256(
            (ROOT / "scripts" / "g0g" / "evaluate_dev.py").read_bytes()),
        "manifest_sha256": _sha256(args.manifest.read_bytes()),
        "selection_sha256": _sha256(args.selection.read_bytes()),
        "gold_sha256": _sha256(args.gold.read_bytes()),
        "started_at": started, "finished_at": finished,
        "audit_rows": result["audit_rows"],
        "combined_ok": result["combined"]["ok"],
        "aggregate": result["metrics"],
    }
    (args.output / "run.json").write_text(json.dumps(
        run, indent=2, sort_keys=True), encoding="utf-8")

    if args.attempts_log is not None:
        args.attempts_log.parent.mkdir(parents=True, exist_ok=True)
        with args.attempts_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "run_id": args.run_id, "split": args.split,
                "runtime_head": head,
                "runner_sha256": run["runner_sha256"],
                "evaluator_sha256": run["evaluator_sha256"],
                "manifest_sha256": run["manifest_sha256"],
                "started_at": started, "finished_at": finished,
                "output": str(args.output),
            }, ensure_ascii=False) + "\n")

    print(json.dumps({"run_dir": str(args.output),
                      "aggregate": result["metrics"],
                      "audit_rows": result["audit_rows"],
                      "combined_ok": result["combined"]["ok"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
