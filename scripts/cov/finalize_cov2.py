"""COV-2D finalizer — mechanical generation of the closing artifacts.

Reads the frozen COV-2 runs and emits:

* ``coverage-delta.jsonl`` — §44: one row per binding side whose
  evaluator outcome changed vs ``runs/000-baseline``, joined on the
  semantic relation signature (never ``relation_id``, §12).
* ``fixes.jsonl`` — §45: append-only generic-fix log, one row per
  committed runtime fix with before/after metrics taken from the run
  ledgers.
* ``final-metrics.json`` — §59–§61: per-stratum statistics, Wilson
  95% intervals, mechanism attribution and the baseline→final debt
  matrix.
* ``VERDICT.json`` — §64–§66/§72 gate evaluation and terminal state.

The script performs no semantic reads of COV-3 content; it only joins
already-produced run ledgers.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COV2 = ROOT / "evidence" / "cov" / "cov2"
RUNS = COV2 / "runs"

BASELINE = RUNS / "000-baseline"
INTERMEDIATE = [RUNS / "001-f1", RUNS / "002-f2"]
FINAL = RUNS / "003-final"

FIX_META = [
    {"fix_id": "F1",
     "run": "001-f1",
     "commit": "c4bed51c464bae1f25aec46906eaf51ce1121075",
     "root_cause": "SUBJECT_SCOPE_NOT_PROVABLE: the before side of an "
                   "operation scoping below the recorded locator was "
                   "abstained upfront, although the subject's prior "
                   "representation is ordinary provable subject state",
     "debt_classes": ["SUBJECT_SCOPE_NOT_PROVABLE"],
     "red_tests": ["tests/cov/test_cov2_subscope.py"],
     "files_changed": ["src/regdelta/history.py"],
     "binding_method": "UNIQUE_STRUCTURAL_TARGET (existing; "
                       "before side no longer scope-gated)"},
    {"fix_id": "F2",
     "run": "003-final",
     "commit": "ebbfdd3eb513de05a57d86d004d23ca71e91f59",
     "root_cause": "NO_STRUCTURAL_CANDIDATE: structural markers in "
                   "variant typographic forms (undotted numerals, "
                   "compound dotted codes, bare disposición ordinal "
                   "segments) were not enumerated, and child-level "
                   "markers truncated parent regions so nested "
                   "sub-locators could never resolve",
     "debt_classes": ["NO_STRUCTURAL_CANDIDATE"],
     "red_tests": ["tests/cov/test_cov2_markers.py"],
     "files_changed": ["src/regdelta/binding.py"],
     "binding_method": "UNIQUE_STRUCTURAL_TARGET (existing; "
                       "tolerant candidate enumeration)"},
]


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in
            path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _wilson(k: int, n: int, z: float = 1.96) -> dict:
    if n == 0:
        return {"low": 0.0, "high": 0.0, "center": 0.0}
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"low": round(c - h, 6), "center": round(c, 6),
            "high": round(c + h, 6)}


def _sides(run: Path) -> dict[tuple[str, str], dict]:
    out = {}
    for r in _load_jsonl(run / "binding-sides.jsonl"):
        out[(r["semantic_relation_signature"], r["side"])] = r
    return out


def _cov(run: Path) -> dict:
    return _load_json(run / "run.json")["cov_metrics"]


def _debt(run: Path) -> dict[tuple[str, str], str]:
    d = _load_json(run / "debt-census.json")
    return {(r["semantic_relation_signature"], r["side"]):
            r["debt_class"] for r in d["rows"]}


def main() -> int:
    base_sides, final_sides = _sides(BASELINE), _sides(FINAL)
    base_debt = _debt(BASELINE)
    inter_sides = [_sides(r) for r in INTERMEDIATE]

    # -- coverage-delta.jsonl (§44) ------------------------------------
    delta_rows = []
    fix_for = {}
    keys = sorted(set(base_sides) | set(final_sides))
    for key in keys:
        b = base_sides.get(key)
        f = final_sides.get(key)
        b_stat = b["runtime_binding_status"] if b else None
        f_stat = f["runtime_binding_status"] if f else None
        b_verd = b["evaluator_verdict"] if b else None
        f_verd = f["evaluator_verdict"] if f else None
        if b_stat == f_stat and b_verd == f_verd:
            continue
        ref = f or b
        # attribute to the first run where the outcome reached its
        # final status
        fix_id = "F1"
        for i, sides in enumerate(inter_sides):
            r = sides.get(key)
            r_stat = r["runtime_binding_status"] if r else None
            if r_stat == f_stat:
                fix_id = FIX_META[i]["fix_id"] if i < len(FIX_META) \
                    else f"run{i}"
                break
        fix_for[key] = fix_id
        delta_rows.append({
            "target": ref["target"],
            "modifier": ref["modifier"],
            "semantic_relation_signature": key[0],
            "locator_key": ref["locator_key"],
            "side": key[1],
            "baseline_status": b_stat,
            "final_status": f_stat,
            "baseline_method":
                b["runtime_binding_method"] if b else None,
            "final_method":
                f["runtime_binding_method"] if f else None,
            "debt_class": base_debt.get(key),
            "generic_fix_id": fix_id,
            "representation_kind": ref["representation_kind"],
            "proof_source":
                (f["runtime_binding_method"] if f else None),
            "evaluator_verdict": f_verd,
            "coverage_credit":
                f_verd == "BINDING_CORRECT"
                and b_verd != "BINDING_CORRECT",
        })
    (COV2 / "coverage-delta.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                  for r in delta_rows) + "\n", encoding="utf-8")

    # -- fixes.jsonl (§45) ----------------------------------------------
    runs = [BASELINE] + INTERMEDIATE + [FINAL]
    metrics = [_cov(r) for r in runs]
    fix_rows = []
    for i, meta in enumerate(FIX_META):
        before = metrics[i]["CURRENT_OPERATIONAL"]
        after = metrics[i + 1]["CURRENT_OPERATIONAL"]
        h_before = metrics[i]["HISTORICAL_PREDECESSOR"]
        h_after = metrics[i + 1]["HISTORICAL_PREDECESSOR"]
        fix_rows.append({
            **meta,
            "positive_assertions_before":
                before["positive_binding_assertions"],
            "positive_assertions_after":
                after["positive_binding_assertions"],
            "relations_before": before["relations_emitted"],
            "relations_after": after["relations_emitted"],
            "locator_proven_ops_before": before["locator_proven_ops"],
            "locator_proven_ops_after": after["locator_proven_ops"],
            "false_delta": {
                k: after[k] - before[k] for k in (
                    "false_fact", "false_binding",
                    "false_subject_attribution",
                    "false_locator_declaration")},
            "b1_b6_delta": 0,
            "current_delta":
                after["positive_binding_assertions"]
                - before["positive_binding_assertions"],
            "historical_delta":
                h_after["positive_binding_assertions"]
                - h_before["positive_binding_assertions"],
        })
    (COV2 / "fixes.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                  for r in fix_rows) + "\n", encoding="utf-8")

    # -- final-metrics.json (§59–§61) ----------------------------------
    final_run = _load_json(FINAL / "run.json")
    base_run = _load_json(BASELINE / "run.json")
    stats = {}
    for stratum in ("CURRENT_OPERATIONAL", "HISTORICAL_PREDECESSOR"):
        rows = [r for r in final_sides.values()
                if r["stratum"] == stratum]
        pos = [r for r in rows
               if r["evaluator_verdict"] == "BINDING_CORRECT"]
        stats[stratum] = {
            "positive_assertions": len(pos),
            "distinct_relations":
                len({r["semantic_relation_signature"] for r in pos}),
            "binding_sides": len(rows),
            "observed_false_bindings":
                sum(1 for r in rows if r["evaluator_verdict"]
                    == "FALSE_BINDING"),
            "wilson95": _wilson(len(pos), len(rows)),
            "before_positive": sum(
                1 for r in pos if r["side"] == "before"),
            "after_positive": sum(
                1 for r in pos if r["side"] == "after"),
        }
    # mechanism attribution (§60)
    mech = {}
    for r in delta_rows:
        if not r["coverage_credit"]:
            continue
        m = r["generic_fix_id"]
        mech[m] = mech.get(m, 0) + 1
    # debt matrix (§61)
    matrix = {}
    final_debt = _debt(FINAL)
    for key, cls in base_debt.items():
        f = final_sides.get(key)
        converted = f is not None \
            and f["evaluator_verdict"] == "BINDING_CORRECT"
        slot = matrix.setdefault(
            final_sides.get(key, base_sides.get(key, {}))
            .get("stratum", "CURRENT_OPERATIONAL"), {})
        row = slot.setdefault(cls, {
            "baseline": 0, "converted": 0, "still_abstained": 0,
            "became_ambiguous": 0, "became_not_found": 0})
        row["baseline"] += 1
        if converted:
            row["converted"] += 1
        elif f and f["runtime_binding_status"] == "AMBIGUOUS":
            row["became_ambiguous"] += 1
        elif f and f["runtime_binding_status"] == "NOT_FOUND":
            row["became_not_found"] += 1
        else:
            row["still_abstained"] += 1
    final_metrics = {
        "baseline_run": "000-baseline",
        "final_run": "003-final",
        "cov_metrics": final_run["cov_metrics"],
        "baseline_metrics": base_run["cov_metrics"],
        "stratum_stats": stats,
        "mechanism_attribution": mech,
        "debt_matrix": matrix,
        "audit_amendments": final_run["audit_amendments"],
    }
    (COV2 / "final-metrics.json").write_text(
        json.dumps(final_metrics, indent=2, ensure_ascii=False,
                   sort_keys=True), encoding="utf-8")

    # -- VERDICT.json (§64–§66, §72) ------------------------------------
    c = final_run["cov_metrics"]["CURRENT_OPERATIONAL"]
    h = final_run["cov_metrics"]["HISTORICAL_PREDECESSOR"]
    hb = base_run["cov_metrics"]["HISTORICAL_PREDECESSOR"]
    gates = {
        "current_positive_bindings_>=443":
            c["positive_binding_assertions"] >= 443,
        "current_relations_>=519": c["relations_emitted"] >= 519,
        "current_locator_proven_>=445":
            c["locator_proven_ops"] >= 445,
        "leaf_operation_accounting_100":
            c["leaf_operation_accounting"] is True,
        "false_counts_zero": all(
            c[k] == 0 for k in (
                "false_fact", "false_binding",
                "false_subject_attribution",
                "false_locator_declaration")),
        "historical_floors":
            h["relations_emitted"] >= hb["relations_emitted"]
            and h["positive_binding_assertions"]
            >= hb["positive_binding_assertions"]
            and h["locator_proven_ops"] >= hb["locator_proven_ops"]
            and h["leaf_operation_accounting"] is True,
        "audit_amendments_zero": final_run["audit_amendments"] == 0,
        "all_bound_independently_verified":
            stats["CURRENT_OPERATIONAL"]["observed_false_bindings"] == 0
            and not any(
                r["runtime_binding_status"] == "BOUND"
                and r["evaluator_verdict"] != "BINDING_CORRECT"
                for r in final_sides.values()),
    }
    verdict = {
        "cov2_dev": "PASS" if all(gates.values())
                    else "FAIL_COVERAGE_TARGET"
                    if gates["false_counts_zero"] else
                    "FAIL_FACTUAL_INTEGRITY",
        "gates": gates,
        "cov3_readiness": "NOT_READY_FOR_COV_3",
        "cov3_selection": "STOP — CURRENT_OPERATIONAL eligible 0 < 3; "
                          "holdout UNMATERIALIZABLE; fresh-corpus "
                          "validation deferred to a separate "
                          "preregistration",
        "final_run": "runs/003-final",
        "runtime_head": final_run["runtime_head"],
        "src_tree_sha256": final_run["src_tree_sha256"],
        "evaluator_sha256": final_run["evaluator_sha256"],
        "evaluation_head": final_run["evaluation_head"],
        "current": {
            "positive_binding_assertions":
                c["positive_binding_assertions"],
            "relations_emitted": c["relations_emitted"],
            "locator_proven_ops": c["locator_proven_ops"],
            "before_positive": c["before_positive"],
            "after_positive": c["after_positive"],
        },
        "baseline_current": {
            "positive_binding_assertions":
                base_run["cov_metrics"]["CURRENT_OPERATIONAL"]
                ["positive_binding_assertions"],
        },
    }
    (COV2 / "VERDICT.json").write_text(
        json.dumps(verdict, indent=2, ensure_ascii=False,
                   sort_keys=True), encoding="utf-8")

    print(json.dumps({"delta_rows": len(delta_rows),
                      "coverage_credits":
                          sum(1 for r in delta_rows
                              if r["coverage_credit"]),
                      "fixes": len(fix_rows),
                      "gates": gates,
                      "cov2_dev": verdict["cov2_dev"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
