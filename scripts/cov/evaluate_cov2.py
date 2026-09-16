"""COV-2 DEV evaluator — representation-binding coverage ledger.

Extension of the frozen G2 evaluation stack (COV-2 §9), written and
frozen before any ``src/regdelta`` change for this gate. Per-target
reconstruction, the G1 binding audit and the O1/O2/O3 re-derivation
are reused verbatim (``evaluate_g2.evaluate_target`` plus the G2.2
subject-outcome/reconciliation instrumentation). This file adds the
COV-2 layer only:

  * stratum assignment per target (COV-1 §3 metadata rule over the
    target's own <metadatos>: vigencia_agotada/estatus_derogacion);
  * binding-sides.jsonl — the canonical COV-2 coverage ledger
    (§11): one row per modification_relation x {before, after};
  * semantic relation signatures (§12) — the stable baseline join
    key, independent of relation_id;
  * ordering.jsonl — every same-date hop group with the official
    ordering evidence (EXP-L1 prior: event date -> amending work
    date -> subtype -> natural number -> document position);
  * continuity.jsonl — every chain predecessor claim with its
    evaluator-derived predecessor and scope compatibility;
  * debt-census.json — §14 taxonomy over every unclaimed
    CURRENT_OPERATIONAL binding side;
  * cov-metrics.json — stratum-split COV-2 metrics.

Audit amendments (chain_predecessor claims only): the frozen audit
compares a non-chained bound before against the *hash-ordered* prior
hop. When the runtime declares an official-order basis
(binding_proof.before.order_basis) the evaluator re-derives the
predecessor from official metadata and re-adjudicates that claim —
recorded in audit-amendments.jsonl. With the unchanged baseline
runtime (no declared basis) zero amendments occur and every canonical
artifact stays byte-identical to the G2.1 reference.

A method string is never evidence: predecessor-claim methods are
re-checked against the evaluator's own ordering derivation and the
claimed representation equality; TEXT/TABLE/IMAGE claims keep the
frozen re-serialization checks.

Usage:
    uv run python -X utf8 scripts/cov/evaluate_cov2.py \
        --manifest evidence/g2/dev/manifest.json \
        --targets evidence/g2/dev/targets.json \
        --gold evidence/g2/dev/declared_modifiers.json \
        --corpus evidence/g1/dev/g0-false-binding-corpus.json \
        --four-cases evidence/g2/root-cause/g1-four-cases.json \
        --dev-reference evidence/g2/dev/runs/001-g21 \
        --output evidence/cov/cov2/runs/000-baseline \
        --run-id 000-baseline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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

from regdelta import ownership  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402
import evaluate_dev as ev  # noqa: E402
import evaluate_g1 as eg1  # noqa: E402
import evaluate_g2 as eg2  # noqa: E402
import evaluate_sealed_g2 as esg2  # noqa: E402

EVALUATOR_NAME = "evaluate_cov2"
EVALUATOR_VERSION = "cov2-v1"
SIGNATURE_VERSION = "cov2-rel-sig-v1"

STRATA = ("CURRENT_OPERATIONAL", "HISTORICAL_PREDECESSOR")

DEBT_CLASSES = (
    "NO_STRUCTURAL_CANDIDATE",
    "SUBJECT_SCOPE_NOT_PROVABLE",
    "NO_OPERATION_OWNED_CONTENT",
    "ANNEX_CODE_NOT_LOCATED",
    "TABLE_CONTENT_NOT_ENUMERATED",
    "ONLY_BROADER_PARENT_PROVABLE",
    "CHAIN_STATE_UNKNOWN",
    "CHAIN_STATE_DELETED",
    "CHAIN_SCOPE_COLLISION",
    "SAME_DATE_ORDER_UNPROVEN",
    "MISSING_CAPTURED_ARTIFACT",
    "AMBIGUOUS_MULTIPLE_CANDIDATES",
    "SIDE_NOT_APPLICABLE",
    "OTHER",
)

# predecessor-claim methods: the before representation is carried
# through a relation the runtime asserts as predecessor — never
# accepted without evaluator re-verification
PREDECESSOR_METHODS = (
    "CHAIN_PREDECESSOR",
    "SCOPE_QUALIFIED_CHAIN_PREDECESSOR",
    "OFFICIAL_SAME_DATE_PREDECESSOR",
    "REDESIGNATION_PREDECESSOR",
)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _wtext(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))


def _dump(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        for x in rows:
            fh.write(json.dumps(x, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# stratum (COV-1 §3 — same metadata rule as COV-3 selection)
# ---------------------------------------------------------------------------


def target_stratum(by_url: dict[str, dict], boe_id: str) -> str:
    xml = ev.dev_xml(by_url, boe_id)
    if xml is None:
        return "UNKNOWN"
    doc = boe_diario.parse_diario(xml).doc
    if doc is None:
        return "UNKNOWN"
    m = doc.metadata
    if (m.get("vigencia_agotada") == "S"
            or m.get("estatus_derogacion") == "S"):
        return "HISTORICAL_PREDECESSOR"
    return "CURRENT_OPERATIONAL"


# ---------------------------------------------------------------------------
# semantic relation signature (COV-2 §12 — frozen serialization)
# ---------------------------------------------------------------------------


def semantic_signature(target: str, modifier: str, node_index,
                       locator_key: str, operation_kind: str,
                       clause_text: str) -> str:
    """Stable comparison key: legal-operation identity, never
    relation_id. node_index is the operation's structural position in
    the frozen modifier document; clause identity is the sha256 of the
    normalized operative clause text."""
    clause_sha = hashlib.sha256(
        ev._norm(clause_text or "").encode("utf-8")).hexdigest()
    payload = (f"{SIGNATURE_VERSION}|{target}|{modifier}|"
               f"{node_index if node_index is not None else '?'}|"
               f"{locator_key}|{operation_kind}|{clause_sha}")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# evaluator-side ordering evidence (EXP-L1 prior, official metadata only)
# ---------------------------------------------------------------------------


def _numkey(num: str) -> tuple:
    return tuple(int(t) if t.isdigit() else t
                 for t in re.split(r"(\d+)", num or ""))


def _mod_meta(by_url: dict[str, dict], boe_id: str) -> dict:
    """Official ordering metadata from the captured diario XML —
    metadatos only, no normative opening."""
    out = {"fecha_disposicion": "", "rango": "", "numero_oficial": ""}
    xml = ev.dev_xml(by_url, boe_id)
    if xml is None:
        return out
    t = xml.decode("utf-8", errors="replace")
    for tag in out:
        m = re.search(rf"<{tag}[^>]*>\s*([^<]*)", t)
        if m:
            out[tag] = m.group(1).strip()
    return out


def _official_key(r: dict, mod_meta: dict, node) -> tuple:
    m = mod_meta.get(r["modifier_boe"], {})
    return (r["publication_date"] or "",
            m.get("fecha_disposicion") or "",
            m.get("rango") or "",
            _numkey(m.get("numero_oficial") or ""),
            node if node is not None else 1 << 30)


# ---------------------------------------------------------------------------
# scope signature (COV-2 §28) — from already-proven structural context
# ---------------------------------------------------------------------------


def scope_signature(r: dict) -> tuple | None:
    """Deterministic ScopeSignature for one relation hop (§28).

    Components: the locator's root family plus the proven enclosing
    scope — taken from a bound representation's structural_scope when
    the runtime proved one, else the locator root itself. A side with
    no proven structural context cannot establish a scope beyond the
    locator root (fail closed at chain time, §31)."""
    parts = r["locator_key"].split(".")
    head = parts[0]
    root = head.split(":", 1)[0]
    bound_scope = None
    for side in ("before", "after"):
        proof = (r.get("binding_proof") or {}).get(side) or {}
        chosen = proof.get("chosen") or {}
        sc = chosen.get("scope")
        if sc and sc not in ("document", "chain_predecessor",
                             "annex_pages", "modifier_annex_pages"):
            bound_scope = sc
            break
    return (root, bound_scope or head)


# ---------------------------------------------------------------------------
# debt census (COV-2 §14) — one primary class per unclaimed side
# ---------------------------------------------------------------------------


def _token_in_tables(doc: boe_diario.DiarioDoc,
                     locator_key: str) -> bool:
    """True when the subject's distinguishing token occurs inside at
    least one table row of ``doc`` — the existence question the
    frozen runtime could not answer."""
    if doc is None:
        return False
    parts = locator_key.split(".")
    head, _, body = parts[0].partition(":")
    if head == "fichero":
        token = ev._fichero_norm(body)

        def probe(cell):
            return token in ev._fichero_norm(cell)
    elif head == "estado":
        token = ev._norm(body)

        def probe(cell):
            return token in ev._norm(cell)
    else:
        token = ev._norm(ev._locator_token(locator_key))

        def probe(cell):
            return bool(re.search(rf"(?<!\w){re.escape(token)}(?!\w)",
                                  ev._norm(cell)))
    for n in doc.nodes:
        if n.kind == "table":
            for row in n.rows:
                if any(probe(c) for c in row):
                    return True
    return False


def classify_side(s: dict, docs: dict[str, boe_diario.DiarioDoc],
                  r: dict) -> str:
    """§14 primary class for one unclaimed binding side."""
    st = s["runtime_binding_status"]
    method = s["runtime_binding_method"] or ""
    reason = s["abstention_reason"] or ""
    if st == "NOT_APPLICABLE":
        return "SIDE_NOT_APPLICABLE"
    if st == "AMBIGUOUS":
        return "AMBIGUOUS_MULTIPLE_CANDIDATES"
    if method == "CHAIN_STATE":
        return ("CHAIN_STATE_DELETED" if "DELETED" in reason
                else "CHAIN_STATE_UNKNOWN")
    if method in ("SUBJECT_SCOPE", "CONTENT_POINTER_SCOPE"):
        return "SUBJECT_SCOPE_NOT_PROVABLE"
    if method == "NO_PROVEN_CONTENT":
        return "NO_OPERATION_OWNED_CONTENT"
    if "broader root annex" in reason:
        return "ONLY_BROADER_PARENT_PROVABLE"
    if "fetch failed" in reason:
        return "MISSING_CAPTURED_ARTIFACT"
    doc = docs.get(r["modifier_boe"]) if s["side"] == "after" \
        else docs.get(s["target"])
    if _token_in_tables(doc, r["locator_key"]):
        return "TABLE_CONTENT_NOT_ENUMERATED"
    if method in ("EXPLICIT_ANNEX_REFERENCE", "MODIFIER_ANNEX_PAGES",
                  "ANNEX_PAGE_MAPPING"):
        return "ANNEX_CODE_NOT_LOCATED"
    if st == "NOT_FOUND":
        return "NO_STRUCTURAL_CANDIDATE"
    return "OTHER"


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def run_cov2(targets: dict[str, str], by_url: dict[str, dict],
             gold: dict, corpus: dict | None, four: dict | None,
             run_id: str, out_dir: Path) -> dict:
    """G2.2-equivalent per-target evaluation plus the COV-2 ledgers.

    The canonical artifact set stays byte-comparable to the G2.1
    reference run as long as the runtime is unchanged and no audit
    amendment fires."""
    out_dir.mkdir(parents=True, exist_ok=True)
    strata = {t: target_stratum(by_url, t) for t in targets}

    all_audit, all_bindings, all_failures = [], [], []
    all_ops, all_attr, all_life, all_subj, all_recon = [], [], [], [], []
    all_rows: dict[str, list[dict]] = {}
    audits_by_rid: dict[str, dict] = {}
    per_target: dict[str, dict] = {}
    mod_meta: dict[str, dict] = {}
    amendments: list[dict] = []

    def meta(boe):
        if boe not in mod_meta:
            mod_meta[boe] = _mod_meta(by_url, boe)
        return mod_meta[boe]

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
            mods = [m["boe_id"] for m in
                    res.get("report", {}).get("modifiers", [])]
            srows, unmatched = esg2.subject_outcomes(
                t, mods, by_url, rel_rows, esg2._target_ref(by_url, t))
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
                rec = esg2.reconcile_modifier(
                    t, mb, [r for r in srows if r["modifier"] == mb],
                    rel_by_mod.get(mb, 0))
                ri = rt_inv.get(mb)
                if ri is not None:
                    if ri.get("leaf_operations_parsed") \
                            != rec["leaf_ops"]:
                        rec["problems"].append(
                            f"ledger leaf_ops {rec['leaf_ops']} != "
                            f"runtime inventory "
                            f"{ri.get('leaf_operations_parsed')}")
                    for s_ in esg2.O1_TAXONOMY:
                        if ri.get(s_, 0) \
                                != rec["o1_distribution"].get(s_, 0):
                            rec["problems"].append(
                                f"ledger {s_} "
                                f"{rec['o1_distribution'].get(s_, 0)}"
                                f" != runtime inventory {ri.get(s_, 0)}")
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

    node_of = {(r["target"], r["emitted_relation_id"]): r["node_index"]
               for r in all_subj if r["emitted_relation_id"]}
    sig_of: dict[str, str] = {}
    for t, rows in all_rows.items():
        for r in rows:
            sig_of[r["relation_id"]] = semantic_signature(
                t, r["modifier_boe"],
                node_of.get((t, r["relation_id"])),
                r["locator_key"], r["operation_kind"],
                r.get("locator_raw") or "")

    # -- ordering + continuity ledgers, expected predecessors ----------
    ordering_rows: list[dict] = []
    continuity_rows: list[dict] = []
    expected_prev_of: dict[str, dict | None] = {}
    for t, rows in all_rows.items():
        by_key: dict[str, list[dict]] = {}
        for r in rows:
            by_key.setdefault(r["locator_key"], []).append(r)
        for key, hops in by_key.items():
            frozen = sorted(hops, key=lambda r: (
                r["publication_date"] or "", r["relation_id"]))

            def okey(r):
                return _official_key(
                    r, {r["modifier_boe"]: meta(r["modifier_boe"])},
                    node_of.get((t, r["relation_id"])))

            official = sorted(hops, key=okey)
            ambiguous = len({okey(r) for r in hops}) < len(hops)
            by_date: dict[str, list[dict]] = {}
            for r in hops:
                by_date.setdefault(r["publication_date"] or "",
                                   []).append(r)
            for d, same in sorted(by_date.items()):
                if len(same) < 2:
                    continue
                ordering_rows.append({
                    "target": t, "locator_key": key,
                    "publication_date": d,
                    "hops": [{
                        "relation_id": r["relation_id"],
                        "modifier": r["modifier_boe"],
                        "operation_kind": r["operation_kind"],
                        "node_index": node_of.get(
                            (t, r["relation_id"])),
                        "fecha_disposicion":
                            meta(r["modifier_boe"])
                            ["fecha_disposicion"],
                        "rango": meta(r["modifier_boe"])["rango"],
                        "numero_oficial":
                            meta(r["modifier_boe"])
                            ["numero_oficial"]}
                        for r in same],
                    "official_order": [
                        r["relation_id"] for r in sorted(same,
                                                         key=okey)],
                    "frozen_order": [
                        r["relation_id"] for r in sorted(
                            same, key=lambda r: r["relation_id"])],
                    "outcome": ("ORDER_AMBIGUOUS"
                                if len({okey(r) for r in same})
                                < len(same)
                                else "ORDER_RESOLVED_OFFICIAL")})
            basis = frozen if ambiguous else official
            for i, r in enumerate(basis):
                expected_prev_of[r["relation_id"]] = (
                    {"relation_id": basis[i - 1]["relation_id"],
                     "after_representation_id":
                         basis[i - 1]["after_representation_id"],
                     "basis": ("ORDER_AMBIGUOUS_FALLBACK" if ambiguous
                               else "OFFICIAL")}
                    if i > 0 else None)
            scopes = {r["relation_id"]: scope_signature(r)
                      for r in hops}
            for i, r in enumerate(frozen):
                proof_b = (r.get("binding_proof") or {}).get(
                    "before") or {}
                prev_scope = (scopes.get(frozen[i - 1]["relation_id"])
                              if i else None)
                my_scope = scopes[r["relation_id"]]
                continuity_rows.append({
                    "target": t, "locator_key": key,
                    "relation_id": r["relation_id"],
                    "semantic_signature": sig_of[r["relation_id"]],
                    "modifier": r["modifier_boe"],
                    "operation_kind": r["operation_kind"],
                    "scope_signature": list(my_scope)
                    if my_scope else None,
                    "predecessor_scope_signature": list(prev_scope)
                    if prev_scope else None,
                    "scope_compatible":
                        (None if i == 0 or not prev_scope or not my_scope
                         else prev_scope == my_scope),
                    "declared_predecessor":
                        proof_b.get("predecessor_relation_id"),
                    "declared_method": proof_b.get("method"),
                    "declared_order_basis": proof_b.get("order_basis"),
                    "evaluator_predecessor":
                        (expected_prev_of.get(r["relation_id"]) or {})
                        .get("relation_id"),
                    "evaluator_basis": (expected_prev_of.get(
                        r["relation_id"]) or {}).get("basis"),
                    "hop_index": i, "hop_count": len(frozen)})

    # -- audit amendments (chain_predecessor under official order) ------
    for a in all_audit:
        claim = a["claims_checked"].get("chain_predecessor")
        if claim not in ("VERIFIED", "CONTRADICTED"):
            continue
        rid = a["relation_id"]
        t = a["target"]
        r = next((x for x in all_rows[t] if x["relation_id"] == rid),
                 None)
        if r is None:
            continue
        exp = expected_prev_of.get(rid)
        if exp is None or exp["basis"] == "ORDER_AMBIGUOUS_FALLBACK":
            continue
        prev_after = exp["after_representation_id"]
        bound_before = r["before_representation_id"]
        if prev_after is None or bound_before is None:
            continue
        if (bound_before == prev_after) != (claim == "VERIFIED"):
            new = "VERIFIED" if bound_before == prev_after \
                else "CONTRADICTED"
            amendments.append({
                "target": t, "relation_id": rid,
                "claim": "chain_predecessor",
                "frozen_verdict": claim, "cov2_verdict": new,
                "evaluator_predecessor": exp["relation_id"],
                "basis": exp["basis"]})
            a["claims_checked"]["chain_predecessor"] = new
            bad = [k for k, v in a["claims_checked"].items()
                   if v in ("CONTRADICTED", "BINDING_FALSE")]
            a["truth_verdict"] = "FALSE_FACT" if bad else "PASS"
            a["root_cause_class"] = sorted(
                {eg1.CLAIM_RCC.get(k, "QUERY_EVALUATION_FAILURE")
                 for k in bad})
            # refresh per-target metric mirrors
            pm = per_target.get(t, {}).get("metrics", {})
            if pm:
                delta = -1 if new == "VERIFIED" else 1
                pm["false_positive_facts"] = sum(
                    1 for x in all_audit if x["target"] == t
                    and x["truth_verdict"] == "FALSE_FACT")

    if amendments:
        # per-target false counts were computed pre-amendment inside
        # evaluate_target; recompute aggregate inputs consistently
        for t, v in per_target.items():
            if "metrics" not in v:
                continue
            taus = [a for a in all_audit if a["target"] == t]
            v["metrics"]["false_positive_facts"] = sum(
                1 for a in taus if a["truth_verdict"] == "FALSE_FACT")

    corpus_result = (eg1.reclassify_corpus(corpus, all_rows,
                                           audits_by_rid, {})
                     if corpus else {"counts": {}, "cases": [],
                                     "total": 0})
    four_result = (eg2.reclassify_four_cases(four, all_rows,
                                             audits_by_rid)
                   if four else {"counts": {}, "cases": [],
                                 "total": 0})

    def agg(key):
        num = sum(v["metrics"][key]["num"] for v in per_target.values()
                  if "metrics" in v)
        den = sum(v["metrics"][key]["den"] for v in per_target.values()
                  if "metrics" in v)
        return {"num": num, "den": den,
                "value": num / den if den else None}

    metrics = {k: agg(k) for k in esg2.METRIC_KEYS}
    for k in esg2.FALSE_COUNT_KEYS:
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

    _dump(out_dir / "audit.jsonl", all_audit)
    _dump(out_dir / "bindings.jsonl", all_bindings)
    _dump(out_dir / "failures.jsonl", all_failures)
    _dump(out_dir / "lifecycle.jsonl", all_life)
    _dump(out_dir / "operations.jsonl", all_ops)
    _dump(out_dir / "attribution.jsonl", all_attr)
    _dump(out_dir / "subject-outcomes.jsonl", all_subj)
    _dump(out_dir / "reconciliation.jsonl", all_recon)
    _dump(out_dir / "relations.jsonl", [
        {**{k: r[k] for k in ("relation_id", "kind",
                              "operation_kind", "locator_key",
                              "modifier_boe", "publication_date",
                              "resolution",
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
    _dump(out_dir / "audit-amendments.jsonl", amendments)

    # -- docs for independent verification ------------------------------
    docs: dict[str, boe_diario.DiarioDoc] = {}
    want = set(targets) | {r["modifier_boe"] for rows in
                           all_rows.values() for r in rows}
    for bid in sorted(want):
        xml = ev.dev_xml(by_url, bid)
        if xml is None:
            continue
        res = boe_diario.parse_diario(xml)
        if res.doc:
            docs[bid] = res.doc

    # -- binding-sides ledger (§11) --------------------------------------
    side_rows: list[dict] = []
    for t, rows in all_rows.items():
        for r in rows:
            a = audits_by_rid.get(r["relation_id"], {})
            claims = a.get("claims_checked", {})
            proof = r.get("binding_proof") or {}
            for side in ("before", "after"):
                sp = proof.get(side) or {}
                claim = claims.get(f"{side}_binding",
                                   "NO_BINDING_CLAIM")
                chosen = sp.get("chosen") or {}
                side_rows.append({
                    "target": t,
                    "stratum": strata.get(t, "UNKNOWN"),
                    "modifier": r["modifier_boe"],
                    "semantic_relation_signature":
                        sig_of[r["relation_id"]],
                    "runtime_relation_id": r["relation_id"],
                    "locator_key": r["locator_key"],
                    "side": side,
                    "operation_kind": r["operation_kind"],
                    "runtime_binding_status": sp.get("status"),
                    "runtime_binding_method": sp.get("method"),
                    "runtime_candidate_count":
                        sp.get("candidate_count"),
                    "evaluator_verdict": claim,
                    "representation_kind": r.get(f"{side}_kind"),
                    "evidence_scope": chosen.get("scope"),
                    "abstention_reason": sp.get("reason"),
                    "declared_order_basis": sp.get("order_basis"),
                    "evaluator_predecessor":
                        (expected_prev_of.get(r["relation_id"]) or {})
                        .get("relation_id")
                        if side == "before" else None})

    # -- debt census (§14) ------------------------------------------------
    rows_by_target = {t: {r["relation_id"]: r for r in rows}
                      for t, rows in all_rows.items()}
    census_rows = []
    for s in side_rows:
        if s["evaluator_verdict"] == "BINDING_CORRECT":
            continue
        rel = rows_by_target[s["target"]][s["runtime_relation_id"]]
        census_rows.append({**s, "debt_class": classify_side(
            s, docs, rel)})
    census = {
        "taxonomy": list(DEBT_CLASSES),
        "unclaimed_sides": len(census_rows),
        "current_operational": dict(Counter(
            s["debt_class"] for s in census_rows
            if s["stratum"] == "CURRENT_OPERATIONAL")),
        "historical_predecessor": dict(Counter(
            s["debt_class"] for s in census_rows
            if s["stratum"] == "HISTORICAL_PREDECESSOR")),
        "rows": census_rows}

    # -- cov metrics -------------------------------------------------------
    def _side_counts(pred):
        sel = [s for s in side_rows if pred(s)]
        return {
            "positive_binding_assertions": sum(
                1 for s in sel
                if s["evaluator_verdict"] == "BINDING_CORRECT"),
            "binding_sides": len(sel),
            "unclaimed_sides": sum(
                1 for s in sel
                if s["evaluator_verdict"] != "BINDING_CORRECT"),
            "before_positive": sum(
                1 for s in sel if s["side"] == "before"
                and s["evaluator_verdict"] == "BINDING_CORRECT"),
            "after_positive": sum(
                1 for s in sel if s["side"] == "after"
                and s["evaluator_verdict"] == "BINDING_CORRECT")}

    def _rel_counts(pred):
        rels = [r for t, rows in all_rows.items() for r in rows
                if pred(t)]
        tp_subj = [s for s in all_subj if pred(s["target"])
                   and s["o1_status"] == ownership.TARGET_PROVEN]
        return {
            "relations_emitted": len(rels),
            "leaf_operations": sum(
                r["leaf_ops"] for r in all_recon if pred(r["target"])),
            "target_proven_ops": sum(
                r["target_proven_ops"] for r in all_recon
                if pred(r["target"])),
            "locator_proven_ops": len({
                (s["modifier"], s["node_index"]) for s in tp_subj
                if s["o2_status"] == ownership.LOC_PROVEN}),
            "leaf_operation_accounting": all(
                not r["problems"] for r in all_recon
                if pred(r["target"])),
            "false_fact": sum(
                1 for a in all_audit if pred(a["target"])
                and a["truth_verdict"] == "FALSE_FACT"),
            "false_binding": sum(
                1 for a in all_audit if pred(a["target"])
                and a["false_binding"]),
            "false_subject_attribution": sum(
                1 for a in all_audit if pred(a["target"])
                and a["false_subject_attribution"]),
            "false_locator_declaration": sum(
                1 for a in all_audit if pred(a["target"])
                and a["false_locator_declaration"])}

    cov_metrics = {
        "signature_version": SIGNATURE_VERSION,
        "strata": strata,
        "audit_amendments": len(amendments),
        "ordering": {
            "same_date_groups": len(ordering_rows),
            "order_resolved_official": sum(
                1 for r in ordering_rows
                if r["outcome"] == "ORDER_RESOLVED_OFFICIAL"),
            "order_ambiguous": sum(
                1 for r in ordering_rows
                if r["outcome"] == "ORDER_AMBIGUOUS"),
            "official_differs_from_hash": sum(
                1 for r in ordering_rows
                if r["official_order"] != r["frozen_order"])},
        "continuity": {
            "chain_predecessor_claims": sum(
                1 for c in continuity_rows
                if c["declared_method"] in PREDECESSOR_METHODS),
            "scope_incompatible_hops": sum(
                1 for c in continuity_rows
                if c["scope_compatible"] is False)},
        "per_stratum": {
            st: {**_rel_counts(lambda t, st=st: strata.get(t) == st),
                 **_side_counts(lambda s, st=st: s["stratum"] == st)}
            for st in STRATA},
        "per_target": {
            t: {"stratum": strata.get(t),
                **_rel_counts(lambda tt, t=t: tt == t),
                **_side_counts(lambda s, t=t: s["target"] == t)}
            for t in sorted(targets)}}

    _dump(out_dir / "binding-sides.jsonl", side_rows)
    _dump(out_dir / "continuity.jsonl", continuity_rows)
    _dump(out_dir / "ordering.jsonl", ordering_rows)
    _wtext(out_dir / "debt-census.json", json.dumps(
        census, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    _wtext(out_dir / "cov-metrics.json", json.dumps(
        cov_metrics, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    _wtext(out_dir / "per-target.json", json.dumps(
        cov_metrics["per_target"], indent=2, sort_keys=True,
        ensure_ascii=False) + "\n")

    cur = cov_metrics["per_stratum"]["CURRENT_OPERATIONAL"]
    hist = cov_metrics["per_stratum"]["HISTORICAL_PREDECESSOR"]
    lines = ["# COV-2 DEV evaluation", "", f"run_id: {run_id}", "",
             "## CURRENT_OPERATIONAL headline", "",
             "| metric | value |", "|---|---|",
             f"| positive_binding_assertions | "
             f"{cur['positive_binding_assertions']} |",
             f"|   before | {cur['before_positive']} |",
             f"|   after | {cur['after_positive']} |",
             f"| binding_sides | {cur['binding_sides']} |",
             f"| relations_emitted | {cur['relations_emitted']} |",
             f"| leaf_operations | {cur['leaf_operations']} |",
             f"| target_proven_ops | {cur['target_proven_ops']} |",
             f"| locator_proven_ops | {cur['locator_proven_ops']} |",
             f"| leaf_operation_accounting | "
             f"{cur['leaf_operation_accounting']} |",
             f"| FALSE_FACT | {cur['false_fact']} |",
             f"| FALSE_BINDING | {cur['false_binding']} |",
             f"| FALSE_SUBJECT_ATTRIBUTION | "
             f"{cur['false_subject_attribution']} |",
             f"| FALSE_LOCATOR_DECLARATION | "
             f"{cur['false_locator_declaration']} |",
             "", "## HISTORICAL_PREDECESSOR", "",
             "| metric | value |", "|---|---|",
             f"| positive_binding_assertions | "
             f"{hist['positive_binding_assertions']} |",
             f"| relations_emitted | {hist['relations_emitted']} |",
             f"| locator_proven_ops | {hist['locator_proven_ops']} |",
             f"| leaf_operation_accounting | "
             f"{hist['leaf_operation_accounting']} |",
             f"| FALSE_* total | "
             f"{hist['false_fact'] + hist['false_binding'] + hist['false_subject_attribution'] + hist['false_locator_declaration']} |",
             "", f"audit_amendments: {len(amendments)}",
             f"same-date groups: "
             f"{cov_metrics['ordering']['same_date_groups']} "
             f"(resolved_official "
             f"{cov_metrics['ordering']['order_resolved_official']}, "
             f"ambiguous "
             f"{cov_metrics['ordering']['order_ambiguous']})"]
    _wtext(out_dir / "report.md", "\n".join(lines) + "\n")
    return {"metrics": metrics, "accounting": accounting,
            "corpus": corpus_result, "four_cases": four_result,
            "audit_rows": len(all_audit),
            "cov_metrics": cov_metrics,
            "binding_sides": len(side_rows),
            "amendments": len(amendments),
            "strata": strata, "combined": combined}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--targets", required=True, type=Path)
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--four-cases", type=Path, default=None)
    ap.add_argument("--dev-reference", type=Path, default=None)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--run-id", default="cov2")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    man = json.loads(args.manifest.read_text(encoding="utf-8"))
    by_url = {e["url"]: e for e in man["entries"].values()}
    tj = json.loads(args.targets.read_text(encoding="utf-8"))
    targets = {b: t["cell"] for b, t in tj["targets"].items()}
    if args.only:
        keep = set(args.only.split(","))
        targets = {b: c for b, c in targets.items() if b in keep}
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
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

    result = run_cov2(targets, by_url, gold, corpus, four,
                      args.run_id, args.output)
    finished = datetime.now(timezone.utc).isoformat()

    equiv = None
    if args.dev_reference is not None:
        equiv = esg2.compare_dev_equivalence(args.output,
                                             args.dev_reference)
        _wtext(args.output / "dev-equivalence.json", json.dumps(
            equiv, indent=2, sort_keys=True) + "\n")

    run = {
        "run_id": args.run_id,
        "runtime_head": head,
        "evaluation_head": head,
        "src_tree_sha256": src_tree,
        "evaluator": EVALUATOR_NAME,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_sha256": _sha256(Path(__file__).read_bytes()),
        "g2_runner_sha256": _sha256(
            (ROOT / "scripts/g2/evaluate_sealed_g2.py").read_bytes()),
        "g2_evaluator_sha256": _sha256(
            (ROOT / "scripts/g2/evaluate_g2.py").read_bytes()),
        "g1_evaluator_sha256": _sha256(
            (ROOT / "scripts/g1/evaluate_g1.py").read_bytes()),
        "g0g_evaluator_sha256": _sha256(
            (ROOT / "scripts/g0g/evaluate_dev.py").read_bytes()),
        "manifest_sha256": _sha256(args.manifest.read_bytes()),
        "targets_sha256": _sha256(args.targets.read_bytes()),
        "gold_sha256": _sha256(args.gold.read_bytes()),
        "started_at": started, "finished_at": finished,
        "audit_rows": result["audit_rows"],
        "audit_amendments": result["amendments"],
        "binding_sides": result["binding_sides"],
        "strata": result["strata"],
        "cov_metrics": result["cov_metrics"]["per_stratum"],
        "dev_equivalence": equiv,
    }
    _wtext(args.output / "run.json", json.dumps(
        run, indent=2, sort_keys=True) + "\n")
    cur = result["cov_metrics"]["per_stratum"]["CURRENT_OPERATIONAL"]
    print(json.dumps({
        "run_dir": str(args.output),
        "CURR": {k: cur[k] for k in (
            "positive_binding_assertions", "relations_emitted",
            "locator_proven_ops", "leaf_operation_accounting",
            "false_fact", "false_binding")},
        "amendments": result["amendments"],
        "dev_equivalence": equiv and equiv["all_identical"]},
        indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
