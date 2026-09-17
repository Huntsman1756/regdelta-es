"""CORE-GAP step 2 — census of the six PROFILE_LIMIT families.

Enumerates every frozen CNMV gap family over all *allowed seen*
corpora: the CNMV DEV split (``evidence/port-cnmv/split-v2/dev``) and
every ``boe_diario_xml__*.xml`` capture under ``evidence/`` whose path
does not contain ``holdout`` (holdout isolation is mechanical, not
semantic: the path filter is applied to the file list before any byte
is opened).

Families (PORT-CNMV-1 adjudicated PROFILE_LIMIT register):

  F1  ``seccion:`` subjects — ontology kind exists, composition cannot
      materialize paths that contain a section level.
  F2  dispositions without ordinal identity.
  F3  two-level nesting ``apartado X) -> número N`` (and the inverse
      word order ``número N del apartado X``).
  F4  image-only annex representation/evidence.
  F5  unnumbered continuation items.
  F6  redesignation/renumbering old→new continuity.

Output: evidence/core-gap/census.json (+ census.md summary).

Usage:
    PYTHONPATH=src python -X utf8 scripts/core-gap/census.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "port-cnmv"))

from regdelta.sources import boe_diario  # noqa: E402
import regdelta.profiles.cnmv as cnmv  # noqa: E402

DEV_RAW = ROOT / "evidence" / "port-cnmv" / "split-v2" / "dev" / "raw"
OUT_DIR = ROOT / "evidence" / "core-gap"

# CNMV targets + modifiers all live as boe_diario_xml__<BOE>.xml
CNMV_TARGETS = ["BOE-A-1994-28725", "BOE-A-2008-16091",
                "BOE-A-2008-20895", "BOE-A-2010-13162"]

# ---------------------------------------------------------------------------
# detectors — mechanical patterns only, no semantic judgment
# ---------------------------------------------------------------------------

_RE_SECCION_HEAD = re.compile(
    r"^\s*SECCI[OÓ]N\s+\S", re.IGNORECASE)
_RE_SECCION_REF = re.compile(
    r"\bsecci[oó]n\s+(?:primera|segunda|tercera|cuarta|quinta|sexta|"
    r"s[eé]ptima|octava|novena|d[eé]cima|\d+|[ivxlcdm]+)\b",
    re.IGNORECASE)
_RE_DISP_HEAD = re.compile(
    r"^\s*(?:disposici[oó]n|norma)\s+"
    r"(adicional|transitoria|final|derogatoria)\b(.*)$", re.IGNORECASE)
_RE_ORDINAL = re.compile(
    r"primera|primero|segunda|segundo|tercera|tercero|cuarta|cuarto|"
    r"quinta|quinto|sexta|sexto|s[eé]ptim|octav|noven|d[eé]cim|"
    r"und[eé]cim|duod[eé]cim|[uú]nic[oa]|bis|ter|qu[aá]ter|\d",
    re.IGNORECASE)
# F3: subject references spanning two levels — "apartado X ... número N"
# or "número N ... apartado X" inside one clause
_RE_TWO_LEVEL = re.compile(
    r"(apartado\s+\S+[^.]{0,80}?\bn[uú]mero\s+\d+|"
    r"n[uú]mero\s+\d+[^.]{0,80}?\bapartado\s+\S+|"
    r"n[uú]mero\s+\d+[^.]{0,80}?\bde\s+(?:la|el)\s+norma\s+\d+|"
    r"letra\s+\(?[a-z]\)?[^.]{0,60}?\bn[uú]mero\s+\d+)",
    re.IGNORECASE)
_RE_CONT_ITEM = re.compile(r"^\s*[–\-•]\s*\S")
_RE_PASA_SER = re.compile(
    r"\bpasa\w*\s+a\s+(?:ser|denominarse)\b", re.IGNORECASE)
_RE_IMG = re.compile(r"<img\b", re.IGNORECASE)


def _doc_stats(path: Path) -> dict:
    """Parse one captured diario XML; count family hits."""
    try:
        doc = boe_diario.parse_diario(path.read_bytes()).doc
    except Exception as e:  # noqa: BLE001 — census must not die on one file
        return {"parse_error": f"{type(e).__name__}: {e}"}
    if doc is None:
        return {"parse_error": "no doc"}
    st: dict = defaultdict(list)
    st["nodes"] = len(doc.nodes)
    st["img_nodes"] = len(doc.images())
    for n in doc.nodes:
        t = re.sub(r"\s+", " ", (n.text or "").strip())
        if not t:
            continue
        if _RE_SECCION_HEAD.match(t):
            st["seccion_heads"].append(t[:80])
        m = _RE_DISP_HEAD.match(t)
        if m and not _RE_ORDINAL.search(m.group(2) or ""):
            st["disp_unnumbered_heads"].append(t[:80])
        for m in _RE_SECCION_REF.finditer(t):
            st["seccion_refs"].append(m.group(0))
        if _RE_TWO_LEVEL.search(t):
            st["two_level_refs"].append(t[:160])
        if _RE_CONT_ITEM.match(n.text or ""):
            st["cont_items"].append(t[:80])
        for m in _RE_PASA_SER.finditer(t):
            st["pasa_ser"].append(t[max(0, m.start() - 60):m.end() + 60])
        if cnmv.REDESIGNATION_RE.search(t):
            st["redesignation_structural"].append(t[:160])
    return dict(st)


def _is_holdout(p: Path) -> bool:
    return "holdout" in str(p).lower().replace("\\", "/")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- corpus enumeration -------------------------------------------------
    cnmv_files = sorted(DEV_RAW.glob("boe_diario_xml__*.xml"))
    cnmv_ids = {f.stem.split("__")[1] for f in cnmv_files}
    all_xml = sorted(ROOT.glob("evidence/**/boe_diario_xml__*.xml"))
    seen_files = [f for f in all_xml if not _is_holdout(f)]
    bde_files = [f for f in seen_files
                 if "port-cnmv" not in str(f).replace("\\", "/")]

    print(f"cnmv dev xml: {len(cnmv_files)} "
          f"(targets={len(set(CNMV_TARGETS) & cnmv_ids)})")
    print(f"boe xml seen (non-holdout, non-cnmv): {len(bde_files)}")
    print(f"holdout xml skipped: {len(all_xml) - len(seen_files)}")

    fam_keys = ("seccion_heads", "seccion_refs", "disp_unnumbered_heads",
                "two_level_refs", "cont_items", "pasa_ser",
                "redesignation_structural", "img_nodes")

    def scan(files):
        agg: dict = {"docs": 0, "parse_errors": 0,
                     "families": defaultdict(int),
                     "per_doc": {}}
        for f in files:
            st = _doc_stats(f)
            if "parse_error" in st:
                agg["parse_errors"] += 1
                continue
            agg["docs"] += 1
            boe = f.stem.split("__")[1]
            hits = {k: (len(st[k]) if isinstance(st.get(k), list)
                        else st.get(k, 0))
                    for k in fam_keys}
            if any(hits.values()):
                agg["per_doc"][boe] = {
                    k: v for k, v in hits.items() if v}
                if boe in CNMV_TARGETS:
                    agg["per_doc"][boe]["_target"] = True
            for k, v in hits.items():
                agg["families"][k] += v
        agg["families"] = dict(agg["families"])
        return agg

    cnmv = scan(cnmv_files)
    bde = scan(bde_files)

    # EXP-B1 already adjudicated the BdE redesignation census
    expb1 = json.loads(
        (ROOT / "evidence/cov/exp-b1/cases.json").read_text("utf-8"))

    census = {
        "step": "CORE-GAP census",
        "corpora": {
            "cnmv_dev": {"xml_docs": len(cnmv_files),
                         "targets": sorted(CNMV_TARGETS),
                         "root": "evidence/port-cnmv/split-v2/dev/raw"},
            "bde_seen": {"xml_docs": len(bde_files),
                         "root": "evidence/**/raw (non-holdout)"},
            "holdout_xml_excluded":
                len(all_xml) - len(seen_files)},
        "cnmv_dev": cnmv,
        "bde_seen": bde,
        "bde_redesignation_prior": {
            "source": "evidence/cov/exp-b1/cases.json",
            "clauses": expb1["case_count"],
            "classes": expb1["class_counts"]},
    }
    (OUT_DIR / "census.json").write_text(
        json.dumps(census, ensure_ascii=False, indent=2,
                   default=str), encoding="utf-8")

    # markdown summary
    lines = ["# CORE-GAP census\n",
             "| family | CNMV dev | BdE seen |",
             "|---|---|---|"]
    labels = {
        "seccion_heads": "F1 seccion heads",
        "seccion_refs": "F1 seccion refs",
        "disp_unnumbered_heads": "F2 unnumbered disposición",
        "two_level_refs": "F3 apartado↔número refs",
        "img_nodes": "F4 image nodes",
        "cont_items": "F5 continuation items",
        "redesignation_structural": "F6 structural redesignations",
        "pasa_ser": "F6 pasa a ser/denominarse (all)",
    }
    for k in fam_keys:
        c = cnmv["families"].get(k, 0)
        b = bde["families"].get(k, 0)
        if k == "pasa_ser":
            b = f"{b} raw / {expb1['case_count']} clauses (EXP-B1)"
        lines.append(f"| {labels[k]} | {c} | {b} |")
    (OUT_DIR / "census.md").write_text("\n".join(lines) + "\n",
                                     encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT_DIR/'census.json'} + census.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
