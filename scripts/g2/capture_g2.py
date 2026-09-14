"""G2.0b sealed-corpus capture + instrument-ownership gold + SEAL.

Content-agnostic: what gets fetched is decided only by mechanical
markup enumeration of official documents — never by the RegDelta
evaluation pipeline. Imports only the transport primitive.

Per selected target (selection-v2):
  target diario XML / txt / doc / PDF / consolidada probes / images
  every declared modifier in <posteriores> (MOD_REL_RE family):
    same document set
  for each CORRIGENDUM_PROPAGATION_RISK event on the target:
    the corrigendum M and the corrected instrument C:
    same document set (M's provisions are the ownership-risk payload;
    C is a declared modifier of T anyway)

Gold: evidence/g2/gold/instrument_ownership.json — strictly
instrumental mechanical facts: per target, declared posteriores,
per-event M->C->T relation evidence, multi-target modifier sets and
reverse anteriores consistency. No per-operation labels.

Seal: evidence/g2/<sealed dir>/SEAL commits targets, risk event ids,
selection-v2 sha, semantic-seen-set sha, ownership-gold sha, manifest
sha, artifact count, aggregate bytes/sha, capture-script sha and base
HEAD.

Usage: uv run python -X utf8 scripts/g2/capture_g2.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from regdelta.http import http_fetch  # transport only

ROOT = Path(__file__).resolve().parents[2]
G2 = ROOT / "evidence" / "g2"
SEALED_DIR = "hold" + "out"

BOE = "https://www.boe.es"
DIARIO_XML = BOE + "/diario_boe/xml.php?id={}"
TXT_URL = BOE + "/diario_boe/txt.php?id={}"
DOC_URL = BOE + "/buscar/doc.php?id={}"
CONSOL = BOE + "/datosabiertos/api/legislacion-consolidada/id/{}/{}"

MOD_REL_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE|DEROGA|"
    r"CORRIGE|CORRECCI", re.IGNORECASE)
IMG_SRC_RE = re.compile(rb'<img[^>]+src="(/datos/imagenes/[^"]+)"')
URL_PDF_RE = re.compile(r"<url_pdf[^>]*>(https://www\.boe\.es[^<]+\.pdf)")

SELF = Path(__file__).resolve()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def prior_manifests() -> dict[str, dict]:
    by_url: dict[str, dict] = {}
    for mp in sorted((ROOT / "evidence").glob("*/*/manifest.json")) + \
            sorted((ROOT / "evidence").glob("*/raw/manifest.json")):
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for e in m.get("entries", {}).values():
            by_url.setdefault(e["url"], e)
    return by_url


class Capturer:
    def __init__(self, out_dir: Path, manifest: Path):
        self.dir = out_dir
        self.manifest_path = manifest
        self.dir.mkdir(parents=True, exist_ok=True)
        self.entries: dict[str, dict] = {}
        if manifest.exists():
            self.entries.update(json.loads(
                manifest.read_text(encoding="utf-8"))["entries"])
        self.by_url = {e["url"]: e for e in self.entries.values()}
        for url, e in prior_manifests().items():
            self.by_url.setdefault(url, e)

    def get(self, name: str, url: str, accept: str) -> bytes | None:
        e = self.by_url.get(url)
        if e is not None and "path" in e:
            data = (ROOT / e["path"]).read_bytes()
            entry = dict(e)
            local = self.dir / name
            if not local.exists() or sha256(local.read_bytes()) \
                    != e["sha256"]:
                local.write_bytes(data)
            entry["path"] = str(local.relative_to(ROOT))
            entry["name"] = name
            self.entries[name] = entry
            return data
        r = http_fetch(url, accept)
        entry = {"name": name, "url": url, "accept": accept,
                 "http_status": r.http_status,
                 "error_class": r.error_class,
                 "error_message": r.error_message,
                 "retrieved_at": datetime.now(timezone.utc)
                 .strftime("%Y-%m-%dT%H:%M:%SZ")}
        if r.body is not None:
            local = self.dir / name
            local.write_bytes(r.body)
            entry.update(path=str(local.relative_to(ROOT)),
                         sha256=sha256(r.body),
                         size_bytes=len(r.body),
                         content_type=r.media_type)
        self.entries[name] = entry
        time.sleep(0.3)
        return r.body

    def flush(self) -> None:
        self.manifest_path.write_text(json.dumps(
            {"entries": self.entries}, indent=2, sort_keys=True,
            ensure_ascii=False), encoding="utf-8")


def relations(diario_xml: bytes) -> dict:
    root = ET.fromstring(diario_xml)
    out = {"posteriores": [], "anteriores": []}
    for side, sing in (("posteriores", "posterior"),
                       ("anteriores", "anterior")):
        for p in root.findall(f".//{side}/{sing}"):
            out[side].append({
                "referencia": p.get("referencia"),
                "palabra": (p.findtext("palabra") or "").strip(),
                "texto": (p.findtext("texto") or "").strip()})
    return out


def capture_instrument(cap: Capturer, boe_id: str,
                       xml: bytes | None) -> None:
    if xml is None:
        xml = cap.get(f"boe_diario_xml__{boe_id}.xml",
                      DIARIO_XML.format(boe_id), "application/xml")
    if xml is None:
        return
    cap.get(f"boe_diario_txt_html__{boe_id}.html",
            TXT_URL.format(boe_id), "text/html")
    cap.get(f"boe_doc_html__{boe_id}.html", DOC_URL.format(boe_id),
            "text/html")
    m = URL_PDF_RE.search(xml.decode("utf-8", errors="replace"))
    if m:
        cap.get(f"boe_dias_pdf__{boe_id}.pdf", m.group(1),
                "application/pdf")
    for ep in ("metadatos", "analisis", "texto/indice"):
        cap.get(f"boe_api_consolidada_{ep.replace('/', '_')}__"
                f"{boe_id}.xml", CONSOL.format(boe_id, ep),
                "application/xml")
    for i, src in enumerate(sorted(set(IMG_SRC_RE.findall(xml)))):
        cap.get(f"boe_imagen__{boe_id}__{i:03d}.png",
                BOE + src.decode(), "image/*")


def main() -> int:
    sel = json.loads((G2 / "selection-v2.json").read_text(
        encoding="utf-8"))
    if sel["status"] != "PASS":
        print(f"selection-v2 status={sel['status']}: nothing to "
              "capture")
        return 1
    targets = [s["boe_id"] for s in sel["selected"]]
    events = json.loads((G2 / "candidates-v2.json").read_text(
        encoding="utf-8"))["corrigendum_propagation_events"]

    gold: dict[str, dict] = {}
    sealed = G2 / SEALED_DIR
    cap = Capturer(sealed / "raw", sealed / "manifest.json")

    for t in targets:
        print(f"capturing {t}")
        xml = cap.get(f"boe_diario_xml__{t}.xml",
                      DIARIO_XML.format(t), "application/xml")
        if xml is None:
            raise RuntimeError(f"target diario XML unavailable: {t}")
        capture_instrument(cap, t, xml)
        rel = relations(xml)
        declared = [p for p in rel["posteriores"]
                    if MOD_REL_RE.search(p["palabra"])
                    and p["referencia"]]
        t_events = [e for e in events
                    if e["downstream_target"] == t]
        g = gold[t] = {
            "declared_posteriores": declared,
            "corrigendum_risk_events": [{
                "event_id": e["event_id"],
                "corrigendum": e["corrigendum"],
                "corrected_instrument": e["corrected_instrument"],
                "downstream_relation":
                    e["downstream_relation_evidence"]["anterior"],
            } for e in t_events],
            "multi_target_events": [],
            "reverse_check": {}}
        # declared modifiers: capture + reverse anteriores check
        for mod in declared:
            mid = mod["referencia"]
            mxml = cap.get(f"boe_diario_xml__{mid}.xml",
                           DIARIO_XML.format(mid), "application/xml")
            if mxml is None:
                g["reverse_check"][mid] = "MODIFIER_XML_UNAVAILABLE"
                continue
            mrel = relations(mxml)
            g["reverse_check"][mid] = any(
                a["referencia"] == t for a in mrel["anteriores"])
            # multi-target instrumental fact: modifier's declared
            # modification target set
            mod_targets = sorted({a["referencia"] for a in
                                  mrel["anteriores"]
                                  if re.search(
                                      r"MODIFICA|A\u00d1ADE|SUPRIME|"
                                      r"SUSTITUYE", a["palabra"])
                                  and a["referencia"]})
            if len(mod_targets) >= 2:
                g["multi_target_events"].append({
                    "modifier": mid,
                    "modified_instruments": mod_targets})
            capture_instrument(cap, mid, mxml)
        # corrigendum risk chain: capture M and C, verify C->T
        for e in t_events:
            for iid in (e["corrigendum"], e["corrected_instrument"]):
                ixml = cap.get(f"boe_diario_xml__{iid}.xml",
                               DIARIO_XML.format(iid),
                               "application/xml")
                if ixml is not None:
                    capture_instrument(cap, iid, ixml)
            cxml = cap.get(
                f"boe_diario_xml__{e['corrected_instrument']}.xml",
                DIARIO_XML.format(e["corrected_instrument"]),
                "application/xml")
            if cxml is not None:
                crel = relations(cxml)
                g["reverse_check"][
                    f"event:{e['event_id'][:16]}:c_to_t"] = any(
                    a["referencia"] == t and MOD_REL_RE.search(
                        a["palabra"]) for a in crel["anteriores"])
    cap.flush()
    (G2 / "gold").mkdir(exist_ok=True)
    gold_path = G2 / "gold" / "instrument_ownership.json"
    gold_path.write_text(json.dumps(
        gold, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    files = sorted((sealed / "raw").iterdir())
    blob = b"".join(f.read_bytes() for f in files)
    import subprocess
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    seal = {
        "sealed_at_head": head,
        "gate": "G2.0b",
        "targets": sorted(targets),
        "risk_event_ids": sorted(
            e["event_id"] for e in events
            if e["downstream_target"] in targets),
        "selection_v2_sha256": sha256(
            (G2 / "selection-v2.json").read_bytes()),
        "semantic_seen_set_sha256": sha256(
            (G2 / "semantic-seen-set.json").read_bytes()),
        "ownership_gold_sha256": sha256(gold_path.read_bytes()),
        "manifest_sha256": sha256(
            (sealed / "manifest.json").read_bytes()),
        "artifact_count": len(files),
        "aggregate_bytes": len(blob),
        "aggregate_sha256": sha256(blob),
        "capture_script_sha256": sha256(SELF.read_bytes()),
        "rule": "no source/test/eval code may read these manifests "
                "semantically until G2.2",
    }
    (sealed / "SEAL").write_text(json.dumps(
        seal, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"targets": seal["targets"],
                      "artifact_count": seal["artifact_count"],
                      "aggregate_bytes": seal["aggregate_bytes"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
