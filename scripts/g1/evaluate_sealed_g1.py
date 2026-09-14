"""G1.2 sealed-split evaluation runner.

Thin orchestration over the frozen G1 evaluator (evaluate_g1): this
entry point adds the G1.2 protocol shell only — split derivation from
selection-v2, fail-closed target checks, binding_proof consistency and
B1-B6 invariant verification, abstention accounting, SEAL integrity
verification and attempts logging. The per-relation audit machinery is
evaluate_g1's, unchanged.

The sealed evidence directory is never named in this file: the holdout
manifest arrives via --manifest and the SEAL is located relative to it.

Usage:
    evaluate_sealed.py --split DEV \
        --manifest evidence/g1/dev/manifest.json \
        --gold evidence/g0g/gold/declared_modifiers.json \
        --corpus evidence/g1/dev/g0-false-binding-corpus.json \
        --selection evidence/g1/selection-v2.json \
        --output <dir> --run-id <id>

    evaluate_sealed.py --split SEALED_HOLDOUT \
        --manifest <sealed manifest> \
        --gold evidence/g1/gold/declared_modifiers.json \
        --selection evidence/g1/selection-v2.json \
        --output <dir> --run-id <id> --official \
        --runtime-head <G1_RUNTIME_HEAD> --attempts-log <path>

Zero network: every byte is served via EVIDENCE_IMPORT. Fresh DB per
target; a combined smoke DB afterwards (NON_GATE_DIAGNOSTIC).
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
sys.path.insert(0, str(ROOT / "scripts" / "g1"))

import evaluate_dev as ev  # noqa: E402
import evaluate_g1 as g1  # noqa: E402

SPLITS = ("DEV", "SEALED_HOLDOUT")

TRUTH_VERDICTS = {"PASS", "FALSE_FACT"}
BINDING_VERDICTS = {"BINDING_CORRECT", "BINDING_FALSE",
                    "BINDING_NOT_CHECKABLE", "NO_BINDING_CLAIM"}
ROOT_CAUSES = set(g1.ROOT_CAUSES)
B_KEYS = ("B1", "B2", "B3", "B4", "B5", "B6")

METRIC_KEYS = ("declared_modifier_recall", "operation_parsing_rate",
               "subject_locator_resolution", "representation_binding",
               "chain_reconstruction", "applicability_extraction",
               "query_execution")

BOUND = "BOUND"
ABSTAIN_STATUSES = {"NOT_FOUND", "AMBIGUOUS", "NOT_PROVABLE"}
NOT_APPLICABLE = "NOT_APPLICABLE"
# op-side pairs where NOT_APPLICABLE is the semantically required status
_NA_METHODS = {"before": {"ADD_NO_BEFORE"},
               "after": {"DELETE_NO_AFTER"}}


class FailClosed(Exception):
    pass


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_manifest(path: Path) -> dict[str, dict]:
    m = json.loads(path.read_text(encoding="utf-8"))
    return {e["url"]: e for e in m["entries"].values()}


def split_allowlist(sel: dict, manifest: dict, split: str) \
        -> dict[str, str]:
    """boe_id -> cell for the requested split.

    SEALED_HOLDOUT derives from selection-v2 only (§5); DEV derives
    from the dev manifest's target cells (the 12 already-seen
    targets)."""
    if split == "SEALED_HOLDOUT":
        out = {}
        for b in sel["SEALED_HOLDOUT"]:
            meta = sel["targets"][b]
            cons = "CONSOLIDATED" if meta["consolidated"] \
                else "NON_CONSOLIDATED"
            out[b] = f"{meta['group']}x{cons}"
        return out
    if split == "DEV":
        return dict(manifest.get("targets", {}))
    raise FailClosed(f"unknown split {split!r}")


def other_split_ids(sel: dict, manifest: dict, split: str) -> set[str]:
    """IDs that belong to a different split; requesting one fails
    closed."""
    out: set[str] = set()
    if split != "SEALED_HOLDOUT":
        out.update(sel.get("SEALED_HOLDOUT", []))
    if split != "DEV":
        out.update(manifest.get("targets", {}))
    return out


def resolve_targets(sel: dict, manifest: dict, split: str,
                    requested: list[str] | None) -> dict[str, str]:
    allow = split_allowlist(sel, manifest, split)
    if not allow:
        raise FailClosed(f"split {split!r} is empty")
    if requested is None:
        return allow
    foreign = set(requested) & other_split_ids(sel, manifest, split)
    if foreign:
        raise FailClosed(f"target in another split: {sorted(foreign)}")
    outside = [t for t in requested if t not in allow]
    if outside:
        raise FailClosed(f"{outside} not in split {split}")
    return {t: allow[t] for t in requested}


# ---------------------------------------------------------------------------
# binding_proof consistency + B1-B6 invariants (§7-8)
# ---------------------------------------------------------------------------


def proof_violations(r: dict) -> list[str]:
    """Mechanical §7 invariants between binding_proof and the persisted
    representation claims. A contradiction is a failure even if the
    represented text happens to be correct."""
    proof = r.get("binding_proof") or {}
    v: list[str] = []
    for side in ("before", "after"):
        p = proof.get(side) or {}
        st = p.get("status")
        rep = r[f"{side}_representation_id"]
        if st == BOUND:
            if rep is None:
                v.append(f"{side}:BOUND_without_representation")
            elif p.get("method") == "CHAIN_PREDECESSOR":
                if not p.get("predecessor_relation_id") \
                        or p.get("predecessor_representation_id") != rep:
                    v.append(f"{side}:chain_predecessor_mismatch")
            else:
                if p.get("candidate_count") != 1 or not p.get("chosen"):
                    v.append(f"{side}:BOUND_without_unique_chosen")
        elif st in ABSTAIN_STATUSES:
            if rep is not None:
                v.append(f"{side}:{st}_persisted_representation")
            cc = p.get("candidate_count")
            if (st == "AMBIGUOUS" and not (cc and cc > 1)) or \
                    (st in ("NOT_FOUND", "NOT_PROVABLE") and cc != 0):
                v.append(f"{side}:{st}_bad_candidate_count")
        elif st == NOT_APPLICABLE:
            if rep is not None:
                v.append(f"{side}:NOT_APPLICABLE_persisted")
            if p.get("candidate_count") != 0:
                v.append(f"{side}:NOT_APPLICABLE_bad_count")
            if p.get("method") not in _NA_METHODS[side]:
                v.append(f"{side}:NOT_APPLICABLE_wrong_method")
            if (side == "before" and r["operation_kind"] != "ADD") or \
                    (side == "after" and r["operation_kind"] != "DELETE"):
                v.append(f"{side}:NOT_APPLICABLE_op_mismatch")
        else:  # no usable proof for this side
            if rep is not None:
                v.append(f"{side}:representation_without_proof")
            elif st is not None:
                v.append(f"{side}:unknown_status")
    return v


def binding_invariants(r: dict, audit: dict,
                       rows_by_id: dict[str, dict]) -> dict[str, str]:
    """B1-B6 per relation: PASS | FAIL | NOT_APPLICABLE. Diagnostic
    decomposition, not six thresholds."""
    proof = r.get("binding_proof") or {}
    claims = audit["claims_checked"]
    inv: dict[str, str] = {}

    # B1 unique-or-unbound: a persisted rep requires a BOUND side whose
    # method either proves a unique candidate or a chain predecessor
    reps = [(s, r[f"{s}_representation_id"]) for s in ("before", "after")]
    bound_any = any(rep for _, rep in reps)
    b1_bad = False
    for side, rep in reps:
        if rep is None:
            continue
        p = proof.get(side) or {}
        if p.get("method") == "CHAIN_PREDECESSOR":
            ok = p.get("predecessor_representation_id") == rep
        else:
            ok = p.get("status") == BOUND and p.get("candidate_count") \
                == 1 and bool(p.get("chosen"))
        b1_bad |= not ok
    inv["B1"] = "FAIL" if b1_bad else ("PASS" if bound_any
                                       else "NOT_APPLICABLE")

    # B2 exact structural scope: bound spans must carry the claimed
    # subject's content — surfaced by the binding verdicts
    bv = [claims.get(f"{s}_binding") for s in ("before", "after")]
    if "BINDING_FALSE" in bv:
        inv["B2"] = "FAIL"
    elif "BINDING_CORRECT" in bv:
        inv["B2"] = "PASS"
    else:
        inv["B2"] = "NOT_APPLICABLE"

    # B3 modifier-side ownership: an after representation must come
    # from the modifier document, never the target's own content
    arep = r["after_representation_id"]
    if arep is None:
        inv["B3"] = "NOT_APPLICABLE"
    elif r.get("after_instrument") not in (None, r["modifier_boe"]) \
            and r["operation_kind"] != "DELETE":
        inv["B3"] = "FAIL"
    else:
        inv["B3"] = "PASS"

    # B4 chain predecessor: verified via the persisted proof, not
    # re-guessed by date order
    cp = claims.get("chain_predecessor")
    inv["B4"] = ("PASS" if cp == "VERIFIED"
                 else "FAIL" if cp == "CONTRADICTED"
                 else "NOT_APPLICABLE")

    # B5 ambiguity degrades: an abstained side must not persist a claim
    abstained = [s for s in ("before", "after")
                 if (proof.get(s) or {}).get("status")
                 in ABSTAIN_STATUSES | {NOT_APPLICABLE}]
    if any(r[f"{s}_representation_id"] for s in abstained):
        inv["B5"] = "FAIL"
    elif abstained:
        inv["B5"] = "PASS"
    else:
        inv["B5"] = "NOT_APPLICABLE"

    # B6 resolution follows verified binding
    rc = claims.get("resolution_consistent")
    inv["B6"] = ("PASS" if rc == "VERIFIED"
                 else "FAIL" if rc == "CONTRADICTED"
                 else "NOT_APPLICABLE")
    return inv


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def _chain_rows(target: str, rows: list[dict],
                chains: dict) -> list[dict]:
    by_sub: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda x: (x["publication_date"] or "",
                                         x["relation_id"])):
        by_sub.setdefault(r["locator_key"], []).append(r)
    broken = set(chains.get("broken_locator_keys", []))
    out = []
    for key, hops in sorted(by_sub.items()):
        if len(hops) < 2:
            continue
        all_proven = all(
            hops[i]["after_representation_id"]
            and hops[i + 1]["before_representation_id"]
            and hops[i]["after_representation_id"]
            == hops[i + 1]["before_representation_id"]
            for i in range(len(hops) - 1))
        verdict = ("CHAIN_BROKEN" if key in broken
                   else "CHAIN_PROVEN" if all_proven
                   else "CHAIN_NOT_PROVABLE")
        out.append({"target": target, "locator_key": key,
                    "chain_verdict": verdict,
                    "hops": [{"relation_id": h["relation_id"],
                              "before_representation_id":
                                  h["before_representation_id"],
                              "after_representation_id":
                                  h["after_representation_id"]}
                             for h in hops]})
    return out


def _abstentions(rows: list[dict]) -> dict:
    sides: dict[str, dict] = {"before": {}, "after": {}}
    reasons: dict[str, int] = {}
    for r in rows:
        proof = r.get("binding_proof") or {}
        for s in ("before", "after"):
            st = (proof.get(s) or {}).get("status") or "NO_PROOF"
            sides[s][st] = sides[s].get(st, 0) + 1
            rs = (proof.get(s) or {}).get("reason")
            if rs:
                reasons[rs] = reasons.get(rs, 0) + 1
    return {"by_side": sides, "by_reason": reasons}


def _verify_seal(manifest_path: Path) -> dict:
    """Hash-only integrity check of the sealed corpus (§4: not an
    opening)."""
    seal_path = manifest_path.parent / "SEAL"
    if not seal_path.exists():
        return {"seal_present": False}
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    manifest_bytes = manifest_path.read_bytes()
    raw = manifest_path.parent / "raw"
    files = sorted(raw.iterdir())
    blob = b"".join(f.read_bytes() for f in files)
    ok = (_sha256(manifest_bytes) == seal["manifest_sha256"]
          and len(files) == seal["artifact_count"]
          and len(blob) == seal["aggregate_bytes"]
          and _sha256(blob) == seal["aggregate_sha256"])
    return {"seal_present": True, "seal_ok": ok,
            "manifest_sha256": seal["manifest_sha256"],
            "aggregate_sha256": seal["aggregate_sha256"],
            "artifact_count": seal["artifact_count"],
            "targets": seal.get("targets", [])}


def run_split(targets: dict[str, str], by_url: dict[str, dict],
              gold: dict, corpus: dict | None,
              rc_by_fid: dict[str, dict], run_id: str,
              out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_audit, all_bindings, all_failures, all_chains = [], [], [], []
    all_rows: dict[str, list[dict]] = {}
    audits_by_rid: dict[str, dict] = {}
    per_target: dict[str, dict] = {}
    combined = {"ok": None, "problems": ["not run"]}
    with tempfile.TemporaryDirectory() as tmp:
        for t in sorted(targets):
            print(f"evaluating {t} ({targets[t]})")
            res = g1.evaluate_target(t, targets[t], by_url, gold,
                                     run_id, Path(tmp))
            if "metrics" not in res:
                per_target[t] = res
                all_failures += res.get("failures", [])
                continue
            rows_by_id = {r["relation_id"]: r
                          for r in res.get("relations", [])}
            for a in res.get("audit", []):
                r = rows_by_id[a["relation_id"]]
                viol = proof_violations(r)
                a["claims_checked"]["binding_proof_consistent"] = (
                    "CONTRADICTED" if viol else "VERIFIED")
                a["proof_violations"] = viol
                a["binding_invariants"] = binding_invariants(
                    r, a, rows_by_id)
                if viol:
                    a["truth_verdict"] = "FALSE_FACT"
                    a["root_cause_class"] = sorted(set(
                        a["root_cause_class"]) | {"SCHEMA_FAILURE"})
                    a["false_binding"] = a["false_binding"] or any(
                        r[f"{s}_representation_id"] and "persisted"
                        in " ".join(viol)
                        for s in ("before", "after"))
            # proof consistency can only tighten the verdict —
            # recompute the two gated counters from augmented audits
            res["metrics"]["false_positive_facts"] = sum(
                1 for a in res["audit"]
                if a["truth_verdict"] == "FALSE_FACT")
            res["metrics"]["false_binding_count"] = sum(
                1 for a in res["audit"] if a["false_binding"])
            gold_ids = {d["modifier_boe_id"]
                        for d in gold.get(t, {}).get("declared", [])}
            discovered = {m["boe_id"] for m in
                          res.get("report", {}).get("modifiers", [])}
            res["metrics"]["gold_detail"] = {
                "gold_count": len(gold_ids),
                "discovered_count": len(discovered),
                "missing_gold_modifiers": sorted(gold_ids - discovered),
                "unexpected_modifier_candidates":
                    sorted(discovered - gold_ids),
                "reverse_cross_checked":
                    res.get("NON_GATE_DIAGNOSTIC", {})
                    .get("reverse_cross_checked_count")}
            for a in res["audit"]:
                audits_by_rid[a["relation_id"]] = a
            all_audit += res["audit"]
            all_bindings += res.get("bindings", [])
            all_failures += res.get("failures", [])
            all_rows[t] = res.get("relations", [])
            all_chains += _chain_rows(
                t, all_rows[t],
                res.get("NON_GATE_DIAGNOSTIC", {}).get("chains", {}))
            per_target[t] = {k: v for k, v in res.items()
                             if k not in ("audit", "bindings",
                                          "failures", "relations",
                                          "chain_ctx")}
        print("combined smoke")
        combined = ev.combined_smoke(targets, by_url, gold, Path(tmp))

    corpus_result = (g1.reclassify_corpus(corpus, all_rows,
                                         audits_by_rid, rc_by_fid)
                     if corpus else {"counts": {}, "cases": [],
                                     "total": 0})

    def agg(key):
        num = sum(v["metrics"][key]["num"] for v in per_target.values()
                  if "metrics" in v)
        den = sum(v["metrics"][key]["den"] for v in per_target.values()
                  if "metrics" in v)
        return {"num": num, "den": den,
                "value": num / den if den else None}

    metrics = {k: agg(k) for k in METRIC_KEYS}
    metrics["false_positive_facts"] = sum(
        v["metrics"]["false_positive_facts"]
        for v in per_target.values() if "metrics" in v)
    metrics["false_binding_count"] = sum(
        v["metrics"]["false_binding_count"]
        for v in per_target.values() if "metrics" in v)
    metrics["source_limitations"] = sum(
        v["metrics"]["source_limitations"]
        for v in per_target.values() if "metrics" in v)
    if corpus:
        metrics["old_false_fact_reproduction_count"] = \
            corpus_result["counts"].get("REPRODUCED_FALSE_FACT", 0)
    flat_rows = [r for rows in all_rows.values() for r in rows]
    metrics["abstentions"] = _abstentions(flat_rows)
    b_fail = {k: 0 for k in B_KEYS}
    for a in all_audit:
        for k in B_KEYS:
            if a.get("binding_invariants", {}).get(k) == "FAIL":
                b_fail[k] += 1
    metrics["binding_invariant_failures"] = b_fail

    (out_dir / "metrics.json").write_text(json.dumps(
        {"aggregate": metrics,
         "per_target": {t: v.get("metrics")
                        for t, v in per_target.items()},
         "corpus_73": corpus_result["counts"]},
        indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (out_dir / "targets.json").write_text(json.dumps(
        per_target, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    with (out_dir / "audit.jsonl").open("w", encoding="utf-8") as fh:
        for a in all_audit:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    with (out_dir / "bindings.jsonl").open("w", encoding="utf-8") as fh:
        rows_by_rid = {(t, r["relation_id"]): r
                       for t, rows in all_rows.items() for r in rows}
        for b in all_bindings:
            p = (rows_by_rid.get((b["target"], b["relation_id"]), {})
                 .get("binding_proof") or {}).get(b["side"]) or {}
            fh.write(json.dumps(
                {**b, "proof_status": p.get("status"),
                 "proof_method": p.get("method"),
                 "proof_reason": p.get("reason")},
                ensure_ascii=False) + "\n")
    with (out_dir / "chains.jsonl").open("w", encoding="utf-8") as fh:
        for c in all_chains:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (out_dir / "failures.jsonl").open("w", encoding="utf-8") as fh:
        for f in all_failures:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    with (out_dir / "relations.jsonl").open("w", encoding="utf-8") as fh:
        for t, rows in all_rows.items():
            for r in rows:
                fh.write(json.dumps(
                    {**{k: r[k] for k in (
                        "relation_id", "kind", "operation_kind",
                        "locator_key", "modifier_boe",
                        "publication_date", "resolution",
                        "before_representation_id",
                        "after_representation_id")},
                     "target": t}, ensure_ascii=False) + "\n")
    (out_dir / "corpus-73.json").write_text(json.dumps(
        corpus_result, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    (out_dir / "combined-smoke.json").write_text(json.dumps(
        combined, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    lines = [f"# G1.2 sealed evaluation — run {run_id}", "",
             "## Per target (first table, §28)", "",
             "| target | gold | rels emitted | rels audited | "
             "before bound | after bound | R/P/U | FF | FB |",
             "|---|---|---|---|---|---|---|---|---|"]
    for t in sorted(per_target):
        v = per_target[t]
        if "metrics" not in v:
            lines.append(f"| {t} | — | ERROR | — | — | — | — | — | — |")
            continue
        rows = all_rows.get(t, [])
        res_d = v["inventory"]["resolution"]
        nb = sum(1 for r in rows if r["before_representation_id"])
        na = sum(1 for r in rows if r["after_representation_id"])
        gold_n = v.get("NON_GATE_DIAGNOSTIC", {}).get("gold_count", 0)
        lines.append(
            f"| {t} | {gold_n} | {len(rows)} | "
            f"{sum(1 for a in all_audit if a['target'] == t)} | "
            f"{nb} | {na} | "
            f"{res_d.get('RESOLVED', 0)}/{res_d.get('PARTIAL', 0)}/"
            f"{res_d.get('UNRESOLVED', 0)} | "
            f"{v['metrics']['false_positive_facts']} | "
            f"{v['metrics']['false_binding_count']} |")
    lines += ["", "## Aggregate", "", "| metric | num/den | value |",
              "|---|---|---|"]
    for k, v in metrics.items():
        if isinstance(v, dict) and "num" in v:
            val = v["value"]
            lines.append(f"| {k} | {v['num']}/{v['den']} | "
                         f"{val if val is None else round(val, 4)} |")
        elif not isinstance(v, dict):
            lines.append(f"| {k} | — | {v} |")
    lines += ["", "abstentions:", "",
              "```", json.dumps(metrics["abstentions"], indent=2,
                                sort_keys=True), "```",
              "", "B1-B6 FAIL counts:", "",
              "```", json.dumps(b_fail, indent=2, sort_keys=True),
              "```"]
    if corpus:
        lines += ["", "corpus-73:", "",
                  "```", json.dumps(corpus_result["counts"], indent=2),
                  "```"]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")
    return {"metrics": metrics, "corpus": corpus_result,
            "audit_rows": len(all_audit), "per_target": per_target,
            "all_rows": all_rows, "all_audit": all_audit,
            "combined": combined}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--root-cause", type=Path, default=None)
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--attempts-log", type=Path, default=None)
    ap.add_argument("--run-id", default="sealed")
    ap.add_argument("--official", action="store_true")
    ap.add_argument("--runtime-head", default=None,
                    help="expected G1_RUNTIME_HEAD for --official runs")
    ap.add_argument("--targets", nargs="*", default=None)
    args = ap.parse_args()

    sel = json.loads(args.selection.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    try:
        allow = resolve_targets(sel, manifest, args.split,
                                args.targets)
    except FailClosed as e:
        print(f"FAIL CLOSED: {e}")
        return 2

    by_url = {e["url"]: e for e in manifest["entries"].values()}
    gold_all = json.loads(args.gold.read_text(encoding="utf-8"))
    gold = {k: v for k, v in gold_all.items() if k in allow}
    corpus = json.loads(args.corpus.read_text(encoding="utf-8")) \
        if args.corpus else None
    rc_by_fid = {}
    if args.root_cause and args.root_cause.exists():
        rc_by_fid = {json.loads(l)["failure_id"]: json.loads(l)
                     for l in args.root_cause.read_text(
                         encoding="utf-8").splitlines() if l.strip()}

    started = datetime.now(timezone.utc).isoformat()
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    src_tree = subprocess.run(["git", "rev-parse", "HEAD:src/regdelta"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()
    seal_pre = _verify_seal(args.manifest)

    def _hashes() -> dict:
        return {
            "runner_sha256": _sha256(Path(__file__).read_bytes()),
            "evaluator_sha256": _sha256(
                (ROOT / "scripts" / "g1" / "evaluate_g1.py")
                .read_bytes()),
            "g0g_evaluator_sha256": _sha256(
                (ROOT / "scripts" / "g0g" / "evaluate_dev.py")
                .read_bytes()),
            "manifest_sha256": _sha256(args.manifest.read_bytes()),
            "selection_sha256": _sha256(args.selection.read_bytes()),
            "gold_sha256": _sha256(args.gold.read_bytes()),
        }

    attempt = {"run_id": args.run_id, "split": args.split,
               "runtime_head": head, **_hashes(),
               "targets": sorted(allow), "official": bool(args.official),
               "output": str(args.output), "started_at": started}

    def record_attempt(extra: dict) -> None:
        if args.attempts_log is None:
            return
        args.attempts_log.parent.mkdir(parents=True, exist_ok=True)
        with args.attempts_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**attempt, **extra},
                                ensure_ascii=False) + "\n")

    if args.official and args.runtime_head and \
            head != args.runtime_head:
        print(f"FAIL CLOSED: HEAD {head} != runtime-head "
              f"{args.runtime_head}")
        record_attempt({"status": "fail_closed_head_mismatch"})
        return 2
    if args.split == "SEALED_HOLDOUT" and \
            not seal_pre.get("seal_ok"):
        print("FAIL CLOSED: SEAL integrity check failed")
        record_attempt({"status": "fail_closed_seal"})
        return 2

    try:
        result = run_split(allow, by_url, gold, corpus, rc_by_fid,
                           args.run_id, args.output)
    except Exception:
        record_attempt({"status": "failed",
                        "finished_at":
                            datetime.now(timezone.utc).isoformat()})
        raise
    finished = datetime.now(timezone.utc).isoformat()
    seal_post = _verify_seal(args.manifest)
    src_tree_post = subprocess.run(
        ["git", "rev-parse", "HEAD:src/regdelta"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip()

    run = {"run_id": args.run_id, "split": args.split,
           "runtime_head": head, "src_tree_sha": src_tree,
           **_hashes(),
           "seal_pre": seal_pre, "seal_post": seal_post,
           "started_at": started, "finished_at": finished,
           "audit_rows": result["audit_rows"],
           "combined_ok": result["combined"].get("ok"),
           "aggregate": result["metrics"]}
    (args.output / "run.json").write_text(json.dumps(
        run, indent=2, sort_keys=True), encoding="utf-8")

    if args.split == "SEALED_HOLDOUT":
        audited = sum(
            1 for a in result["all_audit"])
        emitted = sum(len(rows) for rows in
                      result["all_rows"].values())
        integrity = (
            head == (args.runtime_head or head)
            and src_tree == src_tree_post
            and seal_pre.get("seal_ok", True)
            and seal_post.get("seal_ok", True)
            and seal_pre.get("manifest_sha256")
            == seal_post.get("manifest_sha256")
            and seal_pre.get("aggregate_sha256")
            == seal_post.get("aggregate_sha256")
            and audited == emitted)
        pt = result["per_target"]
        ff_gate = all(
            v.get("metrics", {}).get("false_positive_facts") == 0
            for v in pt.values())
        fb_gate = all(
            v.get("metrics", {}).get("false_binding_count") == 0
            for v in pt.values())
        verdict = "PASS" if (integrity and ff_gate and fb_gate) \
            else "FAIL"
        tgt_verdicts = {}
        for t, v in sorted(pt.items()):
            rows = result["all_rows"].get(t, [])
            res_d = v.get("inventory", {}).get("resolution", {})
            tgt_verdicts[t] = {
                "gold_modifiers": v.get("NON_GATE_DIAGNOSTIC", {})
                .get("gold_count", 0),
                "relations_emitted": len(rows),
                "relations_audited": sum(
                    1 for a in result["all_audit"]
                    if a["target"] == t),
                "before_bindings": sum(
                    1 for r in rows if r["before_representation_id"]),
                "after_bindings": sum(
                    1 for r in rows if r["after_representation_id"]),
                "resolved": res_d.get("RESOLVED", 0),
                "partial": res_d.get("PARTIAL", 0),
                "unresolved": res_d.get("UNRESOLVED", 0),
                "false_facts": v.get("metrics", {})
                .get("false_positive_facts"),
                "false_bindings": v.get("metrics", {})
                .get("false_binding_count"),
            }
        claim = ("Structural binding integrity is supported on the "
                 "complete available fresh amendment-dense BdE holdout "
                 "selected under the preregistered eligibility rule, "
                 "including both textual and visual targets, with "
                 "measured coverage and fail-closed abstention.") \
            if verdict == "PASS" else None
        (args.output / "VERDICT.json").write_text(json.dumps({
            "gate": "G1.2", "runtime_head": head,
            "evaluation_head": head,
            "opened_at": started,
            "protocol_integrity": "PASS" if integrity else "FAIL",
            "false_fact_gate": "PASS" if ff_gate else "FAIL",
            "false_binding_gate": "PASS" if fb_gate else "FAIL",
            "g1_2_verdict": verdict, "claim": claim,
            "targets": tgt_verdicts},
            indent=2, sort_keys=True), encoding="utf-8")

    record_attempt({"status": "completed",
                    "finished_at": finished,
                    "audit_rows": result["audit_rows"],
                    "combined_ok": result["combined"].get("ok")})
    print(json.dumps({"run_dir": str(args.output),
                      "aggregate": result["metrics"],
                      "corpus_73": result["corpus"]["counts"],
                      "audit_rows": result["audit_rows"],
                      "combined_ok": result["combined"].get("ok")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
