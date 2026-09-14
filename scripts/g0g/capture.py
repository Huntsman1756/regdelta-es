"""G0-G.0 evidence capture + declared-modifier gold + holdout seal.

Content-agnostic: what gets fetched is decided only by mechanical
markup enumeration of official documents — never by the RegDelta
evaluation pipeline. Imports only the transport primitive.

Per selected target:
  target diario XML (re-used from discovery capture)
  target doc representation (diario_boe/txt.php)
  target PDF (from the XML's own <url_pdf>)
  consolidada endpoints (metadatos / analisis / texto/indice)
  every <img src="/datos/imagenes/..."> in the target XML
  each modifier declared in <posteriores> (MODIFICA/CORRECCION family):
    same document set + the modifier's own images

Gold: declared_modifiers.json — the explicit posteriores block of each
target parsed independently of the runtime, cross-checked against each
modifier's own <anteriores> block.

Seal: evidence/g0g/holdout/SEAL commits the holdout manifest sha256,
artifact count, aggregate bytes, capture-script sha256 and base HEAD.

Usage: .venv/Scripts/python.exe -X utf8 scripts/g0g/capture.py
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
G0G = ROOT / "evidence" / "g0g"
DISCOVERY_MANIFEST = G0G / "raw" / "manifest.json"

BOE = "https://www.boe.es"
DIARIO_XML = BOE + "/diario_boe/xml.php?id={}"
TXT_URL = BOE + "/diario_boe/txt.php?id={}"
DOC_URL = BOE + "/buscar/doc.php?id={}"
CONSOL = BOE + "/datosabiertos/api/legislacion-consolidada/id/{}/{}"

MOD_REL_RE = re.compile(r"MODIFICA|CORRIGE|CORRECCI", re.IGNORECASE)
IMG_SRC_RE = re.compile(rb'<img[^>]+src="(/datos/imagenes/[^"]+)"')
URL_PDF_RE = re.compile(r"<url_pdf[^>]*>(https://www\.boe\.es[^<]+\.pdf)")

SELF = Path(__file__).resolve()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Capturer:
    """Append-only fetch-recorder writing a manifest per split."""

    def __init__(self, out_dir: Path, manifest: Path):
        self.dir = out_dir
        self.manifest_path = manifest
        self.dir.mkdir(parents=True, exist_ok=True)
        self.entries: dict[str, dict] = {}
        if manifest.exists():
            self.entries.update(json.loads(
                manifest.read_text(encoding="utf-8"))["entries"])
        self.by_url = {e["url"]: e for e in self.entries.values()}
        # discovery raws are re-usable bytes, not re-fetched
        dm = json.loads(DISCOVERY_MANIFEST.read_text(encoding="utf-8"))
        for e in dm["entries"].values():
            self.by_url.setdefault(e["url"], e)

    def get(self, name: str, url: str, accept: str) -> bytes | None:
        e = self.by_url.get(url)
        if e is not None and "path" in e:
            data = (ROOT / e["path"]).read_bytes()
            # re-record under this split's manifest with local path
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


def declared_modifiers(diario_xml: bytes) -> list[dict]:
    """Independent gold extractor: the official <posteriores> block
    only. No runtime parser involved."""
    root = ET.fromstring(diario_xml)
    post = root.find(".//posteriores")
    out = []
    if post is None:
        return out
    for p in post.findall("posterior"):
        palabra = (p.findtext("palabra") or "").strip()
        if MOD_REL_RE.search(palabra) and p.get("referencia"):
            out.append({"modifier_boe_id": p.get("referencia"),
                        "palabra": palabra,
                        "texto": (p.findtext("texto") or "").strip()})
    return out


def reverse_check(modifier_xml: bytes, target_boe: str) -> bool:
    """The modifier's own <anteriores> must reference the target."""
    root = ET.fromstring(modifier_xml)
    ant = root.find(".//anteriores")
    if ant is None:
        return False
    return any(a.get("referencia") == target_boe
               for a in ant.findall("anterior"))


def capture_instrument(cap: Capturer, boe_id: str,
                       xml: bytes) -> None:
    cap.get(f"boe_diario_xml__{boe_id}.xml", DIARIO_XML.format(boe_id),
            "application/xml")
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
        cap.get(f"boe_imagen__{boe_id}__{i:03d}.png", BOE + src.decode(),
                "image/*")


def capture_target(cap: Capturer, target: str, gold: dict) -> None:
    xml = (ROOT / "evidence" / "g0g" / "raw"
           / f"boe_diario_xml__{target}.xml").read_bytes()
    capture_instrument(cap, target, xml)
    mods = declared_modifiers(xml)
    g = gold[target] = {"declared": mods, "reverse_check": {}}
    for mod in mods:
        mid = mod["modifier_boe_id"]
        mxml = cap.get(f"boe_diario_xml__{mid}.xml",
                       DIARIO_XML.format(mid), "application/xml")
        if mxml is None:
            g["reverse_check"][mid] = "MODIFIER_XML_UNAVAILABLE"
            continue
        g["reverse_check"][mid] = reverse_check(mxml, target)
        capture_instrument(cap, mid, mxml)


def main() -> int:
    sel = json.loads((G0G / "selection.json").read_text(
        encoding="utf-8"))
    dev = [b for c in sel["cells"].values()
           for b in c["GENERALIZATION_DEV"]]
    holdout = [b for c in sel["cells"].values()
               for b in c["SEALED_HOLDOUT"]]
    gold: dict[str, dict] = {}
    for split, targets in (("dev", dev), ("holdout", holdout)):
        cap = Capturer(G0G / split / "raw", G0G / split / "manifest.json")
        for t in targets:
            print(f"{split}: capturing {t}")
            capture_target(cap, t, gold)
        cap.flush()
    (G0G / "gold").mkdir(exist_ok=True)
    (G0G / "gold" / "declared_modifiers.json").write_text(
        json.dumps(gold, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    hm = json.loads((G0G / "holdout" / "manifest.json")
                    .read_text(encoding="utf-8"))
    files = sorted((G0G / "holdout" / "raw").iterdir())
    blob = b"".join(f.read_bytes() for f in files)
    seal = {
        "sealed_at_head": "ef58530f5ba8787879ab897fecfc2dd9c424ce69",
        "targets": sorted(holdout),
        "manifest_sha256": sha256(
            (G0G / "holdout" / "manifest.json").read_bytes()),
        "artifact_count": len(files),
        "aggregate_bytes": len(blob),
        "aggregate_sha256": sha256(blob),
        "capture_script_sha256": sha256(SELF.read_bytes()),
        "rule": "no source/test/eval code may read these manifests "
                "until G0-G.2",
    }
    (G0G / "holdout" / "SEAL").write_text(json.dumps(
        seal, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: seal[k] for k in
                      ("targets", "artifact_count", "aggregate_bytes")},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
