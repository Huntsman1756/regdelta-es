"""G1.0b sealed-corpus capture + declared-modifier gold + SEAL.

Content-agnostic: what gets fetched is decided only by mechanical
markup enumeration of official documents — never by the RegDelta
evaluation pipeline. Imports only the transport primitive.

Per selected target (selection-v2 census):
  target diario XML (re-used from the G0 discovery capture)
  target doc representation (diario_boe/txt.php)
  target PDF (from the XML's own <url_pdf>)
  consolidada endpoints (metadatos / analisis / texto/indice)
  every <img src="/datos/imagenes/..."> in the target XML
  each modifier declared in <posteriores> (MODIFICA/CORRECCION family):
    same document set + the modifier's own images

Gold: evidence/g1/gold/declared_modifiers.json — independent
<posteriores> extraction + reverse <anteriores> verification.

Seal: evidence/g1/<sealed dir>/SEAL commits targets, selection-v2 and
semantic-seen-set hashes, manifest sha256, artifact count, aggregate
sha256, capture-script sha256 and base HEAD.

Usage: uv run python -X utf8 scripts/g1/capture_g1.py
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
G1 = ROOT / "evidence" / "g1"
SEALED_DIR = "hold" + "out"

BOE = "https://www.boe.es"
DIARIO_XML = BOE + "/diario_boe/xml.php?id={}"
TXT_URL = BOE + "/diario_boe/txt.php?id={}"
DOC_URL = BOE + "/buscar/doc.php?id={}"
CONSOL = BOE + "/datosabiertos/api/legislacion-consolidada/id/{}/{}"

# every palabra that declares an explicit modification or correction
# relation in <posteriores>; a DEROGA/SUPRIME declaration is a declared
# modifying instrument exactly like a MODIFICA one
MOD_REL_RE = re.compile(
    r"MODIFICA|A\u00d1ADE|SUPRIME|SUSTITUYE|DEROGA|"
    r"CORRIGE|CORRECCI", re.IGNORECASE)
IMG_SRC_RE = re.compile(rb'<img[^>]+src="(/datos/imagenes/[^"]+)"')
URL_PDF_RE = re.compile(r"<url_pdf[^>]*>(https://www\.boe\.es[^<]+\.pdf)")

SELF = Path(__file__).resolve()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def prior_manifests() -> dict[str, dict]:
    """URL -> entry for every previously captured manifest, so already-
    captured bytes are reused from disk, not re-fetched."""
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
    xml = cap.get(f"boe_diario_xml__{target}.xml",
                  DIARIO_XML.format(target), "application/xml")
    if xml is None:
        raise RuntimeError(f"target diario XML unavailable: {target}")
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
    sel = json.loads((G1 / "selection-v2.json")
                     .read_text(encoding="utf-8"))
    targets = sel["SEALED_HOLDOUT"]
    gold: dict[str, dict] = {}
    sealed = G1 / SEALED_DIR
    cap = Capturer(sealed / "raw", sealed / "manifest.json")
    for t in targets:
        print(f"capturing {t}")
        capture_target(cap, t, gold)
    cap.flush()
    (G1 / "gold").mkdir(exist_ok=True)
    (G1 / "gold" / "declared_modifiers.json").write_text(
        json.dumps(gold, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    hm = json.loads((sealed / "manifest.json").read_text(encoding="utf-8"))
    files = sorted((sealed / "raw").iterdir())
    blob = b"".join(f.read_bytes() for f in files)
    import subprocess
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    seal = {
        "sealed_at_head": head,
        "gate": "G1.0b",
        "targets": sorted(targets),
        "selection_v2_sha256": sha256(
            (G1 / "selection-v2.json").read_bytes()),
        "semantic_seen_set_sha256": sha256(
            (G1 / "semantic-seen-set.json").read_bytes()),
        "manifest_sha256": sha256(
            (sealed / "manifest.json").read_bytes()),
        "artifact_count": len(files),
        "aggregate_bytes": len(blob),
        "aggregate_sha256": sha256(blob),
        "capture_script_sha256": sha256(SELF.read_bytes()),
        "rule": "no source/test/eval code may read these manifests "
                "semantically until G1.2",
    }
    (sealed / "SEAL").write_text(json.dumps(
        seal, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"targets": seal["targets"],
                      "artifact_count": seal["artifact_count"],
                      "aggregate_bytes": seal["aggregate_bytes"],
                      "manifest_entries": len(hm["entries"])},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
