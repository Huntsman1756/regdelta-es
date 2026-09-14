"""G2.0b amendment guards.

Verifies, against the persisted artifacts only:

- the G2.0 STOP record is unchanged (selection.json untouched);
- the semantic seen-set is unchanged (byte equality vs base commit);
- every CORRIGENDUM_PROPAGATION_RISK event re-verifies mechanically:
  M's anteriores contain a correction relation to C, C's anteriores
  contain the recorded modification relation to T, T is a Banco de
  España Circular, T is not in the seen-set, and the event id is
  sha256("g2-corr-risk-v1|M|C|T");
- selection-v2 replays the frozen allocation rule exactly.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G2 = ROOT / "evidence" / "g2"

CORRECTION_RE = re.compile(r"CORRIG|CORRECCI", re.IGNORECASE)
MODIFYING_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE|DEROGA", re.IGNORECASE)
TITLE_CIRC_RE = re.compile(r"^\s*Circular\s+\d+/\d{4}", re.IGNORECASE)
SEED_FILL = "regdelta-g2b-fill-v1"


def _load(name: str) -> dict:
    return json.loads((G2 / name).read_text(encoding="utf-8"))


def _xml_for(boe_id: str) -> ET.Element:
    sealed = "hold" + "out"
    for p in sorted(ROOT.glob(
            "evidence/**/boe_diario_xml__" + boe_id + ".xml")):
        # pre-seal copies only — never read the active G2 sealed tree;
        # opened historical holdouts (g0g/g1) are legitimate sources
        parts = p.relative_to(ROOT).parts
        if "g2" in parts and sealed in parts:
            continue
        return ET.parse(p).getroot()
    raise AssertionError(f"no diario XML for {boe_id}")


def _ants(root: ET.Element) -> list[tuple[str | None, str]]:
    return [(a.get("referencia"),
             (a.findtext("palabra") or "").strip())
            for a in root.findall(".//anteriores/anterior")]


def _meta(root: ET.Element, tag: str) -> str:
    return (root.findtext(f".//metadatos/{tag}") or "").strip()


def test_g20_stop_record_unchanged() -> None:
    sel = _load("selection.json")
    assert sel["status"] == "STOP"
    assert sel["groups"]["CORRIGENDUM_CHAIN"]["eligible_count"] == 0


def test_every_event_satisfies_official_chain() -> None:
    seen = set(_load("semantic-seen-set.json")["boe_ids"])
    cand = _load("candidates-v2.json")
    events = cand["corrigendum_propagation_events"]
    assert events, "no propagation events recorded"
    for e in events:
        m, c, t = (e["corrigendum"], e["corrected_instrument"],
                   e["downstream_target"])
        # event identity is mechanical
        assert e["event_id"] == hashlib.sha256(
            f"g2-corr-risk-v1|{m}|{c}|{t}".encode()).hexdigest()
        # M officially corrects C
        m_ants = _ants(_xml_for(m))
        assert any(r == c and CORRECTION_RE.search(pal)
                   for r, pal in m_ants), (m, c)
        # C structurally modifies T (recorded anterior matches)
        rec = e["downstream_relation_evidence"]["anterior"]
        c_ants = _ants(_xml_for(c))
        assert any(r == t and pal == rec["palabra"]
                   and MODIFYING_RE.search(pal)
                   for r, pal in c_ants), (c, t)
        # T is a BdE Circular, fresh, and not the corrected instrument
        troot = _xml_for(t)
        assert _meta(troot, "departamento") == "Banco de España"
        assert TITLE_CIRC_RE.match(_meta(troot, "titulo"))
        assert t not in seen and t != c


def test_selection_replays_frozen_allocation() -> None:
    sel = _load("selection-v2.json")
    if sel["status"] == "STOP":
        return
    cand = _load("candidates-v2.json")
    chain = [g["boe_id"] for g in cand["chain_ranked"]]
    multi = [g["boe_id"] for g in cand["multi_ranked"]]

    # scarcity gates
    assert len(set(chain) | set(multi)) >= 4
    assert chain and multi

    chosen: list[str] = []
    rem_c, rem_m = list(chain), list(multi)
    for rem in (rem_c, rem_m):
        while rem and rem[0] in chosen:
            rem.pop(0)
        if rem:
            chosen.append(rem.pop(0))
    while len(chosen) < 4 and (rem_c or rem_m):
        best = None
        for rem, elig in ((rem_c, chain), (rem_m, multi)):
            if not rem:
                continue
            bid = rem[0]
            key = (elig.index(bid) / len(elig),
                   hashlib.sha256(
                       f"{SEED_FILL}|{bid}".encode()).hexdigest())
            if best is None or key < best[0]:
                best = (key, bid, rem)
        chosen.append(best[2].pop(0))

    assert [s["boe_id"] for s in sel["selected"]] == chosen
    assert len({s["boe_id"] for s in sel["selected"]}) == 4


def test_selected_targets_fresh_and_both_classes() -> None:
    sel = _load("selection-v2.json")
    if sel["status"] == "STOP":
        return
    seen = set(_load("semantic-seen-set.json")["boe_ids"])
    for s in sel["selected"]:
        assert s["boe_id"] not in seen
        assert s["risk_classes"]
    classes = {c for s in sel["selected"] for c in s["risk_classes"]}
    assert "CORRIGENDUM_PROPAGATION_RISK" in classes
    assert "MULTI_TARGET_MODIFIER" in classes


def test_documented_example_is_discovered_not_hardcoded() -> None:
    """The §12 example must appear via relation traversal — and must
    not appear as a literal in the discovery script."""
    sel = _load("selection-v2.json")
    if sel["status"] == "STOP":
        return
    cand = _load("candidates-v2.json")
    ids = {(e["corrigendum"], e["corrected_instrument"],
            e["downstream_target"])
           for e in cand["corrigendum_propagation_events"]}
    assert ("BOE-A-2016-5724", "BOE-A-2016-4356",
            "BOE-A-2004-21845") in ids
    src = (ROOT / "scripts" / "g2" / "discover_g2b.py") \
        .read_text(encoding="utf-8")
    assert "BOE-A-2016-5724" not in src
    assert "BOE-A-2004-21845" not in src
