"""G2.0 candidate pool + subject-ownership-risk selection.

Universe: the frozen G0-G.0 BdE index candidates (evidence/g0g/
candidates.json) minus evidence/g2/semantic-seen-set.json. Risk
classification is mechanical, from official relation metadata only —
no operation parsing:

  CORRIGENDUM_CHAIN (§27A)
      T has a posterior corrigendum M (palabra CORRIGE/CORRECCIÓN) and
      M's own <anteriores> prove M officially corrects ANOTHER
      instrument (CORRIGE-anterior referencia != T) while T appears in
      M's relations (downstream registration).

  MULTI_TARGET_MODIFIER (§27B)
      T has a non-correction posterior modifier M (MODIFICA/AÑADE/
      SUPRIME/SUSTITUYE) whose own <anteriores> identify >= 2 distinct
      modified instruments.

Posterior-instrument diario XMLs are read metadata-only (<anteriores>,
<metadatos>): bodies are never parsed, so fetched instruments remain
CAPTURED_STRUCTURALLY, not semantically seen. Sources are tried in
order: evidence/g0g/raw -> evidence/g2/discovery-raw -> live fetch
(stored under discovery-raw so reruns are byte-stable).

Ranking per group (§28): risk_event_count DESC,
declared_modifier_count DESC, sha256("regdelta-g2-v1"|boe_id) ASC;
top 2. A candidate qualifying for both groups is assigned to the one
with the higher risk_event_count; tie -> hash decides. Fewer than 2
eligible in any group -> STOP G2.0 (§28); no relaxation after
identities are known.

Usage: uv run python -X utf8 scripts/g2/discover_g2.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
G2 = ROOT / "evidence" / "g2"
DISC_RAW = G2 / "discovery-raw"

SEED = "regdelta-g2-v1"
DIARIO_XML = "https://www.boe.es/diario_boe/xml.php?id={}"

CORRECTION_RE = re.compile(r"CORRIG|CORRECCI", re.IGNORECASE)
MODIFYING_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE", re.IGNORECASE)


def _anteriores(root: ET.Element) -> list[dict]:
    out = []
    for a in root.findall(".//anteriores/anterior"):
        out.append({"referencia": a.get("referencia"),
                    "palabra": (a.findtext("palabra") or "").strip(),
                    "texto": (a.findtext("texto") or "").strip()})
    return out


def _instrument_xml(boe_id: str) -> tuple[bytes | None, str]:
    """Bytes + provenance. Repo first; discovery-raw cache second;
    live fetch last (persisted so the run is reproducible)."""
    repo = G0G / "raw" / f"boe_diario_xml__{boe_id}.xml"
    if repo.exists():
        return repo.read_bytes(), f"evidence/g0g/raw/{repo.name}"
    cache = DISC_RAW / f"boe_diario_xml__{boe_id}.xml"
    if cache.exists():
        return cache.read_bytes(), f"evidence/g2/discovery-raw/{cache.name}"
    try:
        data = urllib.request.urlopen(
            DIARIO_XML.format(boe_id), timeout=30).read()
    except Exception:
        return None, "fetch-failed"
    DISC_RAW.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data, f"evidence/g2/discovery-raw/{cache.name} (fetched)"


def main() -> int:
    seen = set(json.loads((G2 / "semantic-seen-set.json")
                          .read_text(encoding="utf-8"))["boe_ids"])
    cand = json.loads((G0G / "candidates.json")
                      .read_text(encoding="utf-8"))

    pool: list[dict] = []
    for e in cand["entries"]:
        bid = e["boe_id"]
        if bid in seen:
            continue
        xml_path = G0G / "raw" / f"boe_diario_xml__{bid}.xml"
        if not xml_path.exists():
            continue
        posts = [{"referencia": p.get("referencia"),
                  "palabra": (p.findtext("palabra") or "").strip(),
                  "texto": (p.findtext("texto") or "").strip()}
                 for p in ET.parse(xml_path).getroot()
                 .findall(".//posteriores/posterior")]

        chain_events, multi_events = [], []
        for po in posts:
            ref = po["referencia"]
            if not ref:
                continue
            if CORRECTION_RE.search(po["palabra"]):
                mdata, src = _instrument_xml(ref)
                if mdata is None:
                    chain_events.append({"corrigendum": ref,
                                         "verdict": "UNEVALUABLE",
                                         "source": src})
                    continue
                ants = _anteriores(ET.fromstring(mdata))
                corrects = sorted({a["referencia"] for a in ants
                                   if CORRECTION_RE.search(a["palabra"])
                                   and a["referencia"]})
                others = [r for r in corrects if r != bid]
                downstream = any(a["referencia"] == bid for a in ants)
                chain_events.append({
                    "corrigendum": ref, "corrects": corrects,
                    "corrects_other_instrument": bool(others),
                    "target_in_corrigendum_relations": downstream,
                    "qualifies": bool(others) and downstream,
                    "source": src,
                    "source_sha256":
                        hashlib.sha256(mdata).hexdigest()})
            elif MODIFYING_RE.search(po["palabra"]):
                mdata, src = _instrument_xml(ref)
                if mdata is None:
                    multi_events.append({"modifier": ref,
                                         "verdict": "UNEVALUABLE",
                                         "source": src})
                    continue
                ants = _anteriores(ET.fromstring(mdata))
                mods = sorted({a["referencia"] for a in ants
                               if MODIFYING_RE.search(a["palabra"])
                               and a["referencia"]})
                multi_events.append({
                    "modifier": ref, "modified_instruments": mods,
                    "qualifies": len(mods) >= 2,
                    "source": src,
                    "source_sha256":
                        hashlib.sha256(mdata).hexdigest()})

        pool.append({
            "boe_id": bid, "circular": e["circular"],
            "boe_pub_date": e["boe_pub_date"],
            "g0_status": e["status"],
            "declared_modifier_count":
                sum(1 for p in posts if p["referencia"]),
            "corrigendum_chain_events": chain_events,
            "multi_target_events": multi_events,
            "chain_risk_count":
                sum(1 for x in chain_events if x.get("qualifies")),
            "multi_risk_count":
                sum(1 for x in multi_events if x.get("qualifies")),
            "g2_rank_key": hashlib.sha256(
                f"{SEED}|{bid}".encode()).hexdigest(),
        })

    # dual membership -> group with higher risk count; tie -> hash
    groups: dict[str, list[dict]] = {
        "CORRIGENDUM_CHAIN": [], "MULTI_TARGET_MODIFIER": []}
    for p in pool:
        c, m = p["chain_risk_count"], p["multi_risk_count"]
        if c == 0 and m == 0:
            continue
        if c > 0 and (c > m or
                      (c == m and int(p["g2_rank_key"], 16) % 2 == 0)):
            groups["CORRIGENDUM_CHAIN"].append(p)
        elif m > 0:
            groups["MULTI_TARGET_MODIFIER"].append(p)

    for g in groups.values():
        g.sort(key=lambda p: (
            -(p["chain_risk_count"] + p["multi_risk_count"]),
            -p["declared_modifier_count"], p["g2_rank_key"]))

    selection = {
        "seed": SEED,
        "rule": ("per group: risk_event_count DESC, "
                 "declared_modifier_count DESC, sha256(seed|boe_id) "
                 "ASC; top 2 per group; any group < 2 -> STOP G2.0"),
        "status": "STOP",
        "groups": {},
    }
    for name, g in groups.items():
        entry = {"eligible": [p["boe_id"] for p in g],
                 "eligible_count": len(g)}
        if len(g) < 2:
            entry["STOP"] = "fewer than 2 eligible candidates"
        selection["groups"][name] = entry

    (G2 / "candidates.json").write_text(json.dumps(
        {"index_source": "evidence/g0g/raw/"
                         "bde_circulares_indice_cronologico.html",
         "frozen_index_sha256": hashlib.sha256(
             (G0G / "raw" / "bde_circulares_indice_cronologico.html")
             .read_bytes()).hexdigest(),
         "universe": "72 G0-G.0 candidates minus 58 seen = %d unseen"
                     % len(pool),
         "pool": pool}, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n", encoding="utf-8")
    (G2 / "selection.json").write_text(json.dumps(
        selection, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(json.dumps({k: v["eligible"]
                      for k, v in selection["groups"].items()},
                     indent=2))
    if any("STOP" in v for v in selection["groups"].values()):
        print("STOP G2.0: a required risk group has < 2 eligible "
              "fresh targets (§28). No holdout is formed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
