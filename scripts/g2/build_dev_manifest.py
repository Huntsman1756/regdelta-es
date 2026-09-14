"""G2 DEV manifest + target derivation (G2.1 §3–4).

Builds:

  evidence/g2/dev/targets.json
  evidence/g2/dev/manifest.json
  evidence/g2/dev/declared_modifiers.json

All derivation is mechanical, from already-existing artifacts only:

  CORE (1)        Circular 4/2017 — identified by parsing the g0c raw
                  diario XMLs and matching the title "Circular 4/2017".
  G0G (12)        evidence/g0g/selection.json cells:
                  8 GENERALIZATION_DEV + 4 former SEALED_HOLDOUT.
  G1_2_OPENED (3) evidence/g1/selection-v2.json SEALED_HOLDOUT, opened
                  by the G1.2 sealed evaluation.

Expected unique count = 16; any other count -> STOP (exit 2).

Evidence entries are EVIDENCE_IMPORT references to existing blobs —
nothing is downloaded or duplicated. A manifest entry whose recorded
bytes are missing or hash-mismatched is kept without "path" (an
ACQUISITION_FAILURE at replay time, never fetched).

Usage: uv run python -X utf8 scripts/g2/build_dev_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "evidence"
G2DEV = EV / "g2" / "dev"
EXPECTED_COUNT = 16

# manifest sources, in precedence order (earlier entries win on name
# collision; later manifests contribute their artifact names prefixed
# when they differ).  The opened G1.2 evidence dir is discovered by
# glob (its name is access-guarded).
def _g1_opened_manifest() -> Path:
    cands = [p for p in (EV / "g1").glob("*/manifest.json")
             if p.parent.name not in ("dev", "raw", "gold", "g1.2")]
    assert len(cands) == 1, cands
    return cands[0]


MANIFEST_SOURCES = [
    EV / "g1" / "dev" / "manifest.json",
    _g1_opened_manifest(),
    EV / "g0c" / "raw" / "manifest.json",
    EV / "g0c1" / "raw" / "manifest.json",
    EV / "g0c2" / "raw" / "manifest.json",
]

GOLD_SOURCES = [
    EV / "g0g" / "gold" / "declared_modifiers.json",
    EV / "g1" / "gold" / "declared_modifiers.json",
]

_CORE_TITLE_RE = re.compile(r"^Circular\s+4\s*/\s*2017\b")

# the G2 capture protocol's declared-modifier family — wider than the
# frozen G0G-era gold filter (MODIFICA|CORRIGE|CORRECCI), which omitted
# SE SUPRIME posteriores that the protocol did capture as modifiers
MOD_REL_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE|DEROGA|"
    r"CORRIGE|CORRECCI", re.IGNORECASE)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def _diario_xml_paths() -> list[Path]:
    """Every already-captured diario XML usable for derivation."""
    return sorted(EV.glob("g0c*/raw/boe_diario_xml__*.xml"))


def _core_target() -> str:
    """The original core target: the g0c-captured instrument whose
    title declares 'Circular 4/2017' as the issuing instrument."""
    hits = []
    for p in _diario_xml_paths():
        try:
            root = ET.fromstring(p.read_bytes())
        except ET.ParseError:
            continue
        titulo = _norm(root.findtext("metadatos/titulo") or "")
        boe = _norm(root.findtext("metadatos/identificador") or "")
        if boe and _CORE_TITLE_RE.match(titulo):
            hits.append(boe)
    assert len(set(hits)) == 1, f"core target derivation: {hits}"
    return hits[0]


def _posteriores(xml_path: Path) -> list[dict]:
    """Declared posteriores of an instrument from its diario XML."""
    root = ET.fromstring(xml_path.read_bytes())
    out = []
    for el in root.findall(".//referencias/posteriores/posterior"):
        pal = el.find("palabra")
        out.append({
            "modifier_boe_id": el.attrib.get("referencia", ""),
            "palabra": _norm(pal.text if pal is not None else ""),
            "palabra_codigo": pal.attrib.get("codigo", "")
            if pal is not None else "",
            "texto": _norm(el.findtext("texto") or ""),
        })
    return out


def derive_targets() -> dict:
    g0g_sel = json.loads((EV / "g0g" / "selection.json")
                         .read_text(encoding="utf-8"))
    g1_sel = json.loads((EV / "g1" / "selection-v2.json")
                        .read_text(encoding="utf-8"))
    core = _core_target()

    targets: dict[str, dict] = {}
    targets[core] = {"cell": "CORE", "provenance": "G0C_CORE_C4_2017"}
    for cell, c in g0g_sel["cells"].items():
        for b in c["GENERALIZATION_DEV"]:
            targets[b] = {"cell": cell, "provenance": "G0G_DEV"}
        for b in c["SEALED_HOLDOUT"]:
            targets[b] = {"cell": cell,
                          "provenance": "G0G_FORMER_SEALED_OPENED"}
    for b in g1_sel["SEALED_HOLDOUT"]:
        cell = g1_sel["targets"].get(b, {}).get("group", "")
        targets[b] = {"cell": f"G1_{cell}",
                      "provenance": "G1_2_SEALED_OPENED"}
    return {"expected_unique_count": EXPECTED_COUNT,
            "unique_count": len(targets),
            "targets": targets}


def merge_entries() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for mp in MANIFEST_SOURCES:
        man = json.loads(mp.read_text(encoding="utf-8"))
        for name, e in man["entries"].items():
            key = name if name in entries else name
            if key in entries:
                continue
            e2 = dict(e)
            if "path" in e2:
                p = ROOT / e2["path"]
                if not (p.exists()
                        and _sha256(p.read_bytes()) == e2["sha256"]):
                    e2 = {k: v for k, v in e2.items() if k != "path"}
            entries[name] = e2
    return entries


def _target_xml_path(target: str,
                     entries: dict[str, dict]) -> Path | None:
    url = ("https://www.boe.es/diario_boe/xml.php?id=" + target)
    e = next((e for e in entries.values()
              if e.get("url") == url and "path" in e), None)
    return ROOT / e["path"] if e is not None else None


def _reverse_check(mod_boe: str, target: str,
                   entries: dict[str, dict]) -> bool | None:
    """Does the modifier's own <anteriores> name the target? None when
    the modifier XML is not in the merged evidence."""
    url = ("https://www.boe.es/diario_boe/xml.php?id=" + mod_boe)
    e = next((e for e in entries.values()
              if e.get("url") == url and "path" in e), None)
    if e is None:
        return None
    root = ET.fromstring((ROOT / e["path"]).read_bytes())
    return any(a.attrib.get("referencia") == target
               for a in root.findall(".//referencias/anteriores/"
                                     "anterior"))


def build_gold(targets: dict[str, dict],
               entries: dict[str, dict]) -> dict:
    """Declared modifiers per target: the frozen gold files plus a
    mechanical union with each target's own <posteriores> under the
    capture protocol's full relation family — frozen entries keep their
    recorded fields; derived additions carry provenance markers."""
    gold: dict[str, dict] = {}
    for gp in GOLD_SOURCES:
        for k, v in json.loads(gp.read_text(encoding="utf-8")).items():
            gold[k] = dict(v)
    for t in targets:
        xp = _target_xml_path(t, entries)
        if xp is None:
            continue
        derived = [d for d in _posteriores(xp)
                   if d["modifier_boe_id"]
                   and MOD_REL_RE.search(d["palabra"])]
        if t not in gold:
            gold[t] = {"target_boe_id": t, "declared": [],
                       "reverse_check": {},
                       "source": "derived_from_target_posteriores",
                       "source_artifact": str(xp.relative_to(ROOT))}
        rec = gold[t]
        known = {d["modifier_boe_id"] for d in rec["declared"]}
        rc = rec.setdefault("reverse_check", {})
        for d in derived:
            mb = d["modifier_boe_id"]
            r = _reverse_check(mb, t, entries)
            if r is not None:
                rc[mb] = r
            if mb not in known:
                rec["declared"].append(
                    {**d, "provenance": "derived_wide_family"})
    return {k: gold[k] for k in sorted(gold) if k in targets}


def main() -> int:
    tj = derive_targets()
    if tj["unique_count"] != EXPECTED_COUNT:
        print(f"STOP: unique target count {tj['unique_count']} "
              f"!= {EXPECTED_COUNT}", file=sys.stderr)
        print(json.dumps(sorted(tj["targets"]), indent=2))
        return 2

    entries = merge_entries()
    gold = build_gold(tj["targets"], entries)

    G2DEV.mkdir(parents=True, exist_ok=True)
    (G2DEV / "targets.json").write_bytes(
        (json.dumps(tj, indent=2, sort_keys=True, ensure_ascii=False)
         + "\n").encode("utf-8"))
    (G2DEV / "manifest.json").write_bytes((json.dumps({
        "gate": "G2.1",
        "description": "G2 DEV logical manifest — references to "
                       "already-open evidence only (EVIDENCE_IMPORT, "
                       "zero network).",
        "sources": [str(p.relative_to(ROOT)) for p in
                    MANIFEST_SOURCES],
        "targets": {b: t["cell"] for b, t in
                    sorted(tj["targets"].items())},
        "entries": entries,
    }, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        .encode("utf-8"))
    (G2DEV / "declared_modifiers.json").write_bytes(
        (json.dumps(gold, indent=2, sort_keys=True, ensure_ascii=False)
         + "\n").encode("utf-8"))
    print(json.dumps({
        "targets": tj["unique_count"],
        "entries": len(entries),
        "entries_with_bytes": sum(1 for e in entries.values()
                                  if "path" in e),
        "gold_targets": len(gold),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
