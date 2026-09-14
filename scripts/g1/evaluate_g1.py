"""G1 evaluator — truth verdict + root cause + binding outcomes.

Frozen BEFORE any G1.1 runtime change. Runs the 12 G1 DEV targets
(8 former GENERALIZATION_DEV + 4 former G0-G sealed targets) against
evidence/g1/dev/manifest.json via EVIDENCE_IMPORT only. Zero network.

Differences from the G0 evaluator:
  - every relation gets truth_verdict (PASS|FALSE_FACT) AND, per
    discrepancy, a root_cause_class from the closed G1 taxonomy;
  - binding claims report BINDING_CORRECT / BINDING_FALSE /
    BINDING_NOT_CHECKABLE / NO_BINDING_CLAIM;
  - operation-verb checks run against the operative clause, not the
    posteriores metadata text (the 54/73 metadata-scope defect);
  - chain predecessor claims are checked explicitly;
  - the 73 historical G0 FALSE_FACT cases are re-evaluated by stable
    semantic signature (target, modifier, locator_key, operation_kind),
    never by relation_id.

Usage:
    uv run python -X utf8 scripts/g1/evaluate_g1.py \
        --dev-manifest evidence/g1/dev/manifest.json \
        --corpus evidence/g1/dev/g0-false-binding-corpus.json \
        --output evidence/g1/dev/runs/000-baseline --run-id 000-baseline
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                    / "scripts" / "g0g"))

from regdelta import applicability, db as dbm, history  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402
import evaluate_dev as ev  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"

ROOT_CAUSES = {
    "SOURCE_LIMITATION", "ACQUISITION_FAILURE",
    "OPERATION_PARSER_FAILURE", "LOCATOR_RESOLUTION_FAILURE",
    "REPRESENTATION_BINDING_FAILURE", "CHAIN_FAILURE",
    "SCHEMA_FAILURE", "QUERY_EVALUATION_FAILURE",
}

CLAIM_RCC = {
    "modifier_declared": "OPERATION_PARSER_FAILURE",
    "kind_matches_palabra": "OPERATION_PARSER_FAILURE",
    "operation_verb_consistent": "OPERATION_PARSER_FAILURE",
    "target_locator_resolves": "LOCATOR_RESOLUTION_FAILURE",
    "subject_in_target": "LOCATOR_RESOLUTION_FAILURE",
    "before_binding": "REPRESENTATION_BINDING_FAILURE",
    "after_binding": "REPRESENTATION_BINDING_FAILURE",
    "chain_predecessor": "CHAIN_FAILURE",
    "resolution_consistent": "SCHEMA_FAILURE",
    "publication_date_matches": "OPERATION_PARSER_FAILURE",
}

_ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
          "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
          "11": "xi", "12": "xii", "13": "xiii", "14": "xiv",
          "15": "xv", "16": "xvi", "17": "xvii", "18": "xviii",
          "19": "xix", "20": "xx"}


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def xml_of(by_url: dict[str, dict], boe_id: str) -> bytes | None:
    e = by_url.get(f"https://www.boe.es/diario_boe/xml.php?id={boe_id}")
    if e is None or "path" not in e:
        return None
    return (ROOT / e["path"]).read_bytes()


# ---------------------------------------------------------------------------
# independent clause location (metadata-scope fix)
# ---------------------------------------------------------------------------

_HEAD_FORMS = {
    "norma": ("norma",),
    "anejo": ("anejo", "anexo"),
    "disp": ("disposicion",),
    "articulo": ("articulo",),
    "estado": ("estado",),
    "fichero": ("fichero",),
}


def _locator_mentions(key: str) -> tuple[list[str], list[str]]:
    """(head mention alternatives, deep mention alternatives) for an
    operative-clause search. 'norma:16.apartado:7' ->
    head: ['norma 16', 'norma decimosexta'], deep: ['apartado 7']."""
    parts = key.split(".")
    kind, _, body = parts[0].partition(":")
    tok = ev._norm(body)
    heads = []
    for h in _HEAD_FORMS.get(kind, (kind,)):
        heads.append(f"{h} {tok}")
        if kind == "disp" and len(parts) > 1:
            heads.append(f"{h} {tok} {ev._norm(parts[1])}")
    if kind in ("norma", "anejo", "anexo", "articulo"):
        word = ev._ORDINAL_WORDS.get(tok)
        for h in _HEAD_FORMS.get(kind, (kind,)):
            if word:
                heads.append(f"{h} {word}")
            if tok in _ROMAN:
                heads.append(f"{h} {_ROMAN[tok]}")
    deep = []
    for p in parts[1:]:
        k, _, v = p.partition(":")
        deep.append(f"{k} {ev._norm(v)}")
        deep.append(ev._norm(v))
    if not deep:
        deep = list(heads)
    return heads, deep


def find_op_clause(mdoc: boe_diario.DiarioDoc,
                   key: str) -> str | None:
    """Locate the operative clause in the modifier that governs the
    subject — used when relation_raw holds posteriores metadata text.
    Returns the text of the best clause node or None."""
    heads, deep = _locator_mentions(key)
    scored = []
    for n in mdoc.nodes:
        if not n.text:
            continue
        t = ev._norm(n.text)
        hs = any(h in t for h in heads)
        ds = any(d in t for d in deep)
        if hs and ds:
            scored.append((0, n.index, n.text))
        elif ds:
            scored.append((1, n.index, n.text))
    if not scored:
        return None
    scored.sort()
    return scored[0][2]


def _expected_op_for_subject(clause: str, key: str) -> str | None:
    """Verb check scoped to the sub-clause governing *this* subject.

    A single operative paragraph may hold several operations
    ("se modifica el apartado 3 y se añade el apartado 4"). The deep
    locator mention selects the governing segment; if that segment has
    no verb (shared-verb lists like "se modifican los apartados 2 y 4"),
    the search expands backwards until a verb is found.
    """
    _, deep = _locator_mentions(key)
    import re as _re
    segs = [s for s in _re.split(r"\s+y\s+|\s+e\s+|;\s*|\.\s+",
                               clause) if s.strip()]
    if len(segs) <= 1:
        return ev._expected_op(clause)
    hit = None
    for i, s in enumerate(segs):
        t = ev._norm(s)
        if any(d in t for d in deep):
            hit = i
    if hit is None:
        return ev._expected_op(clause)
    for j in range(hit, -1, -1):
        exp = ev._expected_op(" ".join(segs[j:hit + 1]))
        if exp is not None:
            return exp
    return ev._expected_op(clause)


# ---------------------------------------------------------------------------
# per-relation audit
# ---------------------------------------------------------------------------


def audit_relation(r: dict, docs: dict[str, boe_diario.DiarioDoc],
                   by_url: dict[str, dict], gold_ids: set,
                   gold_palabra: dict, meta_texts: set,
                   chain_ctx: dict, target: str) -> dict:
    claims: dict[str, str] = {}
    evidence: dict = {}
    notes: list[str] = []

    # -- modifier identity -------------------------------------------------
    if r["modifier_boe"] not in gold_ids:
        claims["modifier_declared"] = "CONTRADICTED"
    else:
        claims["modifier_declared"] = "VERIFIED"
        pal = gold_palabra.get(r["modifier_boe"], "")
        expected_kind = "CORRECTION" if "CORRE" in pal.upper() \
            else "MODIFICATION"
        claims["kind_matches_palabra"] = (
            "VERIFIED" if r["kind"] == expected_kind else "CONTRADICTED")

    # -- operation verb ----------------------------------------------------
    raw = (r.get("relation_raw") or "").strip()
    raw_is_meta = bool(raw) and raw in meta_texts
    clause = raw
    if raw_is_meta:
        mdoc = docs.get(r["modifier_boe"])
        clause = find_op_clause(mdoc, r["locator_key"]) \
            if mdoc else None
        notes.append("relation_raw_is_metadata")
        if clause is None:
            claims["operation_verb_consistent"] = "NOT_CHECKABLE"
    if clause is not None:
        exp = _expected_op_for_subject(clause, r["locator_key"])
        if exp is None:
            claims["operation_verb_consistent"] = "NOT_CHECKABLE"
        else:
            claims["operation_verb_consistent"] = (
                "VERIFIED" if exp == r["operation_kind"]
                else "CONTRADICTED")
        evidence["clause_source"] = ("metadata_relation_raw"
                                     if raw_is_meta else "relation_raw")

    # -- target locator ----------------------------------------------------
    tdoc = docs.get(target)
    if tdoc is None:
        claims["target_locator_resolves"] = "NOT_CHECKABLE"
        claims["subject_in_target"] = "NOT_CHECKABLE"
    else:
        claims["target_locator_resolves"] = (
            "VERIFIED" if ev.locator_resolves(tdoc, r["locator_key"])
            else "CONTRADICTED")
        claims["subject_in_target"] = "VERIFIED" if tdoc is not None \
            else "NOT_CHECKABLE"

    # -- bindings ----------------------------------------------------------
    prev = chain_ctx.get(r["locator_key"])
    targetish = {target, r.get("subject_instrument_boe")} - {None}
    for side in ("before", "after"):
        claim = f"{side}_binding"
        rep = r[f"{side}_representation_id"]
        if rep is None:
            claims[claim] = "NO_BINDING_CLAIM"
            continue
        inst = r[f"{side}_instrument"]
        # instrument scope: a before-image cannot come from the document
        # that declares the change unless it is the proven predecessor's
        # after; new content cannot pre-exist in the target document.
        chain_ok = (side == "before" and prev is not None
                    and rep == prev.get("after_id"))
        if side == "before" and inst == r["modifier_boe"] \
                and not chain_ok:
            claims[claim] = "BINDING_FALSE"
            evidence[f"{side}_instrument"] = inst
            notes.append("before_span_in_modifier_doc")
            continue
        if side == "before" and inst not in targetish \
                and inst is not None and not chain_ok:
            claims[claim] = "BINDING_FALSE"
            evidence[f"{side}_instrument"] = inst
            notes.append("before_span_foreign_document")
            continue
        if side == "after" and inst in targetish \
                and r["operation_kind"] != "DELETE":
            claims[claim] = "BINDING_FALSE"
            evidence[f"{side}_instrument"] = inst
            notes.append("after_span_in_target_doc")
            continue
        doc = docs.get(inst)
        loc = r[f"{side}_locator"]
        kind = r[f"{side}_kind"]
        if kind in ("TEXT", "TABLE"):
            if doc is None or not isinstance(loc, dict) \
                    or "node_span" not in loc:
                claims[claim] = "BINDING_NOT_CHECKABLE"
                continue
            try:
                text = ev._span_text(doc, loc["node_span"])
            except Exception:
                claims[claim] = "BINDING_FALSE"
                evidence[f"{side}_span"] = loc.get("node_span")
                continue
            ok = ev._norm(text) == ev._norm(r[f"{side}_text"] or "")
            token = ev._locator_token(r["locator_key"])
            if r["locator_key"].startswith("fichero:"):
                covers = ev._fichero_norm(token) in \
                    ev._fichero_norm(text) or all(
                        t in ev._fichero_tokens(text)
                        for t in ev._fichero_tokens(token))
            else:
                covers = ev._norm(token) in ev._norm(text)
            claims[claim] = "BINDING_CORRECT" if (ok and covers) \
                else "BINDING_FALSE"
            evidence[f"{side}_span"] = loc["node_span"]
            evidence[f"{side}_instrument"] = inst
        elif kind in ("IMAGE", "PDF_PAGE"):
            if doc is None or not isinstance(loc, dict):
                claims[claim] = "BINDING_NOT_CHECKABLE"
                continue
            xml_srcs = {n.img_src for n in doc.nodes if n.img_src}
            pages = loc.get("pages") or []
            ok_srcs = all(p.get("url", "").replace(
                "https://www.boe.es", "") in xml_srcs for p in pages)
            ok_hash = True
            for p in pages:
                e = by_url.get(p.get("url", ""))
                if e is None or "path" not in e:
                    ok_hash = False
                    continue
                if _sha256((ROOT / e["path"]).read_bytes()) \
                        != p.get("blob_sha256"):
                    ok_hash = False
            evidence[f"{side}_pages"] = [p.get("url") for p in pages]
            claims[claim] = ("BINDING_CORRECT" if (ok_srcs and ok_hash)
                             else "BINDING_FALSE")
        else:
            claims[claim] = "BINDING_NOT_CHECKABLE"

    # -- resolution recomputation ------------------------------------------
    lits = json.loads(r["declared_literals"]) \
        if r["declared_literals"] else None
    exp_res = ev._expected_resolution(
        r["operation_kind"], r["before_representation_id"],
        r["after_representation_id"], lits)
    claims["resolution_consistent"] = (
        "VERIFIED" if exp_res == r["resolution"] else "CONTRADICTED")

    # -- chain predecessor --------------------------------------------------
    if prev is not None and prev["after_id"]:
        claims["chain_predecessor"] = (
            "VERIFIED" if r["before_representation_id"]
            == prev["after_id"] else "CONTRADICTED")
        evidence["predecessor_relation_id"] = prev["relation_id"]

    # -- publication date ----------------------------------------------------
    if r["publication_date"]:
        claims["publication_date_matches"] = "VERIFIED"

    bad = [k for k, v in claims.items()
           if v in ("CONTRADICTED", "BINDING_FALSE")]
    truth = "FALSE_FACT" if bad else "PASS"
    rcc = sorted({CLAIM_RCC.get(k, "QUERY_EVALUATION_FAILURE")
                  for k in bad})
    if raw_is_meta and bad == ["operation_verb_consistent"]:
        rcc = ["QUERY_EVALUATION_FAILURE"]
    return {"claims_checked": claims, "truth_verdict": truth,
            "root_cause_class": rcc, "false_binding": any(
                claims.get(s) == "BINDING_FALSE"
                for s in ("before_binding", "after_binding")),
            "evidence_locator": evidence, "notes": notes}


# ---------------------------------------------------------------------------
# per-target evaluation
# ---------------------------------------------------------------------------


def evaluate_target(target: str, cell: str, by_url: dict[str, dict],
                    gold: dict, run_id: str, tmp_root: Path) -> dict:
    data_dir = tmp_root / target
    data_dir.mkdir(parents=True)
    conn = dbm.connect(data_dir / "regdelta.sqlite")
    failures = []
    report = {}
    try:
        report = history.reconstruct(
            conn, data_dir, target, ev.evidence_fetch(by_url))
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        failures.append({"target": target, "stage": "reconstruct",
                         "failure_class": "QUERY_EVALUATION_FAILURE",
                         "symptom": f"{type(exc).__name__}: {exc}",
                         "status": "OPEN"})
        conn.close()
        return {"target": target, "cell": cell, "error": str(exc),
                "failures": failures}

    rows = ev.relation_rows(conn)
    gdecl = gold.get(target, {}).get("declared", [])
    gold_ids = {d["modifier_boe_id"] for d in gdecl}
    gold_palabra = {d["modifier_boe_id"]: d["palabra"] for d in gdecl}
    meta_texts = {d.get("texto", "").strip() for d in gdecl}
    discovered = {m["boe_id"] for m in report.get("modifiers", [])}
    rev = {r[0] for r in conn.execute(
        """SELECT i.boe_id FROM instrument_relations ir
           JOIN instruments i
             ON i.instrument_id = ir.declaring_instrument_id
           WHERE ir.direction='ANTERIOR' AND ir.other_boe_id=?""",
        (target,))}
    rec = [m for m in gold_ids if m in discovered and m in rev]
    for m in sorted(gold_ids - discovered):
        failures.append({"target": target, "modifier": m,
                         "stage": "discovery",
                         "failure_class": "OPERATION_PARSER_FAILURE",
                         "symptom": "gold modifier not discovered",
                         "status": "OPEN"})
    for m in sorted(gold_ids & discovered - rev):
        failures.append({"target": target, "modifier": m,
                         "stage": "discovery",
                         "failure_class": "OPERATION_PARSER_FAILURE",
                         "symptom": "no reverse ANTERIOR link",
                         "status": "OPEN"})
    for fe in report.get("fetch_errors", []):
        failures.append({"target": target, "stage": "acquire",
                         "failure_class": "ACQUISITION_FAILURE",
                         "symptom": str(fe), "status": "OPEN"})

    # -- applicability -----------------------------------------------------
    app_eligible, app_ok = [], []
    for m in report.get("modifiers", []):
        mb = m["boe_id"]
        xml = xml_of(by_url, mb)
        if xml is None:
            failures.append({"target": target, "modifier": mb,
                             "stage": "acquire",
                             "failure_class": "ACQUISITION_FAILURE",
                             "symptom": "modifier XML not in evidence",
                             "status": "OPEN"})
            continue
        if not ev.modifier_declares_applicability(xml):
            continue
        app_eligible.append(mb)
        try:
            applicability.build(conn, data_dir, mb, target)
            conn.commit()
            n = conn.execute(
                """SELECT COUNT(*) FROM applicability_clauses c
                   JOIN instruments i
                     ON i.instrument_id = c.declaring_instrument_id
                   WHERE i.boe_id=?""", (mb,)).fetchone()[0]
            if n > 0:
                app_ok.append(mb)
            else:
                failures.append({"target": target, "modifier": mb,
                                 "stage": "applicability",
                                 "failure_class":
                                 "OPERATION_PARSER_FAILURE",
                                 "symptom": "disposicion sections "
                                            "present but 0 clauses",
                                 "status": "OPEN"})
        except Exception as exc:  # noqa: BLE001
            failures.append({"target": target, "modifier": mb,
                             "stage": "applicability",
                             "failure_class":
                             "QUERY_EVALUATION_FAILURE",
                             "symptom": f"{type(exc).__name__}: {exc}",
                             "status": "OPEN"})

    # -- docs ---------------------------------------------------------------
    docs: dict[str, boe_diario.DiarioDoc] = {}
    for bid in {target} | {r["modifier_boe"] for r in rows} | \
            {r["before_instrument"] for r in rows
             if r["before_instrument"]} | \
            {r["after_instrument"] for r in rows
             if r["after_instrument"]}:
        xml = xml_of(by_url, bid)
        if xml is not None:
            res = boe_diario.parse_diario(xml)
            if res.doc:
                docs[bid] = res.doc

    # -- audit with chain context --------------------------------------------
    by_sub: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda x: (x["publication_date"] or "",
                                         x["relation_id"])):
        by_sub.setdefault(r["locator_key"], []).append(r)
    chain_ctxs: dict[str, dict] = {}
    for key, hops in by_sub.items():
        for i, r in enumerate(hops):
            chain_ctxs[r["relation_id"]] = {
                r["locator_key"]: {
                    "after_id": hops[i - 1]["after_representation_id"],
                    "relation_id": hops[i - 1]["relation_id"]}} \
                if i > 0 else {}

    audit_rows, bindings_rows = [], []
    for r in rows:
        ctx = chain_ctxs.get(r["relation_id"], {})
        a = audit_relation(r, docs, by_url, gold_ids, gold_palabra,
                           meta_texts, ctx, target)
        a.update(run_id=run_id, target=target,
                 relation_id=r["relation_id"],
                 locator_key=r["locator_key"],
                 modifier=r["modifier_boe"],
                 operation_kind=r["operation_kind"],
                 evidence_quote=None)
        audit_rows.append(a)
        for side in ("before", "after"):
            bindings_rows.append({
                "run_id": run_id, "target": target,
                "relation_id": r["relation_id"], "side": side,
                "locator_key": r["locator_key"],
                "representation_id": r[f"{side}_representation_id"],
                "verdict": a["claims_checked"][f"{side}_binding"],
                "locator": r[f"{side}_locator"]})
        if a["truth_verdict"] == "FALSE_FACT":
            failures.append({
                "target": target, "relation_id": r["relation_id"],
                "stage": "audit", "failure_class":
                "QUERY_EVALUATION_FAILURE",
                "symptom": "FALSE_FACT: " + ", ".join(a["root_cause_class"]),
                "status": "OPEN"})

    for an in report.get("anomalies", []):
        failures.append({"target": target, "stage": "reconstruct",
                         "failure_class": "OPERATION_PARSER_FAILURE",
                         "symptom": json.dumps(an, ensure_ascii=False)[:300],
                         "status": "OPEN"})

    qres = ev.run_queries(conn, target, rows)
    for name, res in qres.items():
        if res["status"] != "OK":
            failures.append({"target": target, "stage": "query",
                             "failure_class":
                             "QUERY_EVALUATION_FAILURE",
                             "symptom": f"{name}: {res['error']}",
                             "status": "OPEN"})

    chains = ev.chain_metrics(conn)
    n_rel = len(rows)
    metrics = {
        "declared_modifier_recall": {
            "num": len(rec), "den": len(gold_ids),
            "value": len(rec) / len(gold_ids) if gold_ids else None},
        "operation_parsing_rate": {
            "num": sum(1 for r in rows
                       if r["operation_kind"] in ev.VALID_OPS),
            "den": n_rel,
            "value": (sum(1 for r in rows
                          if r["operation_kind"] in ev.VALID_OPS)
                      / n_rel) if n_rel else None},
        "subject_locator_resolution": {
            "num": sum(1 for a in audit_rows if a["claims_checked"].get(
                "target_locator_resolves") == "VERIFIED"),
            "den": n_rel,
            "value": (sum(1 for a in audit_rows
                          if a["claims_checked"].get(
                              "target_locator_resolves") == "VERIFIED")
                      / n_rel) if n_rel else None},
        "representation_binding": {
            "num": sum(1 for r in rows if ev.required_bound(r)),
            "den": n_rel,
            "value": (sum(1 for r in rows if ev.required_bound(r))
                      / n_rel) if n_rel else None},
        "chain_reconstruction": {
            "num": chains["CHAIN_PROVEN"],
            "den": chains["multi_hop_subjects"],
            "value": (chains["CHAIN_PROVEN"]
                      / chains["multi_hop_subjects"])
            if chains["multi_hop_subjects"] else None,
            **{k: chains[k] for k in
               ("CHAIN_PROVEN", "CHAIN_NOT_PROVABLE", "CHAIN_BROKEN")}},
        "applicability_extraction": {
            "num": len(app_ok), "den": len(app_eligible),
            "value": (len(app_ok) / len(app_eligible))
            if app_eligible else None},
        "query_execution": {
            "num": sum(1 for v in qres.values() if v["status"] == "OK"),
            "den": 5,
            "value": sum(1 for v in qres.values()
                         if v["status"] == "OK") / 5},
        "false_positive_facts":
            sum(1 for a in audit_rows
                if a["truth_verdict"] == "FALSE_FACT"),
        "false_binding_count":
            sum(1 for a in audit_rows if a["false_binding"]),
        "source_limitations":
            sum(1 for f in failures
                if f["failure_class"] == "SOURCE_LIMITATION"),
    }

    inv = {
        "subjects": conn.execute("SELECT COUNT(*) FROM subjects")
        .fetchone()[0],
        "representations":
            conn.execute("SELECT COUNT(*) FROM representations")
            .fetchone()[0],
        "relations": n_rel,
        "resolution": dict(conn.execute(
            "SELECT resolution, COUNT(*) FROM modification_relations"
            " GROUP BY 1").fetchall()),
        "anomalies": report.get("anomaly_count", 0),
    }
    conn.close()
    return {"target": target, "cell": cell,
            "report": {"modifiers": report.get("modifiers", [])},
            "metrics": metrics, "inventory": inv,
            "query_execution": qres,
            "app_eligible": app_eligible,
            "NON_GATE_DIAGNOSTIC": {
                "gold_count": len(gold_ids),
                "discovered_count": len(discovered),
                "reverse_cross_checked_count": len(rec),
                "chains": chains},
            "audit": audit_rows, "bindings": bindings_rows,
            "failures": failures, "relations": rows,
            "chain_ctx": chain_ctxs}


# ---------------------------------------------------------------------------
# 73-case signature reevaluation
# ---------------------------------------------------------------------------


def case_signature(target: str, modifier: str | None, locator: str | None,
                   op: str | None) -> tuple:
    return (target, modifier, locator, op)


def reclassify_corpus(corpus: dict, all_rows: dict[str, list[dict]],
                      audits: dict[str, dict],
                      rc_by_fid: dict[str, dict]) -> dict:
    """Match every historical case by stable signature; classify:
    CORRECTED | ABSTAINED | ALREADY_CORRECT_G0_EVALUATOR_ERROR |
    REPRODUCED_FALSE_FACT."""
    results = []
    counts = Counter()
    for c in corpus["cases"]:
        sig = case_signature(c["target"], c["modifier"],
                             c["locator_key"], c["operation_kind"])
        rows = all_rows.get(c["target"], [])
        matches = [r for r in rows
                   if case_signature(c["target"], r["modifier_boe"],
                                     r["locator_key"],
                                     r["operation_kind"]) == sig]
        rc = rc_by_fid.get(c["failure_id"], {})
        outcome = None
        if not matches:
            outcome = "ABSTAINED"
        else:
            row = next(
                (m for m in matches
                 if m["relation_id"] == c["relation_id"]), None)
            if row is None and len(matches) > 1:
                bad = [m for m in matches
                       if audits[m["relation_id"]]["truth_verdict"]
                       == "FALSE_FACT"]
                if bad:
                    outcome = "REPRODUCED_FALSE_FACT"
                    row = None
                else:
                    row = matches[0]
            elif row is None:
                row = matches[0]
            a = audits.get(row["relation_id"]) if row else None
            if outcome != "REPRODUCED_FALSE_FACT" and (
                    row is None
                    or a["truth_verdict"] == "FALSE_FACT"):
                outcome = "REPRODUCED_FALSE_FACT"
            else:
                emitted = c.get("emitted_representation") or {}
                identical, lost = True, False
                for side in ("before", "after"):
                    old = emitted.get(side)
                    new = row.get(f"{side}_locator")
                    same = (old is None and not new) or (
                        isinstance(old, dict)
                        and isinstance(new, dict)
                        and old.get("instrument")
                        == new.get("instrument")
                        and old.get("node_span")
                        == new.get("node_span"))
                    if old is not None and not new:
                        lost = True
                    identical &= same
                if identical:
                    outcome = "ALREADY_CORRECT_G0_EVALUATOR_ERROR"
                elif lost:
                    outcome = "ABSTAINED"
                else:
                    outcome = "CORRECTED"
        counts[outcome] += 1
        results.append({"signature": {
            "target": c["target"], "modifier": c["modifier"],
            "locator_key": c["locator_key"],
            "operation_kind": c["operation_kind"]},
            "failure_id": c["failure_id"],
            "old_relation_id": c["relation_id"],
            "old_claim_types": c["claim_types"],
            "relation_raw_is_metadata":
            rc.get("relation_raw_is_metadata"),
            "old_root_cause_class": rc.get("root_cause_class"),
            "matched_relations": len(matches),
            "outcome": outcome,
            "new_truth_verdict": audits.get(
                matches[0]["relation_id"], {}).get("truth_verdict")
            if matches else None,
            "new_root_cause_class": audits.get(
                matches[0]["relation_id"], {}).get("root_cause_class")
            if matches else None})
    return {"total": len(results), "counts": dict(counts),
            "cases": results}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def run_split(targets: dict[str, str], by_url: dict[str, dict],
              gold: dict, corpus: dict, rc_by_fid: dict[str, dict],
              run_id: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_audit, all_bindings, all_failures = [], [], []
    all_rows: dict[str, list[dict]] = {}
    audits_by_rid: dict[str, dict] = {}
    per_target = {}
    with tempfile.TemporaryDirectory() as tmp:
        for t in sorted(targets):
            cell = targets[t]
            print(f"evaluating {t} ({cell})")
            res = evaluate_target(t, cell, by_url, gold, run_id,
                                  Path(tmp))
            per_target[t] = {k: v for k, v in res.items()
                             if k not in ("audit", "bindings",
                                          "failures", "relations",
                                          "chain_ctx")}
            all_rows[t] = res.get("relations", [])
            for a in res.get("audit", []):
                audits_by_rid[a["relation_id"]] = a
            all_audit += res.get("audit", [])
            all_bindings += res.get("bindings", [])
            all_failures += res.get("failures", [])

    corpus_result = reclassify_corpus(corpus, all_rows, audits_by_rid,
                                      rc_by_fid)

    def agg(key):
        num = sum(v["metrics"][key]["num"]
                  for v in per_target.values())
        den = sum(v["metrics"][key]["den"]
                  for v in per_target.values())
        return {"num": num, "den": den,
                "value": num / den if den else None}

    metric_keys = ("declared_modifier_recall", "operation_parsing_rate",
                   "subject_locator_resolution",
                   "representation_binding", "chain_reconstruction",
                   "applicability_extraction", "query_execution")
    metrics = {k: agg(k) for k in metric_keys}
    metrics["false_positive_facts"] = sum(
        v["metrics"]["false_positive_facts"]
        for v in per_target.values())
    metrics["false_binding_count"] = sum(
        v["metrics"]["false_binding_count"]
        for v in per_target.values())
    metrics["source_limitations"] = sum(
        v["metrics"]["source_limitations"]
        for v in per_target.values())
    metrics["old_false_fact_reproduction_count"] = \
        corpus_result["counts"].get("REPRODUCED_FALSE_FACT", 0)

    (out_dir / "metrics.json").write_text(json.dumps(
        {"aggregate": metrics, "per_target": {
            t: v["metrics"] for t, v in per_target.items()},
         "corpus_73": corpus_result["counts"]},
        indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "targets.json").write_text(json.dumps(
        per_target, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    with (out_dir / "audit.jsonl").open("w", encoding="utf-8") as fh:
        for a in all_audit:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    with (out_dir / "bindings.jsonl").open("w", encoding="utf-8") as fh:
        for b in all_bindings:
            fh.write(json.dumps(b, ensure_ascii=False) + "\n")
    with (out_dir / "failures.jsonl").open("w", encoding="utf-8") as fh:
        for f in all_failures:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    with (out_dir / "relations.jsonl").open("w", encoding="utf-8") as fh:
        for t, rows in all_rows.items():
            for r in rows:
                fh.write(json.dumps(
                    {**{k: r[k] for k in
                        ("relation_id", "kind", "operation_kind",
                         "locator_key", "modifier_boe",
                         "publication_date", "resolution",
                         "before_representation_id",
                         "after_representation_id")},
                     "target": t}, ensure_ascii=False) + "\n")
    (out_dir / "corpus-73.json").write_text(json.dumps(
        corpus_result, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    lines = ["# G1 DEV evaluation", "", f"run_id: {run_id}", "",
             "| target | relations | FALSE_FACT | FALSE_BINDING |",
             "|---|---|---|---|"]
    for t in sorted(per_target):
        m = per_target[t]["metrics"]
        lines.append(f"| {t} | {per_target[t]['inventory']['relations']}"
                     f" | {m['false_positive_facts']}"
                     f" | {m['false_binding_count']} |")
    lines += ["", "corpus-73:",
              json.dumps(corpus_result["counts"], indent=2)]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")
    return {"metrics": metrics, "corpus": corpus_result,
            "audit_rows": len(all_audit)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-manifest", required=True, type=Path)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--root-cause", type=Path,
                    default=ROOT / "evidence" / "g1" / "root-cause"
                    / "cases.jsonl")
    ap.add_argument("--gold", type=Path,
                    default=G0G / "gold" / "declared_modifiers.json")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--run-id", default="g1")
    args = ap.parse_args()

    man = json.loads(args.dev_manifest.read_text(encoding="utf-8"))
    by_url = {e["url"]: e for e in man["entries"].values()}
    gold_all = json.loads(args.gold.read_text(encoding="utf-8"))
    targets = man["targets"]
    gold = {k: v for k, v in gold_all.items() if k in targets}
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    rc_by_fid = {}
    if args.root_cause.exists():
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

    result = run_split(targets, by_url, gold, corpus, rc_by_fid,
                       args.run_id, args.output)
    finished = datetime.now(timezone.utc).isoformat()

    run = {
        "run_id": args.run_id,
        "runtime_head": head, "src_tree_sha": src_tree,
        "evaluator_sha256": _sha256(Path(__file__).read_bytes()),
        "dev_manifest_sha256": _sha256(
            args.dev_manifest.read_bytes()),
        "corpus_73_sha256": _sha256(args.corpus.read_bytes()),
        "started_at": started, "finished_at": finished,
        "audit_rows": result["audit_rows"],
        "aggregate": result["metrics"],
    }
    (args.output / "run.json").write_text(json.dumps(
        run, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"run_dir": str(args.output),
                      "aggregate": result["metrics"],
                      "corpus_73": result["corpus"]["counts"],
                      "audit_rows": result["audit_rows"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
