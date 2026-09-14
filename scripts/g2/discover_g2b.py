"""G2.0b event-centric ownership-risk discovery + selection-v2.

Amends the G2.0 discovery traversal only — CORRIGENDUM_CHAIN becomes
CORRIGENDUM_PROPAGATION_RISK, discovered event-centrically:

    corrigendum M -> officially corrects instrument C
    C -> modification relation -> downstream target T
    T = Banco de España Circular, never semantically seen, T != C

MULTI_TARGET_MODIFIER is unchanged from G2.0 and recomputed
mechanically for reproducibility.

All derivation is official relation metadata (posteriores /
anteriores / metadatos rango, departamento, url_eli). No operation or
subject parsing: CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN.

Corrigendum universe (PREREG §4): correction-relation ids referenced
by every diario XML already captured under evidence/**/raw, plus
correction relations found in the posteriores of instruments fetched
during traversal (bounded BFS over the official relation graph).
Fetched bytes persist under evidence/g2/discovery-v2/raw with a
manifest so reruns are byte-stable.

Selection (amendment §8-§10): exactly 4 fresh unique targets,
>= 1 per risk class; scarcity stops before selection:

    unique eligible < 4        -> STOP
    chain eligible == 0        -> STOP
    multi eligible == 0        -> STOP

Allocation: top-1 of each class first; remaining slots go to the best
normalized within-group rank (rank / group eligible count), ties via
sha256("regdelta-g2b-fill-v1"|boe_id). A target eligible in both
classes materializes once with risk_classes=[...].

Usage: uv run python -X utf8 scripts/g2/discover_g2b.py
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
DISC = G2 / "discovery-v2"
DISC_RAW = DISC / "raw"
DISC_RAW_V1 = G2 / "discovery-raw"

SEED_CHAIN = "regdelta-g2b-v1"
SEED_MULTI = "regdelta-g2-v1"       # G2.0 ranking seed, unchanged
SEED_FILL = "regdelta-g2b-fill-v1"
EVENT_SEED = "g2-corr-risk-v1"

DIARIO_XML = "https://www.boe.es/diario_boe/xml.php?id={}"

CORRECTION_RE = re.compile(r"CORRIG|CORRECCI", re.IGNORECASE)
# §5B structural modification effects (incl. DEROGA per amendment)
MODIFYING_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE|DEROGA", re.IGNORECASE)
# multi group keeps the G2.0 palabra set (no DEROGA) for reproducibility
MODIFYING_G20_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE", re.IGNORECASE)
CIRC_RE = re.compile(r"Circular\s+(\d+/\d{4})", re.IGNORECASE)
ELI_CORR_RE = re.compile(
    r"/eli/es/cir/(\d{4})/(\d{2})/(\d{2})/(\d+)/corrigendum/")
TITLE_CIRC_RE = re.compile(r"^\s*Circular\s+(\d+/\d{4})", re.IGNORECASE)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- store

class Store:
    """boe_id -> (bytes, provenance) with repo-first resolution."""

    def __init__(self) -> None:
        self.local: dict[str, Path] = {}
        sealed = "hold" + "out"
        for p in sorted(
                ROOT.glob("evidence/**/raw/boe_diario_xml__*.xml")):
            # seed universe = instruments captured before this gate;
            # exclude bytes produced by G2.0b itself (discovery-v2 and
            # the sealed dir) so reruns are deterministic
            parts = p.relative_to(ROOT).parts
            if "discovery-v2" in parts or \
                    ("g2" in parts and sealed in parts):
                continue
            bid = p.stem.split("__", 1)[-1]
            self.local.setdefault(bid, p)
        self.manifest: dict[str, dict] = {}
        mp = DISC / "manifest.json"
        if mp.exists():
            self.manifest.update(
                json.loads(mp.read_text(encoding="utf-8"))["entries"])

    def get(self, boe_id: str) -> tuple[bytes | None, str]:
        if boe_id in self.local:
            p = self.local[boe_id]
            return p.read_bytes(), str(p.relative_to(ROOT))
        cache = DISC_RAW / f"boe_diario_xml__{boe_id}.xml"
        if cache.exists():
            return cache.read_bytes(), str(cache.relative_to(ROOT))
        cache2 = DISC_RAW_V1 / f"boe_diario_xml__{boe_id}.xml"
        if cache2.exists():
            return cache2.read_bytes(), str(cache2.relative_to(ROOT))
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
        DISC.mkdir(parents=True, exist_ok=True)
        (DISC / "manifest.json").write_text(json.dumps(
            {"entries": self.manifest}, indent=2, sort_keys=True,
            ensure_ascii=False) + "\n", encoding="utf-8")


def anteriores(root: ET.Element) -> list[dict]:
    return [{"referencia": a.get("referencia"),
             "palabra": (a.findtext("palabra") or "").strip(),
             "texto": (a.findtext("texto") or "").strip()}
            for a in root.findall(".//anteriores/anterior")]


def posteriores(root: ET.Element) -> list[dict]:
    return [{"referencia": p.get("referencia"),
             "palabra": (p.findtext("palabra") or "").strip(),
             "texto": (p.findtext("texto") or "").strip()}
            for p in root.findall(".//posteriores/posterior")]


def meta(root: ET.Element, tag: str) -> str:
    return (root.findtext(f".//metadatos/{tag}") or "").strip()


# ------------------------------------------------- corrected instrument

def resolve_corrected(m_root: ET.Element) -> tuple[str | None, dict]:
    """§5 Step A: ELI corrects -> unique official correction relation.
    Returns (boe_id | None, evidence)."""
    corr_ants = [a for a in anteriores(m_root)
                 if CORRECTION_RE.search(a["palabra"]) and a["referencia"]]
    eli = meta(m_root, "url_eli")
    ev = {"method": None, "eli": eli,
          "correction_anteriores": corr_ants}
    m = ELI_CORR_RE.search(eli)
    if m:
        # corrigendum of circular N/YYYY -> among correction anteriores,
        # the one whose texto names that circular is C
        circ = f"{m.group(4)}/{m.group(1)}"
        hits = [a for a in corr_ants
                if circ in CIRC_RE.findall(a["texto"])]
        ev.update(method="ELI_CORRECTS", corrected_circular=circ,
                  eli_matched_anteriores=len(hits))
        if len(hits) == 1:
            return hits[0]["referencia"], ev
        if len(corr_ants) == 1:
            return corr_ants[0]["referencia"], ev
        ev["method"] = "AMBIGUOUS"
        return None, ev
    if len(corr_ants) == 1:
        ev["method"] = "UNIQUE_CORRECTION_RELATION"
        return corr_ants[0]["referencia"], ev
    ev["method"] = "AMBIGUOUS" if corr_ants else "NO_CORRECTION_RELATION"
    return None, ev


def is_bde_circular(root: ET.Element) -> bool:
    return meta(root, "departamento") == "Banco de España" and \
        bool(TITLE_CIRC_RE.match(meta(root, "titulo")))


# ---------------------------------------------------------------- main

def main() -> int:
    seen = set(json.loads((G2 / "semantic-seen-set.json")
                          .read_text(encoding="utf-8"))["boe_ids"])
    cand = json.loads((G0G / "candidates.json")
                      .read_text(encoding="utf-8"))
    store = Store()

    # -- corrigendum universe: correction posteriores of every captured
    #    diario XML + of instruments fetched during traversal
    queue: list[str] = []
    queued: set[str] = set()
    for bid, path in sorted(store.local.items()):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for p in posteriores(root):
            if CORRECTION_RE.search(p["palabra"]) and p["referencia"] \
                    and p["referencia"] not in queued:
                queued.add(p["referencia"])
                queue.append(p["referencia"])

    events: list[dict] = []
    ambiguous: list[dict] = []
    t_meta: dict[str, dict] = {}

    while queue:
        m = queue.pop(0)
        mdata, msrc = store.get(m)
        if mdata is None:
            continue
        mroot = ET.fromstring(mdata)
        is_corr = CORRECTION_RE.search(meta(mroot, "rango") or "") or \
            any(CORRECTION_RE.search(a["palabra"])
                for a in anteriores(mroot))
        if not is_corr:
            continue
        # relation-graph expansion: corrigenda declared in M's own
        # posteriores are reached instruments too
        for p in posteriores(mroot):
            if CORRECTION_RE.search(p["palabra"]) and p["referencia"] \
                    and p["referencia"] not in queued:
                queued.add(p["referencia"])
                queue.append(p["referencia"])
        c, cev = resolve_corrected(mroot)
        if c is None:
            ambiguous.append({"corrigendum": m, "evidence": cev})
            continue
        cdata, csrc = store.get(c)
        if cdata is None:
            continue
        croot = ET.fromstring(cdata)
        for p in posteriores(croot):   # corrigenda of C are reached too
            if CORRECTION_RE.search(p["palabra"]) and p["referencia"] \
                    and p["referencia"] not in queued:
                queued.add(p["referencia"])
                queue.append(p["referencia"])
        mod_ants = [a for a in anteriores(croot)
                    if MODIFYING_RE.search(a["palabra"])
                    and a["referencia"]]
        for a in mod_ants:
            t = a["referencia"]
            if t == c or t in seen:
                continue
            if t not in t_meta:
                tdata, tsrc = store.get(t)
                if tdata is None:
                    t_meta[t] = {"bde_circular": False,
                                 "verdict": "XML_UNAVAILABLE",
                                 "source": tsrc}
                    continue
                troot = ET.fromstring(tdata)
                t_meta[t] = {
                    "bde_circular": is_bde_circular(troot),
                    "titulo": meta(troot, "titulo"),
                    "posteriores_count":
                        sum(1 for p2 in posteriores(troot)
                            if p2["referencia"]),
                    "source": tsrc,
                    "source_sha256": sha256(tdata)}
            if not t_meta[t]["bde_circular"]:
                continue
            events.append({
                "event_id": sha256(
                    f"{EVENT_SEED}|{m}|{c}|{t}".encode()),
                "corrigendum": m,
                "corrected_instrument": c,
                "downstream_target": t,
                "correction_relation_evidence": {
                    "method": cev["method"],
                    "corrigendum_eli": cev["eli"],
                    "correction_anteriores": cev["correction_anteriores"],
                    "corrigendum_source": msrc,
                    "corrigendum_sha256": sha256(mdata)},
                "downstream_relation_evidence": {
                    "anterior": a,
                    "corrected_source": csrc,
                    "corrected_sha256": sha256(cdata)},
                "target_evidence": t_meta[t],
            })

    # dedupe events (same M may resolve repeatedly is impossible; same
    # (M,C,T) can repeat only via duplicate queue entries — kept
    # deterministic anyway)
    uniq = {e["event_id"]: e for e in events}
    events = sorted(uniq.values(), key=lambda e: e["event_id"])

    # -- chain-group per-target aggregates
    chain: dict[str, dict] = {}
    for e in events:
        t = e["downstream_target"]
        g = chain.setdefault(t, {
            "boe_id": t, "events": [],
            "corrigendum_risk_event_count": 0,
            "distinct_corrected_instrument_count": 0,
            "declared_modifier_count":
                t_meta[t].get("posteriores_count", 0),
            "g2b_rank_key": sha256(
                f"{SEED_CHAIN}|{t}".encode())})
        g["events"].append(e["event_id"])
    for g in chain.values():
        g["corrigendum_risk_event_count"] = len(g["events"])
        g["distinct_corrected_instrument_count"] = len({
            e["corrected_instrument"] for e in events
            if e["downstream_target"] == g["boe_id"]})
    chain_ranked = sorted(chain.values(), key=lambda g: (
        -g["corrigendum_risk_event_count"],
        -g["distinct_corrected_instrument_count"],
        -g["declared_modifier_count"], g["g2b_rank_key"]))

    # -- multi group: identical mechanics to G2.0 over unseen candidates
    multi: list[dict] = []
    for e in cand["entries"]:
        bid = e["boe_id"]
        if bid in seen:
            continue
        x = G0G / "raw" / f"boe_diario_xml__{bid}.xml"
        if not x.exists():
            continue
        posts = posteriores(ET.parse(x).getroot())
        hits = []
        for po in posts:
            ref = po["referencia"]
            if not ref or CORRECTION_RE.search(po["palabra"]) or \
                    not MODIFYING_G20_RE.search(po["palabra"]):
                continue
            mdata, msrc = store.get(ref)
            if mdata is None:
                continue
            mods = sorted({a["referencia"] for a in anteriores(
                ET.fromstring(mdata))
                if MODIFYING_G20_RE.search(a["palabra"])
                and a["referencia"]})
            if len(mods) >= 2:
                hits.append({"modifier": ref,
                             "modified_instruments": mods,
                             "source": msrc})
        if hits:
            multi.append({
                "boe_id": bid, "circular": e["circular"],
                "risk_event_count": len(hits), "events": hits,
                "declared_modifier_count":
                    sum(1 for p in posts if p["referencia"]),
                "g2_rank_key": sha256(
                    f"{SEED_MULTI}|{bid}".encode())})
    multi_ranked = sorted(multi, key=lambda g: (
        -g["risk_event_count"], -g["declared_modifier_count"],
        g["g2_rank_key"]))

    # -- scarcity gate (frozen before identities considered)
    chain_eligible = [g["boe_id"] for g in chain_ranked]
    multi_eligible = [g["boe_id"] for g in multi_ranked]
    unique_eligible = set(chain_eligible) | set(multi_eligible)

    selection: dict = {
        "amendment": "G2.0b",
        "seeds": {"chain": SEED_CHAIN, "multi": SEED_MULTI,
                  "fill": SEED_FILL, "event": EVENT_SEED},
        "rule": ("exactly 4 unique fresh targets; >=1 per risk class; "
                 "top-1 per class then best normalized within-group "
                 "rank (rank/eligible_count), tie -> fill seed hash"),
        "status": "PASS", "selected": [], "groups": {
            "CORRIGENDUM_PROPAGATION_RISK": {
                "eligible": chain_eligible,
                "eligible_count": len(chain_eligible)},
            "MULTI_TARGET_MODIFIER": {
                "eligible": multi_eligible,
                "eligible_count": len(multi_eligible)}}}
    stop = None
    if len(unique_eligible) < 4:
        stop = "fewer than 4 unique eligible fresh targets"
    elif not chain_eligible:
        stop = "CORRIGENDUM_PROPAGATION_RISK eligible = 0"
    elif not multi_eligible:
        stop = "MULTI_TARGET_MODIFIER eligible = 0"
    if stop:
        selection["status"] = "STOP"
        selection["stop_reason"] = stop
    else:
        # deterministic allocation: top-1 per class, then fill by
        # normalized within-group rank
        chosen: list[str] = []
        rem_c = list(chain_eligible)
        rem_m = list(multi_eligible)

        def take(bid: str, cls: str) -> None:
            if bid in chosen:
                return
            chosen.append(bid)
            classes = [cls]
            if bid in chain_eligible and bid in multi_eligible:
                classes = sorted({"CORRIGENDUM_PROPAGATION_RISK",
                                  "MULTI_TARGET_MODIFIER"})
            selection["selected"].append(
                {"boe_id": bid, "risk_classes": classes})

        # top-1 per class (first still-unchosen candidate)
        for rem, cls in ((rem_c, "CORRIGENDUM_PROPAGATION_RISK"),
                         (rem_m, "MULTI_TARGET_MODIFIER")):
            while rem and rem[0] in chosen:
                rem.pop(0)
            if rem:
                take(rem.pop(0), cls)
        while len(chosen) < 4 and (rem_c or rem_m):
            best = None
            for grp, rem, elig in (
                    ("CORRIGENDUM_PROPAGATION_RISK", rem_c,
                     chain_eligible),
                    ("MULTI_TARGET_MODIFIER", rem_m, multi_eligible)):
                if not rem:
                    continue
                bid = rem[0]
                key = (elig.index(bid) / len(elig),
                       sha256(f"{SEED_FILL}|{bid}".encode()))
                if best is None or key < best[0]:
                    best = (key, bid, grp, rem)
            _, bid, grp, rem = best
            rem.pop(0)
            take(bid, grp)
        if len(chosen) < 4:
            selection["status"] = "STOP"
            selection["stop_reason"] = \
                "allocation could not reach 4 unique targets"

    DISC.mkdir(parents=True, exist_ok=True)
    store.flush()
    (G2 / "candidates-v2.json").write_text(json.dumps({
        "amendment": "G2.0b",
        "corrigendum_universe_size": len(queued),
        "corrigendum_propagation_events": events,
        "ambiguous_corrigenda": ambiguous,
        "chain_ranked": chain_ranked,
        "multi_ranked": multi_ranked,
    }, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (G2 / "selection-v2.json").write_text(json.dumps(
        selection, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(f"corrigenda processed: {len(queued)}  events: {len(events)}")
    print("chain eligible:", chain_eligible)
    print("multi eligible:", multi_eligible)
    print("selected:", [s["boe_id"] for s in selection["selected"]])
    print("status:", selection["status"],
          selection.get("stop_reason", ""))
    return 0 if selection["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
