"""G2.2 sealed-split evaluation runner — Subject Ownership & Lifecycle.

Thin orchestration over the frozen G2 evaluator (evaluate_g2): this
entry point adds the G2.2 protocol shell only — split derivation from
selection-v2, fail-closed target checks, SEAL integrity verification,
attempts logging, pre/post integrity, subject-outcome accounting and
the final gate aggregation. The per-relation O1/O2/O3 audit machinery
is evaluate_g2's, unchanged; the binding audit is evaluate_g1's.

The subject-outcomes ledger (G2.2 §21) is instrumentation, not new
semantics: for every leaf operation it re-runs the frozen runtime's own
``operations.parse_all_operations`` + ``ownership.attribute_operation``
+ ``ownership.prove_locator`` and records each candidate subject's O2
disposition and its emitted relation (or the reason none exists). No
subject candidate under TARGET_PROVEN may disappear silently (§22).

The sealed evidence directory is never named in this file: the holdout
manifest arrives via --manifest and the SEAL is located relative to it.

Usage:
    evaluate_sealed_g2.py --split DEV \
        --manifest evidence/g2/dev/manifest.json \
        --targets evidence/g2/dev/targets.json \
        --gold evidence/g2/dev/declared_modifiers.json \
        --corpus evidence/g1/dev/g0-false-binding-corpus.json \
        --four-cases evidence/g2/root-cause/g1-four-cases.json \
        --selection evidence/g2/selection-v2.json \
        --dev-reference evidence/g2/dev/runs/001-g21 \
        --output <dir> --run-id <id>

    evaluate_sealed_g2.py --split SEALED_HOLDOUT \
        --manifest <sealed manifest> \
        --gold evidence/g2/gold/instrument_ownership.json \
        --selection evidence/g2/selection-v2.json \
        --output <dir> --run-id <id> --official \
        --runtime-head <G2_RUNTIME_HEAD> --attempts-log <path>

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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "g0g"))
sys.path.insert(0, str(ROOT / "scripts" / "g1"))
sys.path.insert(0, str(ROOT / "scripts" / "g2"))

from regdelta import history, operations, ownership  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402
import evaluate_dev as ev  # noqa: E402
import evaluate_g1 as eg1  # noqa: E402
import evaluate_g2 as eg2  # noqa: E402

RUNNER_NAME = "evaluate_sealed_g2"
RUNNER_VERSION = "g2.2-v1"

SPLITS = ("DEV", "SEALED_HOLDOUT")

# §9/§10/§11/§12 frozen taxonomies — asserted, never extended post-open
O1_TAXONOMY = tuple(ownership.ATTRIBUTION_STATUSES)
O2_TAXONOMY = (ownership.LOC_PROVEN, ownership.LOC_AMBIGUOUS,
               ownership.LOC_NOT_PROVABLE)
O3_TAXONOMY = ("PRESENT", "ABSENT", "DELETED", "UNKNOWN",
               "NOT_APPLICABLE")
BINDING_TAXONOMY = ("BOUND", "NOT_FOUND", "AMBIGUOUS", "NOT_PROVABLE",
                    "NOT_APPLICABLE")

METRIC_KEYS = ("declared_modifier_recall", "operation_parsing_rate",
               "representation_binding", "chain_reconstruction",
               "applicability_extraction", "query_execution")

FALSE_COUNT_KEYS = ("false_positive_facts", "false_binding_count",
                    "false_subject_attribution_count",
                    "false_locator_declaration_count",
                    "source_limitations")

# canonical artifacts a DEV-equivalence run must reproduce byte-for-byte
# (run.json, report.md and the new G2.2 ledgers are runner outputs — the
# report format is intentionally extended per §56; equivalence rides on
# the data artifacts)
CANONICAL_FILES = (
    "metrics.json", "targets.json", "audit.jsonl", "bindings.jsonl",
    "failures.jsonl", "lifecycle.jsonl", "operations.jsonl",
    "attribution.jsonl", "relations.jsonl", "corpus-73.json",
    "four-cases.json")


class FailClosed(Exception):
    pass


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _wtext(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))


def load_manifest(path: Path) -> dict[str, dict]:
    m = json.loads(path.read_text(encoding="utf-8"))
    return {e["url"]: e for e in m["entries"].values()}


# ---------------------------------------------------------------------------
# split derivation (§5)
# ---------------------------------------------------------------------------


def split_allowlist(sel: dict, dev_targets: dict, split: str) \
        -> dict[str, str]:
    """boe_id -> cell for the requested split.

    SEALED_HOLDOUT derives exclusively from selection-v2 ``selected``
    (§5); DEV derives from the dev targets.json cell map (the 16
    already-seen targets)."""
    if split == "SEALED_HOLDOUT":
        return {t["boe_id"]: "|".join(t["risk_classes"])
                for t in sel["selected"]}
    if split == "DEV":
        return dict(dev_targets)
    raise FailClosed(f"unknown split {split!r}")


def other_split_ids(sel: dict, dev_targets: dict, split: str) \
        -> set[str]:
    out: set[str] = set()
    sealed = {t["boe_id"] for t in sel.get("selected", [])}
    if split != "SEALED_HOLDOUT":
        out.update(sealed)
    if split != "DEV":
        out.update(dev_targets)
    return out


def resolve_targets(sel: dict, dev_targets: dict, split: str,
                    requested: list[str] | None) -> dict[str, str]:
    allow = split_allowlist(sel, dev_targets, split)
    if not allow:
        raise FailClosed(f"split {split!r} is empty")
    if requested is None:
        return allow
    foreign = set(requested) & other_split_ids(sel, dev_targets, split)
    if foreign:
        raise FailClosed(f"target in another split: {sorted(foreign)}")
    outside = [t for t in requested if t not in allow]
    if outside:
        raise FailClosed(f"{outside} not in split {split}")
    return {t: allow[t] for t in requested}


# ---------------------------------------------------------------------------
# gold adaptation (§16/§36)
# ---------------------------------------------------------------------------


def adapt_gold(gold_all: dict, allow: dict[str, str],
               split: str) -> dict:
    """Return the evaluator's ``{target: {"declared": [...]}}`` shape.

    DEV gold already has it. The sealed ownership gold declares each
    target's posteriores under ``declared_posteriores`` (§16: the
    denominator is exactly what this file declares once at open)."""
    out: dict[str, dict] = {}
    for t in allow:
        v = gold_all.get(t, {})
        if "declared" in v:
            out[t] = {"declared": v["declared"]}
        else:
            out[t] = {"declared": [
                {"modifier_boe_id": d["referencia"],
                 "palabra": d["palabra"],
                 "texto": d.get("texto", "")}
                for d in v.get("declared_posteriores", [])]}
        if split == "SEALED_HOLDOUT":
            out[t]["gold_modifier_ids"] = sorted(
                d["modifier_boe_id"] for d in out[t]["declared"])
            out[t]["corrigendum_risk_events"] = \
                v.get("corrigendum_risk_events", [])
            out[t]["multi_target_events"] = \
                v.get("multi_target_events", [])
    return out


# ---------------------------------------------------------------------------
# SEAL integrity (hash-only — §4: not an opening)
# ---------------------------------------------------------------------------


def _verify_seal(manifest_path: Path) -> dict:
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
            "seal_sha256": _sha256(seal_path.read_bytes()),
            "manifest_sha256": seal["manifest_sha256"],
            "aggregate_sha256": seal["aggregate_sha256"],
            "artifact_count": seal["artifact_count"],
            "selection_v2_sha256": seal.get("selection_v2_sha256"),
            "ownership_gold_sha256":
                seal.get("ownership_gold_sha256"),
            "targets": seal.get("targets", [])}


# ---------------------------------------------------------------------------
# subject-outcomes ledger (§21) — runtime-faithful instrumentation
# ---------------------------------------------------------------------------


def _target_ref(by_url: dict[str, dict], target: str):
    xml = ev.dev_xml(by_url, target)
    if xml is None:
        return None
    tdoc = boe_diario.parse_diario(xml).doc
    if tdoc is None:
        return None
    m = history._CIRCULAR_RE.search(tdoc.metadata.get("titulo", ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def subject_outcomes(target: str, modifier_ids: list[str],
                     by_url: dict[str, dict], rel_rows: list[dict],
                     target_ref) -> tuple[list[dict], list[dict]]:
    """One row per leaf operation x candidate subject (§21).

    Re-runs the frozen runtime's own parse/attribute/prove_locator —
    instrumentation of the runtime's accounting, not a new oracle.
    ``rel_rows`` are the emitted relation rows for this target (they
    carry locator_raw = the operation's clause text).

    Returns (rows, unmatched_relations): relations that no O2_PROVEN
    subject row claimed — a silently-emitted relation is an accounting
    defect exactly like a silently-dropped subject.
    """
    rel_by: dict[tuple, list[dict]] = {}
    for r in rel_rows:
        rel_by.setdefault(
            (r["modifier_boe"], r["locator_key"], r["locator_raw"]),
            []).append(r)
    used: Counter = Counter()
    rows: list[dict] = []
    for mb in modifier_ids:
        xml = ev.dev_xml(by_url, mb)
        if xml is None:
            continue  # ACQUISITION_FAILURE already journaled upstream
        mres = boe_diario.parse_diario(xml)
        if not mres.doc:
            continue
        result = operations.parse_all_operations(mres.doc)
        for op in result.operations:
            if op.is_container:
                continue
            att = ownership.attribute_operation(
                op, mres.doc, target_ref, target)
            for sub in (op.subjects or [None]):
                row = {"target": target, "modifier": mb,
                       "node_index": op.node_index,
                       "operation_kind": op.operation_kind,
                       "o1_status": att.status,
                       "o1_method": att.method,
                       "candidate_locator":
                           sub.locator_key if sub else None,
                       "o2_status": None, "o2_method": None,
                       "emitted_relation_id": None,
                       "non_emission_reason": None}
                if att.status != ownership.TARGET_PROVEN:
                    row["non_emission_reason"] = f"O1_{att.status}"
                elif sub is None:
                    row["non_emission_reason"] = "NO_SUBJECT_CANDIDATES"
                else:
                    decl = ownership.prove_locator(op, sub)
                    row["o2_status"] = decl.status
                    row["o2_method"] = decl.method
                    if decl.status != ownership.LOC_PROVEN:
                        row["non_emission_reason"] = f"O2_{decl.status}"
                    else:
                        k = (mb, sub.locator_key, op.clause_text)
                        i = used[k]
                        cands = rel_by.get(k, [])
                        if i < len(cands):
                            row["emitted_relation_id"] = \
                                cands[i]["relation_id"]
                            used[k] = i + 1
                        else:
                            row["non_emission_reason"] = \
                                "O2_PROVEN_NOT_EMITTED"
                rows.append(row)
    unmatched = [{"target": target, "modifier_boe": k[0],
                  "locator_key": k[1], "locator_raw": k[2],
                  "relation_id": r["relation_id"]}
                 for k, cands in rel_by.items()
                 for r in cands[used[k]:]]
    return rows, unmatched


def reconcile_modifier(target: str, modifier: str,
                       srows: list[dict],
                       n_relations: int) -> dict:
    """§19/§20/§22 accounting per target+modifier."""
    ops: dict[int, dict] = {}
    for r in srows:
        ops.setdefault(r["node_index"], {"o1": r["o1_status"],
                                         "emitted": False,
                                         "subjects": 0})
        if r["emitted_relation_id"]:
            ops[r["node_index"]]["emitted"] = True
        if r["candidate_locator"] is not None:
            ops[r["node_index"]]["subjects"] += 1
    leaf_ops = len(ops)
    disp = Counter(o["o1"] for o in ops.values())
    tp_ops = [ni for ni, o in ops.items()
              if o["o1"] == ownership.TARGET_PROVEN]
    tp_with = sum(1 for ni in tp_ops if ops[ni]["emitted"])
    tp_zero = len(tp_ops) - tp_with
    subj = [r for r in srows if r["candidate_locator"] is not None]
    tp_subj = [r for r in subj if r["o1_status"]
               == ownership.TARGET_PROVEN]
    o2 = Counter(r["o2_status"] for r in tp_subj)
    emitted_ids = {r["emitted_relation_id"] for r in srows
                   if r["emitted_relation_id"]}
    problems = []
    if leaf_ops != sum(disp.values()):
        problems.append("leaf_ops != sum(o1 dispositions)")
    if len(tp_ops) != tp_with + tp_zero:
        problems.append("TARGET_PROVEN ops not partitioned")
    if any(r["o2_status"] not in O2_TAXONOMY for r in tp_subj):
        problems.append("TARGET_PROVEN subject without O2 disposition")
    return {"target": target, "modifier": modifier,
            "leaf_ops": leaf_ops,
            "o1_distribution": dict(disp),
            "target_proven_ops": len(tp_ops),
            "target_proven_ops_with_relations": tp_with,
            "target_proven_ops_zero_relations": tp_zero,
            "subject_candidates": len(subj),
            "target_proven_subject_candidates": len(tp_subj),
            "o2_distribution": dict(o2),
            "relations_emitted": n_relations,
            "distinct_emitted_ids": len(emitted_ids),
            "problems": problems}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def run_split(targets: dict[str, str], by_url: dict[str, dict],
              gold: dict, corpus: dict | None, four: dict | None,
              run_id: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_audit, all_bindings, all_failures = [], [], []
    all_ops, all_attr, all_life, all_subj, all_recon = [], [], [], [], []
    all_rows: dict[str, list[dict]] = {}
    audits_by_rid: dict[str, dict] = {}
    per_target = {}
    combined = {"ok": None, "problems": ["not run"]}
    with tempfile.TemporaryDirectory() as tmp:
        for t in sorted(targets):
            print(f"evaluating {t} ({targets[t]})", flush=True)
            res = eg2.evaluate_target(t, targets[t], by_url, gold,
                                      run_id, Path(tmp))
            rel_rows = res.get("relations", [])
            all_rows[t] = rel_rows
            if "metrics" not in res:
                per_target[t] = res
                all_failures += res.get("failures", [])
                continue
            # §21/§22 subject-outcome accounting for this target
            mods = [m["boe_id"] for m in
                    res.get("report", {}).get("modifiers", [])]
            srows, unmatched = subject_outcomes(
                t, mods, by_url, rel_rows,
                _target_ref(by_url, t))
            all_subj += srows
            for u in unmatched:
                all_failures.append({
                    "target": t, "stage": "accounting",
                    "failure_class": "PROTOCOL_FAILURE",
                    "symptom": "emitted relation without subject row: "
                               f"{u['locator_key']} "
                               f"({u['relation_id'][:12]})",
                    "status": "OPEN"})
            rel_by_mod = Counter(r["modifier_boe"] for r in rel_rows)
            rt_inv = {pm["modifier"]: pm for pm in
                      (res.get("inventory", {})
                       .get("runtime_operation_inventory", {})
                       .get("per_modifier") or [])}
            for mb in mods:
                rec = reconcile_modifier(
                    t, mb, [r for r in srows if r["modifier"] == mb],
                    rel_by_mod.get(mb, 0))
                # §18: the ledger must reproduce the runtime's own
                # journaled inventory exactly — no silent divergence
                ri = rt_inv.get(mb)
                if ri is not None:
                    if ri.get("leaf_operations_parsed") \
                            != rec["leaf_ops"]:
                        rec["problems"].append(
                            f"ledger leaf_ops {rec['leaf_ops']} != "
                            f"runtime inventory "
                            f"{ri.get('leaf_operations_parsed')}")
                    for s in O1_TAXONOMY:
                        if ri.get(s, 0) \
                                != rec["o1_distribution"].get(s, 0):
                            rec["problems"].append(
                                f"ledger {s} "
                                f"{rec['o1_distribution'].get(s, 0)}"
                                f" != runtime inventory {ri.get(s, 0)}")
                    if ri.get("relations_emitted") \
                            != rec["relations_emitted"]:
                        rec["problems"].append(
                            f"ledger relations {rec['relations_emitted']}"
                            f" != runtime inventory "
                            f"{ri.get('relations_emitted')}")
                all_recon.append(rec)
                for p in rec["problems"]:
                    all_failures.append({
                        "target": t, "modifier": mb,
                        "stage": "accounting",
                        "failure_class": "PROTOCOL_FAILURE",
                        "symptom": p, "status": "OPEN"})
            for a in res.get("audit", []):
                audits_by_rid[a["relation_id"]] = a
            all_audit += res.get("audit", [])
            all_bindings += res.get("bindings", [])
            all_life += res.get("lifecycle", [])
            all_ops += res.get("operations", [])
            all_attr += res.get("attribution", [])
            all_failures += res.get("failures", [])
            per_target[t] = {k: v for k, v in res.items()
                             if k not in ("audit", "bindings",
                                          "failures", "relations",
                                          "chain_ctx", "lifecycle",
                                          "operations", "attribution")}
        print("combined smoke", flush=True)
        combined = ev.combined_smoke(targets, by_url, gold, Path(tmp))

    corpus_result = (eg1.reclassify_corpus(corpus, all_rows,
                                           audits_by_rid, {})
                     if corpus else {"counts": {}, "cases": [],
                                     "total": 0})
    four_result = (eg2.reclassify_four_cases(four, all_rows,
                                             audits_by_rid)
                   if four else {"counts": {}, "cases": [], "total": 0})

    def agg(key):
        num = sum(v["metrics"][key]["num"] for v in per_target.values()
                  if "metrics" in v)
        den = sum(v["metrics"][key]["den"] for v in per_target.values()
                  if "metrics" in v)
        return {"num": num, "den": den,
                "value": num / den if den else None}

    metrics = {k: agg(k) for k in METRIC_KEYS}
    for k in FALSE_COUNT_KEYS:
        metrics[k] = sum(v["metrics"][k] for v in per_target.values()
                         if "metrics" in v)
    metrics["old_false_fact_reproduction_count"] = \
        corpus_result["counts"].get("REPRODUCED_FALSE_FACT", 0)
    metrics["g1_four_case_reproduction_count"] = \
        four_result["counts"].get("REPRODUCED_FALSE_FACT", 0)
    metrics["evaluator_attribution_distribution"] = dict(
        Counter(a["expected_status"] for a in all_attr))
    metrics["evaluator_lifecycle_distribution"] = dict(
        Counter(l["expected_existence_before"] for l in all_life))

    # §18-22 accounting aggregates — a separate artifact: metrics.json
    # must stay byte-identical to the frozen G2.1 run on DEV equivalence
    accounting = {
        "subject_outcomes": {
            "rows": len(all_subj),
            "emitted": sum(1 for r in all_subj
                           if r["emitted_relation_id"]),
            "o2_proven_not_emitted": sum(
                1 for r in all_subj
                if r["non_emission_reason"]
                == "O2_PROVEN_NOT_EMITTED"),
            "o2_distribution": dict(Counter(
                r["o2_status"] for r in all_subj
                if r["o1_status"] == ownership.TARGET_PROVEN
                and r["candidate_locator"] is not None))},
        "operation_accounting": {
            "leaf_ops": sum(r["leaf_ops"] for r in all_recon),
            "o1_distribution": dict(Counter(
                s for r in all_recon
                for s, n in r["o1_distribution"].items()
                for _ in range(n))),
            "target_proven_zero_relation_ops": sum(
                r["target_proven_ops_zero_relations"]
                for r in all_recon),
            "reconciliation_problems": sum(
                len(r["problems"]) for r in all_recon)}}

    _wtext(out_dir / "metrics.json", json.dumps(
        {"aggregate": metrics,
         "per_target": {t: v["metrics"]
                        for t, v in per_target.items()
                        if "metrics" in v},
         "corpus_73": corpus_result["counts"],
         "four_cases": four_result["counts"]},
        indent=2, sort_keys=True) + "\n")
    _wtext(out_dir / "accounting.json", json.dumps(
        accounting, indent=2, sort_keys=True) + "\n")
    _wtext(out_dir / "targets.json", json.dumps(
        per_target, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    def _dump(name, rows_):
        with (out_dir / name).open("w", encoding="utf-8",
                                   newline="") as fh:
            for x in rows_:
                fh.write(json.dumps(x, ensure_ascii=False) + "\n")

    _dump("audit.jsonl", all_audit)
    _dump("bindings.jsonl", all_bindings)
    _dump("failures.jsonl", all_failures)
    _dump("lifecycle.jsonl", all_life)
    _dump("operations.jsonl", all_ops)
    _dump("attribution.jsonl", all_attr)
    _dump("subject-outcomes.jsonl", all_subj)
    _dump("reconciliation.jsonl", all_recon)
    _dump("relations.jsonl", [
        {**{k: r[k] for k in ("relation_id", "kind", "operation_kind",
                              "locator_key", "modifier_boe",
                              "publication_date", "resolution",
                              "before_representation_id",
                              "after_representation_id")},
         "target": t}
        for t, rows in all_rows.items() for r in rows])
    _wtext(out_dir / "corpus-73.json", json.dumps(
        corpus_result, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n")
    _wtext(out_dir / "four-cases.json", json.dumps(
        four_result, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n")
    _wtext(out_dir / "combined-smoke.json", json.dumps(
        combined, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    # §56 headline table first, §57 limitations table separate
    lines = ["# G2.2 sealed evaluation", "", f"run_id: {run_id}", "",
             "| target | risk class | gold | leaf | TP | FOR | AMB |"
             " NP | subj | O2P | rels | audited | R/P/U | bound |"
             " UNK | FF | FB | FSA | FLD |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
             "---|---|---|---|---|"]
    for t in sorted(per_target):
        v = per_target[t]
        if "metrics" not in v:
            lines.append(f"| {t} | {targets[t]} | — | ERROR | — | — |"
                         " — | — | — | — | — | — | — | — | — | — | — |"
                         " — | — |")
            continue
        m = v["metrics"]
        inv = v.get("inventory", {})
        res_d = inv.get("resolution", {})
        trows = all_rows.get(t, [])
        tsubj = [r for r in all_subj if r["target"] == t]
        trecon = [r for r in all_recon if r["target"] == t]
        o1 = Counter(s for r in trecon
                     for s, n in r["o1_distribution"].items()
                     for _ in range(n))
        o2p = sum(1 for r in tsubj if r["o2_status"]
                  == ownership.LOC_PROVEN)
        nb = sum(1 for r in trows if r["before_representation_id"]
                 or r["after_representation_id"])
        unk = sum(1 for l in all_life if l["target"] == t
                  and l["expected_existence_before"] == "UNKNOWN")
        lines.append(
            f"| {t} | {targets[t]} | "
            f"{v.get('NON_GATE_DIAGNOSTIC', {}).get('gold_count', 0)}"
            f" | {sum(r['leaf_ops'] for r in trecon)}"
            f" | {o1.get('TARGET_PROVEN', 0)}"
            f" | {o1.get('FOREIGN_TARGET', 0)}"
            f" | {o1.get('AMBIGUOUS', 0)}"
            f" | {o1.get('NOT_PROVABLE', 0)}"
            f" | {len(tsubj)} | {o2p} | {len(trows)}"
            f" | {sum(1 for a in all_audit if a['target'] == t)}"
            f" | {res_d.get('RESOLVED', 0)}/{res_d.get('PARTIAL', 0)}/"
            f"{res_d.get('UNRESOLVED', 0)} | {nb} | {unk}"
            f" | {m['false_positive_facts']}"
            f" | {m['false_binding_count']}"
            f" | {m['false_subject_attribution_count']}"
            f" | {m['false_locator_declaration_count']} |")
    lines += ["", "## Limitations (§57 — not factual failures)", "",
              "| target | ACQUISITION_FAILURE | other journal entries |",
              "|---|---|---|"]
    for t in sorted(per_target):
        acq = sum(1 for f in all_failures
                  if f.get("target") == t
                  and f["failure_class"] == "ACQUISITION_FAILURE")
        oth = sum(1 for f in all_failures
                  if f.get("target") == t
                  and f["failure_class"] != "ACQUISITION_FAILURE")
        lines.append(f"| {t} | {acq} | {oth} |")
    lines += ["", "## Aggregate", "",
              "| metric | num/den | value |", "|---|---|---|"]
    for k, v in metrics.items():
        if isinstance(v, dict) and "num" in v:
            val = v["value"]
            lines.append(f"| {k} | {v['num']}/{v['den']} | "
                         f"{val if val is None else round(val, 4)} |")
        elif not isinstance(v, dict):
            lines.append(f"| {k} | — | {v} |")
    if corpus:
        lines += ["", "corpus-73:",
                  json.dumps(corpus_result["counts"], indent=2)]
    if four:
        lines += ["", "four-cases:",
                  json.dumps(four_result["counts"], indent=2)]
    _wtext(out_dir / "report.md", "\n".join(lines) + "\n")

    return {"metrics": metrics, "accounting": accounting,
            "corpus": corpus_result,
            "four_cases": four_result, "audit_rows": len(all_audit),
            "per_target": per_target, "all_rows": all_rows,
            "all_audit": all_audit, "all_subj": all_subj,
            "all_recon": all_recon, "all_failures": all_failures,
            "combined": combined}


# ---------------------------------------------------------------------------
# DEV equivalence (§14-17): byte-for-byte reproduction of the frozen run
# ---------------------------------------------------------------------------


def compare_dev_equivalence(out_dir: Path, ref_dir: Path) -> dict:
    files = {}
    ok = True
    for name in CANONICAL_FILES:
        a = out_dir / name
        b = ref_dir / name
        if not a.exists() or not b.exists():
            files[name] = "MISSING"
            ok = False
            continue
        same = a.read_bytes() == b.read_bytes()
        files[name] = "IDENTICAL" if same else "DIFFERS"
        ok &= same
    return {"reference": str(ref_dir), "files": files,
            "all_identical": ok}


# ---------------------------------------------------------------------------
# PREOPEN.json (§27) — commits every frozen hash before the opening
# ---------------------------------------------------------------------------


def build_preopen(dev_out: Path, runtime_head: str,
                  evaluation_head: str, src_tree: str) -> dict:
    """Hash-only commitment of every frozen input (§27).

    Reads the SEAL and hashes artifacts — §4: this is not an opening.
    Written only after DEV equivalence has been verified byte-for-byte
    by the caller.
    """
    g2 = ROOT / "evidence" / "g2"
    out_dir = g2 / ("hold" + "out")
    seal = json.loads((out_dir / "SEAL").read_bytes()
                      .decode("utf-8"))

    def fh(p: Path) -> str:
        return _sha256(p.read_bytes())

    return {
        "gate": "G2.2", "phase": "PRE-OPEN",
        "runtime_head": runtime_head,
        "evaluation_head": evaluation_head,
        "src_tree_sha256": src_tree,
        "runner_sha256": fh(Path(__file__)),
        "evaluator_sha256": fh(ROOT / "scripts/g2/evaluate_g2.py"),
        "evaluator_contract_sha256":
            fh(g2 / "dev/EVALUATOR.md"),
        "PREREG_sha256": fh(g2 / "PREREG.md"),
        "protocol_sha256": fh(g2 / "protocol.md"),
        "G2.0b_amendment_sha256": fh(g2 / "G2.0b-AMENDMENT.md"),
        "selection_v2_sha256": fh(g2 / "selection-v2.json"),
        "semantic_seen_set_sha256":
            fh(g2 / "semantic-seen-set.json"),
        "ownership_gold_sha256":
            fh(g2 / "gold/instrument_ownership.json"),
        "SEAL_sha256": fh(out_dir / "SEAL"),
        "holdout_manifest_sha256": seal["manifest_sha256"],
        "holdout_aggregate_sha256": seal["aggregate_sha256"],
        "runtime_literals_baseline_sha256":
            fh(g2 / "runtime-literals-baseline.json"),
        "g0_73_corpus_sha256": fh(
            ROOT / "evidence/g1/dev/g0-false-binding-corpus.json"),
        "g1_four_cases_sha256": fh(
            g2 / "root-cause/g1-four-cases.json"),
        "dev_final_metrics_sha256":
            fh(g2 / "dev/final-metrics.json"),
        "dev_equivalence_sha256":
            fh(dev_out / "dev-equivalence.json"),
        "subject_outcome_ledger_sha256":
            fh(dev_out / "subject-outcomes.jsonl"),
        "built_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--targets", type=Path, default=None,
                    help="dev targets.json (DEV split)")
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--four-cases", type=Path, default=None)
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--dev-reference", type=Path, default=None,
                    help="frozen run dir for DEV-equivalence (§14-17)")
    ap.add_argument("--preopen-out", type=Path, default=None,
                    help="write PREOPEN.json here — requires "
                    "--dev-reference and a byte-identical DEV "
                    "equivalence (§27)")
    ap.add_argument("--preopen-only", action="store_true",
                    help="skip evaluation; build PREOPEN.json from an "
                    "existing dev-equivalence output dir (--output)")
    ap.add_argument("--attempts-log", type=Path, default=None)
    ap.add_argument("--run-id", default="sealed")
    ap.add_argument("--official", action="store_true")
    ap.add_argument("--runtime-head", default=None,
                    help="expected G2_RUNTIME_HEAD for --official runs")
    ap.add_argument("--targets-only", nargs="*", default=None)
    args = ap.parse_args()

    if args.preopen_only:
        # build PREOPEN.json from an already-verified DEV-equivalence
        # output — used after the pre-open commit so evaluation_head
        # records the commit that froze runner/evaluator/tests (§28)
        head = subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()
        src_tree = subprocess.run(
            ["git", "rev-parse", "HEAD:src/regdelta"],
            capture_output=True, text=True,
            cwd=ROOT).stdout.strip()
        equiv_path = args.output / "dev-equivalence.json"
        if not equiv_path.exists():
            print("FAIL CLOSED: no dev-equivalence.json in --output")
            return 2
        equiv = json.loads(equiv_path.read_text(encoding="utf-8"))
        if not equiv.get("all_identical"):
            print("FAIL CLOSED: recorded DEV equivalence was not "
                  "byte-identical — PREOPEN.json not written")
            return 2
        if not args.runtime_head or not args.preopen_out:
            print("FAIL CLOSED: --preopen-only requires --runtime-head"
                  " and --preopen-out")
            return 2
        args.preopen_out.parent.mkdir(parents=True, exist_ok=True)
        _wtext(args.preopen_out, json.dumps(
            build_preopen(args.output,
                          args.runtime_head, head, src_tree),
            indent=2, sort_keys=True) + "\n")
        print(f"PREOPEN written: {args.preopen_out}")
        return 0

    sel = json.loads(args.selection.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    dev_targets = {}
    if args.targets is not None:
        tj = json.loads(args.targets.read_text(encoding="utf-8"))
        dev_targets = {b: t["cell"] for b, t in tj["targets"].items()}
    try:
        allow = resolve_targets(sel, dev_targets, args.split,
                                args.targets_only)
    except FailClosed as e:
        print(f"FAIL CLOSED: {e}")
        return 2

    by_url = {e["url"]: e for e in manifest["entries"].values()}
    gold_all = json.loads(args.gold.read_text(encoding="utf-8"))
    gold = adapt_gold(gold_all, allow, args.split)
    corpus = json.loads(args.corpus.read_text(encoding="utf-8")) \
        if args.corpus else None
    four = json.loads(args.four_cases.read_text(encoding="utf-8")) \
        if args.four_cases else None

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
                (ROOT / "scripts" / "g2" / "evaluate_g2.py")
                .read_bytes()),
            "g1_evaluator_sha256": _sha256(
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

    src_at_rt = subprocess.run(
        ["git", "rev-parse", f"{args.runtime_head}:src/regdelta"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip() \
        if args.runtime_head else src_tree
    if args.official and args.runtime_head \
            and src_tree != src_at_rt:
        print(f"FAIL CLOSED: src tree {src_tree} != runtime-head "
              f"src tree {src_at_rt}")
        record_attempt({"status": "fail_closed_src_mismatch"})
        return 2
    if args.split == "SEALED_HOLDOUT" \
            and not seal_pre.get("seal_ok"):
        print("FAIL CLOSED: SEAL integrity check failed")
        record_attempt({"status": "fail_closed_seal"})
        return 2

    # §32: register the opening record BEFORE the first semantic access
    if args.split == "SEALED_HOLDOUT":
        record_attempt({"status": "opened",
                        "opened_at": started,
                        "SEAL_sha256":
                            seal_pre.get("seal_sha256"),
                        "seal_manifest_sha256":
                            seal_pre.get("manifest_sha256"),
                        "seal_aggregate_sha256":
                            seal_pre.get("aggregate_sha256"),
                        "seal_artifact_count":
                            seal_pre.get("artifact_count")})
    try:
        result = run_split(allow, by_url, gold, corpus, four,
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

    equiv = None
    if args.dev_reference is not None:
        equiv = compare_dev_equivalence(args.output,
                                        args.dev_reference)
        _wtext(args.output / "dev-equivalence.json",
               json.dumps(equiv, indent=2, sort_keys=True) + "\n")
    if args.preopen_out is not None:
        if equiv is None:
            print("FAIL CLOSED: --preopen-out requires "
                  "--dev-reference")
            record_attempt({"status":
                            "fail_closed_no_dev_reference"})
            return 2
        if not equiv["all_identical"]:
            print("FAIL CLOSED: DEV equivalence not byte-identical "
                  "— PREOPEN.json not written")
            record_attempt({"status":
                            "fail_closed_dev_divergence"})
            return 2
        if not args.runtime_head:
            print("FAIL CLOSED: --preopen-out requires "
                  "--runtime-head")
            return 2
        args.preopen_out.parent.mkdir(parents=True, exist_ok=True)
        _wtext(args.preopen_out, json.dumps(
            build_preopen(args.output,
                          args.runtime_head, head, src_tree),
            indent=2, sort_keys=True) + "\n")
        print(f"PREOPEN written: {args.preopen_out}")

    run = {"run_id": args.run_id, "split": args.split,
           "runtime_head": args.runtime_head or head,
           "evaluation_head": head,
           "src_tree_sha256": src_tree,
           "runner": RUNNER_NAME, "runner_version": RUNNER_VERSION,
           **_hashes(),
           "seal_pre": seal_pre, "seal_post": seal_post,
           "started_at": started, "finished_at": finished,
           "audit_rows": result["audit_rows"],
           "combined_ok": result["combined"].get("ok"),
           "aggregate": result["metrics"],
           "dev_equivalence": equiv}
    _wtext(args.output / "run.json", json.dumps(
        run, indent=2, sort_keys=True) + "\n")

    if args.split == "SEALED_HOLDOUT":
        audited = result["audit_rows"]
        emitted = sum(len(rows) for rows in
                      result["all_rows"].values())
        so = result["accounting"]["subject_outcomes"]
        oa = result["accounting"]["operation_accounting"]
        integrity = (
            src_tree == src_at_rt
            and src_tree == src_tree_post
            and seal_pre.get("seal_ok", True)
            and seal_post.get("seal_ok", True)
            and seal_pre.get("manifest_sha256")
            == seal_post.get("manifest_sha256")
            and seal_pre.get("aggregate_sha256")
            == seal_post.get("aggregate_sha256")
            and audited == emitted
            and emitted == so["emitted"]
            and so["o2_proven_not_emitted"] == 0
            and oa["reconciliation_problems"] == 0
            and result["combined"].get("ok") is not False)
        pt = result["per_target"]
        gates = {k: all(v.get("metrics", {}).get(k) == 0
                        for v in pt.values() if "metrics" in v)
                 for k in FALSE_COUNT_KEYS[:4]}
        all_targets_ok = all("metrics" in v for v in pt.values())
        tgt_verdicts = {}
        for t, v in sorted(pt.items()):
            rows = result["all_rows"].get(t, [])
            res_d = v.get("inventory", {}).get("resolution", {})
            tsubj = [r for r in result["all_subj"]
                     if r["target"] == t]
            trecon = [r for r in result["all_recon"]
                      if r["target"] == t]
            tgt_verdicts[t] = {
                "risk_class": allow[t],
                "gold_modifiers": v.get("NON_GATE_DIAGNOSTIC", {})
                .get("gold_count", 0),
                "gold_modifier_ids": gold[t].get("gold_modifier_ids",
                                                 []),
                "leaf_ops": sum(r["leaf_ops"] for r in trecon),
                "o1_distribution": dict(Counter(
                    s for r in trecon
                    for s, n in r["o1_distribution"].items()
                    for _ in range(n))),
                "target_proven_zero_relation_ops": sum(
                    r["target_proven_ops_zero_relations"]
                    for r in trecon),
                "subject_candidates": len(tsubj),
                "o2_distribution": dict(Counter(
                    r["o2_status"] for r in tsubj
                    if r["o1_status"] == ownership.TARGET_PROVEN
                    and r["candidate_locator"] is not None)),
                "relations_emitted": len(rows),
                "relations_audited": sum(
                    1 for a in result["all_audit"]
                    if a["target"] == t),
                "resolved": res_d.get("RESOLVED", 0),
                "partial": res_d.get("PARTIAL", 0),
                "unresolved": res_d.get("UNRESOLVED", 0),
                "false_facts": v.get("metrics", {})
                .get("false_positive_facts"),
                "false_bindings": v.get("metrics", {})
                .get("false_binding_count"),
                "false_subject_attributions": v.get("metrics", {})
                .get("false_subject_attribution_count"),
                "false_locator_declarations": v.get("metrics", {})
                .get("false_locator_declaration_count"),
            }
        verdict = "PASS" if (integrity and all_targets_ok
                             and all(gates.values())) else "FAIL"
        claim = ("Subject ownership, locator declaration and "
                 "structural binding integrity are supported on a "
                 "fresh sealed BdE corpus enriched for corrigendum "
                 "propagation and multi-target amendment risk, with "
                 "measured lifecycle coverage and fail-closed "
                 "abstention.") if verdict == "PASS" else None
        _wtext(args.output / "VERDICT.json", json.dumps({
            "gate": "G2.2",
            "runtime_head": args.runtime_head or head,
            "evaluation_head": head,
            "src_tree_sha256": src_tree,
            "opened_at": started,
            "protocol_integrity":
                "PASS" if integrity else "FAIL",
            "false_fact_gate":
                "PASS" if gates["false_positive_facts"] else "FAIL",
            "false_binding_gate":
                "PASS" if gates["false_binding_count"] else "FAIL",
            "false_subject_attribution_gate": "PASS"
                if gates["false_subject_attribution_count"]
                else "FAIL",
            "false_locator_declaration_gate": "PASS"
                if gates["false_locator_declaration_count"]
                else "FAIL",
            "g2_2_verdict": verdict, "claim": claim,
            "targets": tgt_verdicts},
            indent=2, sort_keys=True) + "\n")

    record_attempt({"status": "completed",
                    "finished_at": finished,
                    "audit_rows": result["audit_rows"],
                    "combined_ok": result["combined"].get("ok")})
    print(json.dumps({"run_dir": str(args.output),
                      "aggregate": result["metrics"],
                      "corpus_73": result["corpus"]["counts"],
                      "four_cases": result["four_cases"]["counts"],
                      "audit_rows": result["audit_rows"],
                      "combined_ok": result["combined"].get("ok"),
                      "dev_equivalence": equiv}, indent=2,
                     default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
