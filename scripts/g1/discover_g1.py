"""G1.0 candidate pool + amendment-dense holdout selection.

Fully offline: reuses the FROZEN G0-G.0 BdE index snapshot and the
candidate diario XMLs captured under evidence/g0g/raw. Nothing is
re-fetched; no RegDelta pipeline code runs here.

Pool:     G0 ELIGIBLE candidates - evidence/g1/semantic-seen-set.json
Filter:   >= 2 explicit MODIFYING instruments in <posteriores>
          (corrections without modification operations do not count)
Groups:   TEXT / VISUAL (from the frozen G0 classification)
Rank:     1. declared_modifying_instrument_count DESC
          2. explicit anejo/anexo references in <posteriores> DESC
          3. sha256("regdelta-g1-v1|" + boe_id) ASC
Select:   top 2 per group -> SEALED_HOLDOUT (4 fresh unseen targets)
          fewer than 2 eligible in a group => STOP.

Usage: uv run python -X utf8 scripts/g1/discover_g1.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
G1 = ROOT / "evidence" / "g1"

SEED = "regdelta-g1-v1"

# a posteriores entry counts as an explicit modifying instrument iff its
# palabra declares amendment operations; pure error corrections do not
MODIFYING_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE|DEROGA", re.IGNORECASE)
CORRECTION_RE = re.compile(r"CORRIGE|CORRECCI", re.IGNORECASE)
ANEJO_RE = re.compile(r"anej[oa]s?\b|anexos?\b", re.IGNORECASE)


def posteriores(diario_xml: bytes) -> list[dict]:
    root = ET.fromstring(diario_xml)
    post = root.find(".//posteriores")
    out = []
    if post is None:
        return out
    for p in post.findall("posterior"):
        out.append({"referencia": p.get("referencia"),
                    "palabra": (p.findtext("palabra") or "").strip(),
                    "texto": (p.findtext("texto") or "").strip()})
    return out


def main() -> int:
    seen = set(json.loads((G1 / "semantic-seen-set.json")
                          .read_text(encoding="utf-8"))["boe_ids"])
    cand = json.loads((G0G / "candidates.json")
                      .read_text(encoding="utf-8"))
    eligible = [e for e in cand["entries"] if e["status"] == "ELIGIBLE"]

    pool = []
    for e in eligible:
        bid = e["boe_id"]
        if bid in seen:
            continue
        xml_path = G0G / "raw" / f"boe_diario_xml__{bid}.xml"
        if not xml_path.exists():
            continue
        posts = posteriores(xml_path.read_bytes())
        modifying = [p for p in posts
                     if MODIFYING_RE.search(p["palabra"])
                     and not (CORRECTION_RE.search(p["palabra"])
                              and not MODIFYING_RE.search(p["palabra"]))]
        anejo_refs = sum(len(ANEJO_RE.findall(p["palabra"] + " "
                                              + p["texto"]))
                         for p in modifying)
        pool.append({
            "boe_id": bid,
            "circular": e["circular"],
            "boe_pub_date": e["boe_pub_date"],
            "group": "VISUAL" if e["visual"] else "TEXT",
            "consolidated": e["consolidated"],  # descriptive only
            "declared_modifying_instrument_count": len(modifying),
            "modifying_instruments": sorted(
                p["referencia"] for p in modifying if p["referencia"]),
            "explicit_anejo_refs_in_posteriores": anejo_refs,
            "g1_rank_key": hashlib.sha256(
                f"{SEED}|{bid}".encode()).hexdigest(),
        })

    pool = [p for p in pool
            if p["declared_modifying_instrument_count"] >= 2]

    groups: dict[str, list[dict]] = {}
    for p in pool:
        groups.setdefault(p["group"], []).append(p)
    for g in groups.values():
        g.sort(key=lambda p: (
            -p["declared_modifying_instrument_count"],
            -p["explicit_anejo_refs_in_posteriores"],
            p["g1_rank_key"]))

    selection = {
        "seed": SEED,
        "rule": ("per group: modifying_count DESC, anejo_refs DESC, "
                 "sha256(seed|boe_id) ASC; top 2 -> SEALED_HOLDOUT"),
        "dev": ("G1 DEV = the 12 already-seen G0-G targets "
                "(8 GENERALIZATION_DEV + 4 former SEALED_HOLDOUT); "
                "no fresh instrument may enter DEV"),
        "groups": {},
    }
    ok = True
    for name in ("TEXT", "VISUAL"):
        g = groups.get(name, [])
        entry = {"ranked": [p["boe_id"] for p in g],
                 "SEALED_HOLDOUT": [p["boe_id"] for p in g[:2]]}
        if len(g) < 2:
            entry["STOP"] = "fewer than 2 eligible candidates"
            ok = False
        selection["groups"][name] = entry

    (G1 / "candidates.json").write_text(json.dumps(
        {"index_source": "evidence/g0g/raw/"
                         "bde_circulares_indice_cronologico.html",
         "frozen_index_sha256": hashlib.sha256(
             (G0G / "raw" / "bde_circulares_indice_cronologico.html")
             .read_bytes()).hexdigest(),
         "pool": pool}, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    (G1 / "selection.json").write_text(json.dumps(
        selection, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    print(json.dumps({k: v.get("SEALED_HOLDOUT", "STOP")
                      for k, v in selection["groups"].items()},
                     indent=2))
    print(f"pool size: {len(pool)} "
          f"(TEXT {len(groups.get('TEXT', []))}, "
          f"VISUAL {len(groups.get('VISUAL', []))})")
    if not ok:
        print("STOP: group underpopulated")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
