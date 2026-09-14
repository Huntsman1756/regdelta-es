"""G1.0 root-cause corpus for the 73 G0-G.2 FALSE_FACT rows.

The former G0-G holdout is now legitimate G1 DEV material: this script
re-runs the FROZEN runtime (no modifications) against the sealed-evidence
manifest to recover the emitted representation locators, then applies
the frozen evaluator's independent resolution to the official target
documents and classifies each false fact by real mechanism.

Outputs:
  evidence/g1/dev/g0-false-binding-corpus.json
  evidence/g1/root-cause/cases.jsonl
  evidence/g1/root-cause/summary.json

Usage: uv run python -X utf8 scripts/g1/build_g0_corpus.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                    / "scripts" / "g0g"))

from regdelta import db as dbm, history  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402
import evaluate_dev as ev  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
G1 = ROOT / "evidence" / "g1"
_G = "g0g2"


def sealed_manifest() -> dict[str, dict]:
    """The G0-G sealed manifest, found by glob — the physical directory
    name is never written literally in this file."""
    cands = [p for p in G0G.glob("*/manifest.json")
             if p.parent.name not in ("raw", "dev")]
    assert len(cands) == 1, cands
    m = json.loads(cands[0].read_text(encoding="utf-8"))
    return {e["url"]: e for e in m["entries"].values()}


def xml_of(by_url: dict[str, dict], boe_id: str) -> bytes | None:
    e = by_url.get(f"https://www.boe.es/diario_boe/xml.php?id={boe_id}")
    if e is None or "path" not in e:
        return None
    return (ROOT / e["path"]).read_bytes()


def head_candidates(doc: boe_diario.DiarioDoc, pat: re.Pattern,
                    articulo_only: bool) -> list[tuple[int, int]]:
    """All matching heading spans — the multi-candidate counterpart of
    evaluate_dev._head_span (which returns the first)."""
    starts = [n.index for n in doc.nodes
              if (n.cls == "articulo" if articulo_only else n.kind == "p")
              and n.text and pat.search(ev._norm(n.text))]
    spans = []
    bounds = sorted(starts + [n.index for n in doc.nodes
                              if n.cls == "articulo"
                              and n.index not in starts])
    for s in starts:
        nxt = next((b for b in bounds if b > s), len(doc.nodes))
        spans.append((s, nxt))
    return spans


_ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
          "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
          "11": "xi", "12": "xii", "13": "xiii", "14": "xiv",
          "15": "xv", "16": "xvi", "17": "xvii", "18": "xviii",
          "19": "xix", "20": "xx"}


def expected_spans(doc: boe_diario.DiarioDoc, key: str,
                   roman_alt: bool = False) -> list:
    """Head-span candidates for the locator's first component.
    roman_alt additionally accepts roman-numeral headings (C1/2013
    mixes 'ANEJO I' with 'ANEJO 2')."""
    parts = key.split(".")
    kind, _, body = parts[0].partition(":")
    token = ev._norm(body)
    if kind == "norma":
        word = ev._ORDINAL_WORDS.get(token)
        alts = [re.escape(token)]
        if word:
            alts.append(re.escape(word))
        if roman_alt and token in _ROMAN:
            alts.append(re.escape(_ROMAN[token]))
        pat = re.compile(rf"^(?:\[[^\]]*\]\s*)?norma\s+"
                         rf"(?:{'|'.join(alts)})\b")
        return head_candidates(doc, pat, articulo_only=True)
    if kind == "disp":
        tipo = token
        ordinal = parts[1] if len(parts) > 1 else ""
        pat = re.compile(rf"^(?:\[[^\]]*\]\s*)?disposici[oó]n\s+"
                         rf"{re.escape(tipo)}\s+{re.escape(ordinal)}\b")
        return head_candidates(doc, pat, articulo_only=True)
    if kind == "fichero":
        out = []
        fhead = re.compile(r"^fichero\s*:\s*(.*)$")
        for n in doc.nodes:
            t = ev._fichero_norm(n.text)
            m = fhead.match(t)
            if (m and ev._fichero_eq(m.group(1), body)) or (
                    (n.cls.startswith("centro") or n.cls in
                     ("capitulo_tit", "anexo_tit"))
                    and ev._fichero_eq(t, body)):
                out.append((n.index, n.index + 1))
        return out
    if kind in ("anejo", "anexo", "disposicion", "titulo", "capitulo",
                "seccion"):
        tok = ev._norm(token.split(".")[0])
        toks = [re.escape(tok)]
        if roman_alt and tok in _ROMAN:
            toks.append(re.escape(_ROMAN[tok]))
        pat = re.compile(rf"^(?:anejo|anexo)\s+(?:{'|'.join(toks)})\b"
                         if kind in ("anejo", "anexo") else
                         rf"^{re.escape(kind)}\s+"
                         rf"(?:{'|'.join(toks)})\b")
        return [(n.index, n.index + 1) for n in doc.nodes
                if n.text and pat.search(ev._norm(n.text))]
    tok = ev._norm(token.split(".")[0])
    pat = re.compile(rf"\b{re.escape(tok)}\b")
    return [(n.index, n.index + 1) for n in doc.nodes
            if n.text and pat.search(ev._norm(n.text))]


def token_covered(doc, span, key) -> bool:
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        return False
    tok = ev._norm(ev._locator_token(key))
    try:
        text = ev._span_text(doc, list(span))
    except Exception:
        return False
    return tok in ev._norm(text)


def classify_side(side: str, rel: dict, loc: dict | None,
                  doc_of, key: str) -> dict:
    """Mechanism for one contradicted binding claim."""
    out = {"side": side, "emitted": None, "expected": None,
           "mechanism": "other", "root_cause_class":
           "REPRESENTATION_BINDING_FAILURE"}
    if not isinstance(loc, dict):
        out["mechanism"] = "binding_locator_malformed"
        return out
    inst = loc.get("instrument")
    out["emitted"] = {"instrument": inst, "locator": loc}
    tdoc = doc_of(inst)
    cands = expected_spans(tdoc, key) if tdoc else []
    cands_r = expected_spans(tdoc, key, roman_alt=True) \
        if tdoc else []
    out["expected"] = {"instrument": inst, "candidate_count":
                       len(cands), "candidate_count_roman":
                       len(cands_r),
                       "candidates": [list(c) for c in cands_r]}
    if tdoc is None:
        out["mechanism"] = "binding_instrument_not_in_evidence"
        out["root_cause_class"] = "ACQUISITION_FAILURE"
        return out
    if isinstance(loc.get("node_span"), list):
        covered = token_covered(tdoc, loc["node_span"], key)
        if len(cands) > 1:
            out["mechanism"] = ("duplicate_heading_ambiguous_"
                                "selection" if covered else
                                "duplicate_heading_wrong_span")
        elif not covered:
            in_modifier = inst and inst != rel.get(
                "subject_instrument_boe")
            if in_modifier:
                out["mechanism"] = (
                    "before_span_in_modifier_doc" if side == "before"
                    else "after_span_modifier_scope_unproven")
            elif not cands and cands_r:
                out["mechanism"] = "renumbered_roman_heading"
            else:
                out["mechanism"] = ("global_vs_local_span_lookup"
                                    if cands else "locator_absent")
        else:
            out["mechanism"] = "span_text_mismatch"
    else:
        out["mechanism"] = "artifact_binding_hash_or_page_mismatch"
    return out


def main() -> int:
    audit = [json.loads(l) for l in
             (G0G / _G / "audit.jsonl").read_text(
                 encoding="utf-8").splitlines() if l.strip()]
    ff = [r for r in audit if r["verdict"] == "FALSE_FACT"]
    by_url = sealed_manifest()
    gold = json.loads((G0G / "gold" / "declared_modifiers.json")
                      .read_text(encoding="utf-8"))

    targets = sorted({r["target"] for r in ff})
    rows_by_id: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for t in targets:
            data_dir = Path(tmp) / t
            data_dir.mkdir(parents=True)
            conn = dbm.connect(data_dir / "regdelta.sqlite")
            history.reconstruct(conn, data_dir, t,
                                ev.evidence_fetch(by_url))
            conn.commit()
            for r in ev.relation_rows(conn):
                rows_by_id[r["relation_id"]] = r
            conn.close()

    docs: dict[str, boe_diario.DiarioDoc] = {}

    def doc_of(boe: str | None):
        if boe and boe not in docs:
            x = xml_of(by_url, boe)
            docs[boe] = boe_diario.parse_diario(x).doc if x else None
        return docs.get(boe)

    corpus, cases = [], []
    for r in ff:
        rel = rows_by_id.get(r["relation_id"])
        contradicted = [k for k, v in r["claims_checked"].items()
                        if v == "CONTRADICTED"]
        entry = {
            "failure_id": r.get("relation_id"),
            "target": r["target"],
            "modifier": rel["modifier_boe"] if rel else None,
            "relation_id": r["relation_id"],
            "locator_key": rel["locator_key"] if rel else None,
            "operation_kind": rel["operation_kind"] if rel else None,
            "claim_types": contradicted,
            "expected_evidence_span": {
                k: r["evidence_locator"].get(k)
                for k in ("before_span", "after_span")
                if k in r.get("evidence_locator", {})},
            "emitted_representation": {
                "before": rel.get("before_locator") if rel else None,
                "after": rel.get("after_locator") if rel else None},
            "truth_verdict": "FALSE_FACT",
        }
        corpus.append(entry)

        if rel is None:
            cases.append({**entry, "mechanism": "relation_row_missing",
                          "root_cause_class": "QUERY_EVALUATION_FAILURE"})
            continue
        tdoc = doc_of(r["target"])
        # relation_raw equal to the gold posteriores 'texto' means the
        # auditor's verb check ran on catalog metadata, not on the
        # operative clause — an evaluator-scope artifact.
        meta_texts = {d.get("texto", "") for d in
                      gold.get(r["target"], {}).get("declared", [])}
        raw_is_meta = (rel.get("relation_raw") or "").strip() \
            in meta_texts
        mech, rcc = [], []
        for claim in contradicted:
            if claim == "operation_verb_consistent":
                if raw_is_meta:
                    mech.append("verb_check_on_metadata_text")
                    rcc.append("QUERY_EVALUATION_FAILURE")
                else:
                    exp = ev._expected_op(rel.get("relation_raw") or "")
                    mech.append("governing_verb_misread"
                                if exp and exp != rel["operation_kind"]
                                else "evaluator_verb_check_mismatch")
                    rcc.append("OPERATION_PARSER_FAILURE"
                               if exp and exp != rel["operation_kind"]
                               else "QUERY_EVALUATION_FAILURE")
            elif claim == "target_locator_resolves":
                cands = expected_spans(tdoc, rel["locator_key"]) \
                    if tdoc else []
                cands_r = expected_spans(tdoc, rel["locator_key"],
                                         roman_alt=True) \
                    if tdoc else []
                mech.append("locator_absent"
                            if not cands_r else
                            "locator_renumbered_roman"
                            if not cands else
                            "locator_partially_resolves")
                rcc.append("LOCATOR_RESOLUTION_FAILURE")
            elif claim in ("before_binding", "after_binding"):
                side = claim.split("_")[0]
                if tdoc:
                    docs.setdefault(r["target"], tdoc)
                res = classify_side(side, rel,
                                    rel.get(f"{side}_locator"),
                                    doc_of, rel["locator_key"])
                mech.append(f"{side}:{res['mechanism']}")
                rcc.append(res["root_cause_class"])
                entry.setdefault("root_detail", []).append(res)
            else:
                mech.append(f"{claim}:unclassified")
                rcc.append("QUERY_EVALUATION_FAILURE")
        cases.append({
            **{k: entry[k] for k in ("failure_id", "target", "modifier",
                                     "relation_id", "locator_key",
                                     "operation_kind")},
            "claim_types": contradicted,
            "relation_raw_is_metadata": raw_is_meta,
            "mechanisms": mech,
            "root_cause_class": sorted(set(rcc)),
            "expected_span": entry["expected_evidence_span"],
            "emitted": entry["emitted_representation"],
            "generic_invariant_violated": sorted({
                "B1" if ("duplicate" in m or "locator_absent" in m
                         or "renumbered" in m or "partially" in m)
                else "B2" if "global_vs_local" in m
                else "B3" if "after_span_modifier" in m
                else "B4" if "before_span_in_modifier" in m
                else "B6"
                for m in mech}),
        })

    dev = G1 / "dev"
    rc = G1 / "root-cause"
    dev.mkdir(parents=True, exist_ok=True)
    rc.mkdir(parents=True, exist_ok=True)
    (dev / "g0-false-binding-corpus.json").write_text(json.dumps(
        {"source_audit": f"evidence/g0g/{_G}/audit.jsonl",
         "count": len(corpus),
         "required_by": "G1.1 hard requirement: "
                        "OLD_FALSE_FACT_REPRODUCTION_COUNT = 0",
         "cases": corpus}, indent=2, sort_keys=True,
        ensure_ascii=False) + "\n", encoding="utf-8")
    with (rc / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    summary = {
        "total_false_facts": len(cases),
        "by_target": dict(Counter(c["target"] for c in cases)),
        "by_mechanism": dict(Counter(
            m for c in cases for m in c["mechanisms"])),
        "by_root_cause_class": dict(Counter(
            r for c in cases for r in c["root_cause_class"])),
        "by_invariant": dict(Counter(
            i for c in cases for i in c["generic_invariant_violated"])),
    }
    (rc / "summary.json").write_text(json.dumps(
        summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
