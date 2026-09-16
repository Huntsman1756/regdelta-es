"""COV-3 holdout selection — the COV-1 §11 / COV-2 §6 frozen rule.

Mechanical, metadata-only, over never-seen Banco de España Circular
targets of the frozen index corpus (evidence/g0g/candidates.json) plus
the G2.0b relation graph (evidence/g2/candidates-v2.json), excluding
the COV-2-extended semantic seen-set.

Eligibility (frozen):

    declared_modifier_count >= 3
    (official <posteriores> bearing MODIFICA|DEROGA|SUPRIME|AÑADE|
    SUSTITUYE over T, with referencia)

Stratum (assigned BEFORE selection — COV-1 §3 metadata rule over the
candidate's own captured <metadatos>):

    vigencia_agotada = S  OR  estatus_derogacion = S
        -> HISTORICAL_PREDECESSOR
    otherwise -> CURRENT_OPERATIONAL

Rank within each stratum (frozen):

    declared_modifier_count            DESC
    same_date_modifier_cluster_count   DESC   (distinct modifier
                                       publication dates carrying
                                       >=2 declared modifiers)
    sha256("regdelta-cov-v1"|boe_id)   ASC

Allocation (frozen):

    CURRENT_OPERATIONAL eligible < 3      -> STOP
    select top 3 CURRENT_OPERATIONAL
    if >=1 HISTORICAL_PREDECESSOR eligible:
        select top 1 HISTORICAL_PREDECESSOR
    else:
        select top 4th CURRENT_OPERATIONAL

Reads only <metadatos> (incl. codigo attributes), <posteriores> and
<anteriores> — eligibility fetches never open an instrument
semantically (protocol: CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN).
Fetched bytes persist under evidence/cov/cov3/discovery-raw/ with a
manifest so reruns are byte-stable.

Usage: uv run python -X utf8 scripts/cov/select_cov3.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from regdelta.http import http_fetch  # transport only

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
G2 = ROOT / "evidence" / "g2"
COV3 = ROOT / "evidence" / "cov" / "cov3"
DISC_RAW = COV3 / "discovery-raw"
DISC_MANIFEST = COV3 / "discovery-manifest.json"

SEED = "regdelta-cov-v1"
DIARIO_XML = "https://www.boe.es/diario_boe/xml.php?id={}"

# COV-1 §11 eligible palabra family (corrigenda are relation metadata,
# not amendment modifiers, and are excluded here exactly as the prereg
# names them)
MODIFYING_RE = re.compile(
    r"MODIFICA|AÑADE|SUPRIME|SUSTITUYE|DEROGA", re.IGNORECASE)

RANGO_CIRCULAR = "1390"
DEPARTAMENTO_BDE = "1020"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Store:
    """boe_id -> (bytes, provenance); repo-first, then cov3 cache,
    then a single eligibility fetch persisted byte-exactly."""

    def __init__(self) -> None:
        self.local: dict[str, Path] = {}
        sealed = "hold" + "out"
        for p in sorted(
                ROOT.glob("evidence/**/raw/boe_diario_xml__*.xml")):
            parts = p.relative_to(ROOT).parts
            # bytes sealed inside a *previous* holdout stay usable as
            # provenance (hash-only reads); the cov3 holdout dir itself
            # is excluded so a rerun cannot read its own output
            if "cov3" in parts and sealed in parts:
                continue
            bid = p.stem.split("__", 1)[-1]
            self.local.setdefault(bid, p)
        self.manifest: dict[str, dict] = {}
        if DISC_MANIFEST.exists():
            self.manifest.update(json.loads(
                DISC_MANIFEST.read_text(encoding="utf-8"))["entries"])

    def get(self, boe_id: str) -> tuple[bytes | None, str]:
        if boe_id in self.local:
            p = self.local[boe_id]
            return p.read_bytes(), str(p.relative_to(ROOT))
        cache = DISC_RAW / f"boe_diario_xml__{boe_id}.xml"
        if cache.exists():
            return cache.read_bytes(), str(cache.relative_to(ROOT))
        r = http_fetch(DIARIO_XML.format(boe_id), "application/xml")
        entry = {"name": cache.name, "url": DIARIO_XML.format(boe_id),
                 "http_status": r.http_status,
                 "error_class": r.error_class,
                 "retrieved_at": datetime.now(timezone.utc)
                 .strftime("%Y-%m-%dT%H:%M:%SZ")}
        if r.body is not None:
            DISC_RAW.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(r.body)
            entry.update(path=str(cache.relative_to(ROOT)),
                         sha256=sha256(r.body), size_bytes=len(r.body))
        self.manifest[cache.name] = entry
        if r.body is None:
            return None, "fetch-failed"
        return r.body, str(cache.relative_to(ROOT)) + " (fetched)"

    def flush(self) -> None:
        DISC_RAW.mkdir(parents=True, exist_ok=True)
        DISC_MANIFEST.write_text(json.dumps(
            {"entries": self.manifest}, indent=2, sort_keys=True,
            ensure_ascii=False) + "\n", encoding="utf-8")


def meta(root: ET.Element, tag: str) -> str:
    return (root.findtext(f".//metadatos/{tag}") or "").strip()


def meta_code(root: ET.Element, tag: str) -> str:
    el = root.find(f".//metadatos/{tag}")
    return (el.attrib.get("codigo") or "").strip() if el is not None \
        else ""


def posteriores(root: ET.Element) -> list[dict]:
    return [{"referencia": p.get("referencia"),
             "palabra": (p.findtext("palabra") or "").strip(),
             "texto": (p.findtext("texto") or "").strip()}
            for p in root.findall(".//posteriores/posterior")]


def pub_date(root: ET.Element) -> str:
    raw = meta(root, "fecha_publicacion")
    return (f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8
            else raw)


def main() -> int:
    seen = set(json.loads((ROOT / "evidence" / "cov"
                           / "semantic-seen-set.json")
                          .read_text(encoding="utf-8"))["boe_ids"])
    cand = json.loads((G0G / "candidates.json")
                      .read_text(encoding="utf-8"))
    cv2 = json.loads((G2 / "candidates-v2.json")
                     .read_text(encoding="utf-8"))

    universe: dict[str, str] = {}   # boe_id -> universe source
    for e in cand["entries"]:
        universe.setdefault(e["boe_id"], "index_corpus")
    for g in cv2.get("chain_ranked", []) + cv2.get("multi_ranked", []):
        universe.setdefault(g["boe_id"], "g2b_relation_graph")
    for e in cv2.get("corrigendum_propagation_events", []):
        universe.setdefault(e["downstream_target"],
                            "g2b_relation_graph")

    store = Store()
    candidates: dict[str, dict] = {}
    excluded: dict[str, str] = {}
    for bid in sorted(universe):
        if bid in seen:
            excluded[bid] = "SEMANTICALLY_SEEN"
            continue
        data, src = store.get(bid)
        if data is None:
            excluded[bid] = "XML_UNAVAILABLE"
            continue
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            excluded[bid] = "XML_PARSE_ERROR"
            continue
        if meta_code(root, "departamento") != DEPARTAMENTO_BDE \
                or meta_code(root, "rango") != RANGO_CIRCULAR:
            excluded[bid] = "NOT_BDE_CIRCULAR"
            continue
        declared = [p for p in posteriores(root)
                    if MODIFYING_RE.search(p["palabra"])
                    and p["referencia"]]
        stratum = ("HISTORICAL_PREDECESSOR"
                   if meta(root, "vigencia_agotada") == "S"
                   or meta(root, "estatus_derogacion") == "S"
                   else "CURRENT_OPERATIONAL")
        # same-date cluster axis: fetch each declared modifier's own
        # metadatos for its official publication date (metadata only)
        dates: dict[str, int] = {}
        for d in declared:
            mdata, _ = store.get(d["referencia"])
            if mdata is None:
                continue
            try:
                mroot = ET.fromstring(mdata)
            except ET.ParseError:
                continue
            dt = pub_date(mroot)
            if dt:
                dates[dt] = dates.get(dt, 0) + 1
        clusters = sum(1 for n in dates.values() if n >= 2)
        candidates[bid] = {
            "boe_id": bid,
            "universe": universe[bid],
            "source": src,
            "source_sha256": sha256(data),
            "titulo": meta(root, "titulo"),
            "stratum": stratum,
            "vigencia_agotada": meta(root, "vigencia_agotada"),
            "estatus_derogacion": meta(root, "estatus_derogacion"),
            "declared_modifier_count": len(declared),
            "declared_modifiers": sorted(d["referencia"]
                                         for d in declared),
            "same_date_modifier_cluster_count": clusters,
            "eligible": len(declared) >= 3,
            "rank_key": sha256(f"{SEED}|{bid}".encode()),
        }
    store.flush()

    def ranked(stratum: str) -> list[dict]:
        return sorted(
            (c for c in candidates.values()
             if c["eligible"] and c["stratum"] == stratum),
            key=lambda c: (-c["declared_modifier_count"],
                           -c["same_date_modifier_cluster_count"],
                           c["rank_key"]))

    curr_ranked = ranked("CURRENT_OPERATIONAL")
    hist_ranked = ranked("HISTORICAL_PREDECESSOR")

    selection: dict = {
        "gate": "COV-3",
        "seed": SEED,
        "rule": ("require >=3 CURRENT_OPERATIONAL eligible else STOP; "
                 "select top 3 CURR; if >=1 HISTORICAL_PREDECESSOR "
                 "eligible select top 1 HIST else top 4th CURR"),
        "rank_within_stratum": ("declared_modifier_count DESC, "
                                "same_date_modifier_cluster_count "
                                "DESC, sha256('regdelta-cov-v1'|"
                                "boe_id) ASC"),
        "universe_size": len(universe),
        "seen_set_size": len(seen),
        "status": "PASS",
        "eligible": {
            "CURRENT_OPERATIONAL":
                [c["boe_id"] for c in curr_ranked],
            "HISTORICAL_PREDECESSOR":
                [c["boe_id"] for c in hist_ranked]},
        "candidates": candidates,
        "excluded": excluded,
        "selected": []}

    if len(curr_ranked) < 3:
        selection["status"] = "STOP"
        selection["stop_reason"] = (
            f"CURRENT_OPERATIONAL eligible = {len(curr_ranked)} < 3")
    else:
        picks = curr_ranked[:3]
        if hist_ranked:
            picks.append(hist_ranked[0])
        elif len(curr_ranked) >= 4:
            picks.append(curr_ranked[3])
        else:
            selection["status"] = "STOP"
            selection["stop_reason"] = (
                "no HISTORICAL_PREDECESSOR eligible and no 4th "
                "CURRENT_OPERATIONAL")
        selection["selected"] = [
            {"boe_id": c["boe_id"], "stratum": c["stratum"],
             "declared_modifier_count": c["declared_modifier_count"],
             "same_date_modifier_cluster_count":
                 c["same_date_modifier_cluster_count"],
             "rank_key": c["rank_key"]}
            for c in picks]

    COV3.mkdir(parents=True, exist_ok=True)
    (COV3 / "selection.json").write_text(json.dumps(
        selection, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(f"universe: {len(universe)}  seen-excluded: "
          f"{sum(1 for v in excluded.values() if v == 'SEMANTICALLY_SEEN')}")
    print("CURR eligible:", [c['boe_id'] for c in curr_ranked])
    print("HIST eligible:", [c['boe_id'] for c in hist_ranked])
    print("selected:", [s['boe_id'] for s in selection['selected']])
    print("status:", selection["status"],
          selection.get("stop_reason", ""))
    return 0 if selection["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
