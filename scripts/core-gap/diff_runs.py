"""CORE-GAP regression harness — differential run comparison.

Compares a new replay against a frozen baseline ledger and classifies
every previously emitted output as exactly one of:

    IDENTICAL               row-by-row equal on compared fields
    EXPECTED_DELTA:<case>   difference claimed by a preregistered
                            gate-case in expected-deltas.json
    UNEXPECTED_DELTA        anything else — blocks the program

Usage:
    PYTHONPATH=src python -X utf8 scripts/core-gap/diff_runs.py \
        --baseline evidence/core-gap/baseline/bde-dev \
        --new      evidence/core-gap/runs/<id>/bde-dev \
        --deltas   evidence/core-gap/expected-deltas.json \
        --out      evidence/core-gap/runs/<id>/diff-bde.json

The comparator works on the JSONL ledgers both runs emit
(relations/operations/subject-outcomes/bindings/lifecycle/attribution)
plus, for CNMV probe runs, the run envelope census.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# row identity keys per ledger file
_KEY = {
    "relations.jsonl": ("relation_id",),
    "operations.jsonl": ("target", "modifier", "node_index", "leaf"),
    "subject-outcomes.jsonl": ("target", "modifier", "node_index",
                               "candidate_locator"),
    "bindings.jsonl": ("relation_id",),
    "lifecycle.jsonl": ("target", "locator_key"),
    "attribution.jsonl": ("target", "modifier", "node_index"),
    "failures.jsonl": None,   # order-sensitive; compared as multiset
    "redesignations.jsonl": ("edge_id",),
    "audit.jsonl": ("relation_id",),
}


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in
            p.read_text(encoding="utf-8").splitlines() if l.strip()]


# fields that legitimately differ between runs of the same code —
# run identity/timestamps never carry semantic content
_VOLATILE = {"run_id", "started_at", "finished_at", "timestamp"}


def _row_key(fname: str, row: dict) -> str:
    ks = _KEY.get(fname)
    if not ks:
        return json.dumps(row, sort_keys=True, ensure_ascii=False)
    return "|".join(str(row.get(k)) for k in ks)


def _strip_volatile(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in _VOLATILE}


def _match_expected(deltas: list[dict], fname: str, key: str,
                    row: dict | None) -> str | None:
    """Return case id if the delta is preregistered for this row."""
    for d in deltas:
        if d.get("file") != fname:
            continue
        pred = d.get("match", {})
        if pred and row is not None and all(
                str(row.get(k)) == str(v) for k, v in pred.items()):
            return d["case"]
        # key-prefix match (e.g. all rows of a target)
        if row is not None and d.get("match_key_prefix") and \
                key.startswith(d["match_key_prefix"]):
            return d["case"]
        # substring match over the serialized row (failures ledger
        # embeds the anomaly detail inside a JSON symptom string)
        if row is not None and d.get("match_contains") and \
                d["match_contains"] in json.dumps(
                    row, ensure_ascii=False):
            return d["case"]
    return None


def diff_dir(baseline: Path, new: Path, deltas: list[dict]) -> dict:
    out = {"files": {}, "summary": {"IDENTICAL": 0, "EXPECTED_DELTA": 0,
                                    "UNEXPECTED_DELTA": 0,
                                    "NEW_ROWS": 0, "LOST_ROWS": 0}}
    files = sorted({f.name for f in baseline.glob("*.jsonl")} |
                   {f.name for f in new.glob("*.jsonl")})
    for fname in files:
        brows = {_row_key(fname, r): r for r in
                 _load_jsonl(baseline / fname)}
        nrows = {_row_key(fname, r): r for r in
                 _load_jsonl(new / fname)}
        rep = {"identical": 0, "expected": [], "unexpected": [],
               "new_rows": [], "lost_rows": []}
        for k, br in brows.items():
            nr = nrows.get(k)
            if nr is None:
                case = _match_expected(deltas, fname, k, br)
                (rep["expected"] if case else rep["lost_rows"]
                 ).append({"key": k, "case": case})
                continue
            if _strip_volatile(br) == _strip_volatile(nr):
                rep["identical"] += 1
                continue
            changed = {f: [br.get(f), nr.get(f)] for f in
                       set(_strip_volatile(br)) | set(_strip_volatile(nr))
                       if br.get(f) != nr.get(f)}
            case = _match_expected(deltas, fname, k, nr)
            entry = {"key": k, "case": case, "changed": changed}
            (rep["expected"] if case else rep["unexpected"]).append(entry)
        for k, nr in nrows.items():
            if k not in brows:
                case = _match_expected(deltas, fname, k, nr)
                (rep["expected"] if case else rep["new_rows"]
                 ).append({"key": k, "case": case})
        out["files"][fname] = rep
        s = out["summary"]
        s["IDENTICAL"] += rep["identical"]
        s["EXPECTED_DELTA"] += len(rep["expected"])
        s["UNEXPECTED_DELTA"] += len(rep["unexpected"])
        s["NEW_ROWS"] += len(rep["new_rows"])
        s["LOST_ROWS"] += len(rep["lost_rows"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--deltas", type=Path, default=None)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    deltas = []
    if args.deltas and args.deltas.exists():
        deltas = json.loads(args.deltas.read_text("utf-8")).get(
            "expected_deltas", [])

    rep = diff_dir(args.baseline, args.new, deltas)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    s = rep["summary"]
    print(json.dumps(s, indent=2))
    if s["UNEXPECTED_DELTA"] or s["LOST_ROWS"]:
        print("UNEXPECTED_DELTA present — blocks program", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
