"""G0-G.0 discovery: mechanical candidate pool + 2x2 stratification +
deterministic hash selection. Evidence-capture tooling only — this
script never runs the RegDelta evaluation pipeline (no reconstruct, no
operations parsing, no applicability, no queries).

Pool:      BdE official chronological circular index (captured).
Eligibility: is "Circular N/YYYY del Banco de España"; diario_boe XML
           responds; <analisis><posteriores> declares >=1 explicit
           MODIFICA/CORRECCION relation; not in the project seen-set.
Cells:     {TEXT, VISUAL} x {CONSOLIDATED, NON_CONSOLIDATED}
           VISUAL  = >=1 <img src="/datos/imagenes/..."> in diario XML
           CONSOLIDATED = consolidada metadatos endpoint returns 200
Select:    rank = sha256("regdelta-g0g-v1|" + boe_id) ascending;
           ranks 1-2 -> GENERALIZATION_DEV, rank 3 -> SEALED_HOLDOUT.
           Exactly 3 per cell; fewer => STOP.

Usage: .venv/Scripts/python.exe -X utf8 scripts/g0g/discover.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from regdelta.http import http_fetch  # transport only

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
RAW = G0G / "raw"
MANIFEST = RAW / "manifest.json"

INDEX_URL = ("https://www.bde.es/wbe/es/areas-actuacion/normativa/"
             "circulares-banco-de-espana/"
             "circulares-banco-espana-indice-cronologico/")
SUMARIO_URL = "https://www.boe.es/datosabiertos/api/boe/sumario/{}"
DIARIO_XML = "https://www.boe.es/diario_boe/xml.php?id={}"
CONSOL_METADATOS = ("https://www.boe.es/datosabiertos/api/"
                    "legislacion-consolidada/id/{}/metadatos")

SEED = "regdelta-g0g-v1"
MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
          "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
          "octubre": 10, "noviembre": 11, "diciembre": 12}
MOD_REL_RE = re.compile(r"MODIFICA|CORRIGE|CORRECCI", re.IGNORECASE)
IMG_RE = re.compile(rb'<img[^>]+src="/datos/imagenes/')
CIRC_RE = re.compile(r"Circular (\d+)/(\d{4})")
BOE_ID_RE = re.compile(r"BOE-A-\d{4}-\d+")

_entries: dict[str, dict] = {}
_prior_by_url: dict[str, dict] = {}


def capture(name: str, url: str, accept: str) -> bytes | None:
    """Fetch-and-record: every captured byte lands in raw/ + manifest.
    Idempotent: a previously captured URL is served from disk."""
    if url in _prior_by_url:
        e = _prior_by_url[url]
        _entries[e["name"]] = e
        return (ROOT / e["path"]).read_bytes() if "path" in e else None
    r = http_fetch(url, accept)
    entry = {"name": name, "url": url, "accept": accept,
             "http_status": r.http_status,
             "error_class": r.error_class,
             "error_message": r.error_message,
             "retrieved_at": datetime.now(timezone.utc)
             .strftime("%Y-%m-%dT%H:%M:%SZ")}
    if r.body is not None:
        path = RAW / f"{name}"
        path.write_bytes(r.body)
        entry.update(path=str(path.relative_to(ROOT)),
                     sha256=hashlib.sha256(r.body).hexdigest(),
                     size_bytes=len(r.body),
                     content_type=r.media_type)
    _entries[name] = entry
    time.sleep(0.3)  # be polite to the public endpoint
    return r.body


YEAR_HEADING_RE = re.compile(
    r'<p[^>]*class="[^"]*number[^"]*"[^>]*>\s*(\d{4})\s*</p>')
# "(BOE de 6 de diciembre de 2017)" or, inside a year section whose
# heading already gives it, "(BOE de 2 de noviembre)"
BOE_DATE_RE = re.compile(
    r"BOE de (\d{1,2}) de ([a-záéíóú]+)(?: de (\d{4}))?",
    re.IGNORECASE)


def index_entries(html: str) -> list[dict]:
    """(clf_id, circular N/YYYY, boe publication date) per index row.
    The anchor text ends at the circular name; the "(BOE de ...)" tail
    lives in the enclosing block. Entries under a year heading may omit
    the year — it is the section year."""
    tokens = sorted(
        [(m.start(), "year", m) for m in YEAR_HEADING_RE.finditer(html)]
        + [(m.start(), "link", m) for m in re.finditer(
            r'href="[^"]*clf_www/leyes\.jsp\?id=(\d+)[^"]*"[^>]*>',
            html)])
    year = None
    out = []
    for _, kind, m in tokens:
        if kind == "year":
            year = int(m.group(1))
            continue
        clf_id = m.group(1)
        block = html[m.start():m.start() + 4000]
        end = re.search(r"</li>", block)
        text = re.sub(r"<[^>]+>", " ",
                      block[:end.end()] if end else block)
        text = re.sub(r"\s+", " ", text).strip()
        cm = CIRC_RE.search(text)
        d = BOE_DATE_RE.search(text)
        if not (cm and d):
            continue
        yr = d.group(3) or (str(year) if year else None)
        if yr is None:
            continue
        out.append({"clf_id": clf_id,
                    "circular": f"{cm.group(1)}/{cm.group(2)}",
                    "boe_pub_date": (f"{yr}-"
                                     f"{MONTHS[d.group(2).lower()]:02d}-"
                                     f"{int(d.group(1)):02d}"),
                    "index_text": text})
    # the same circular can recur in the index; first occurrence wins
    seen = set()
    uniq = []
    for e in out:
        if e["circular"] not in seen:
            seen.add(e["circular"])
            uniq.append(e)
    return uniq


def boe_id_for(circular: str, pub_date: str, tag: str) -> str | None:
    """Resolve 'N/YYYY' + BOE pub date -> BOE-A id via the daily
    sumario item whose title starts with 'Circular N/YYYY'."""
    body = capture(f"boe_sumario__{pub_date}",
                   SUMARIO_URL.format(pub_date.replace("-", "")),
                   "application/xml")
    if body is None:
        return None
    root = ET.fromstring(body)
    want = f"Circular {circular}"
    hits = [it.findtext("identificador") for it in root.iter("item")
            if (it.findtext("titulo") or "").startswith(want)]
    return hits[0] if len(hits) == 1 else None


def seen_set() -> set[str]:
    """BOE ids of BdE circulars whose normative content is already
    captured before G0-G.0 in evidence/** (excluding this gate's own
    evidence/g0g output) or tests/fixtures/**.

    A capture only marks an id as seen when the captured document IS
    that instrument (per-instrument captures carry the id in the name)
    and its title identifies it as 'Circular N/YYYY'. A bare textual
    reference — e.g. a sumario item or a <posterior> mention inside
    another norm — does not capture its content and does not exclude it.
    """
    ids: set[str] = set()
    files = [p for p in ROOT.glob("evidence/*/raw/*")
             if p.is_file() and "g0g" not in p.parts]
    files += [p for p in ROOT.glob("tests/fixtures/*") if p.is_file()]
    for mp in files:
        name = mp.name
        if not name.startswith("boe_"):
            continue
        m = BOE_ID_RE.search(name)
        if not m:
            continue
        try:
            head = mp.read_bytes()[:300000].decode("utf-8",
                                                  errors="replace")
        except OSError:
            continue
        if re.search(r"<titulo>[^<]*Circular \d+/\d{4}", head) or \
                re.search(r"<title>[^<]*Circular \d+/\d{4}", head):
            ids.add(m.group(0))
    return ids


def classify(diario_xml: bytes) -> dict:
    """Structural classification only — never content reading."""
    root = ET.fromstring(diario_xml)
    post = root.find(".//posteriores")
    mod_rels = []
    if post is not None:
        for p in post.findall("posterior"):
            palabra = (p.findtext("palabra") or "")
            if MOD_REL_RE.search(palabra):
                mod_rels.append(p.get("referencia"))
    return {
        "modifier_relations": sorted(r for r in mod_rels if r),
        "has_declared_modifier": bool(mod_rels),
        "img_nodes": len(IMG_RE.findall(diario_xml)),
        "visual": bool(IMG_RE.findall(diario_xml)),
    }


def consolidated(boe_id: str) -> bool | None:
    name = f"boe_api_consolidada_metadatos__{boe_id}.xml"
    url = CONSOL_METADATOS.format(boe_id)
    if url in _prior_by_url:
        e = _prior_by_url[url]
        _entries[name] = e
        return {200: True, 404: False}.get(e["http_status"])
    r = http_fetch(url, "application/xml")
    _entries[name] = {"name": name,
                      "url": CONSOL_METADATOS.format(boe_id),
                      "accept": "application/xml",
                      "http_status": r.http_status,
                      "error_class": r.error_class,
                      "error_message": r.error_message,
                      "retrieved_at": datetime.now(timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%SZ")}
    if r.body is not None:
        (RAW / name).write_bytes(r.body)
        _entries[name].update(
            path=f"evidence/g0g/raw/{name}",
            sha256=hashlib.sha256(r.body).hexdigest(),
            size_bytes=len(r.body), content_type=r.media_type)
    time.sleep(0.3)
    if r.http_status == 200:
        return True
    if r.http_status == 404:
        return False
    return None


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists():
        prev = json.loads(MANIFEST.read_text(encoding="utf-8"))
        _prior_by_url.update(
            {e["url"]: e for e in prev.get("entries", {}).values()})
    seen = seen_set()
    (G0G / "seen-set.json").write_text(json.dumps(
        {"generated_at_head": "ef58530f5ba8787879ab897fecfc2dd9c424ce69",
         "scope": ["evidence/**", "tests/fixtures/**"],
         "boe_ids": sorted(seen)}, indent=2, sort_keys=True),
        encoding="utf-8")

    html = capture("bde_circulares_indice_cronologico.html",
                   INDEX_URL, "text/html").decode("utf-8",
                                                errors="replace")
    entries = index_entries(html)
    print(f"index entries: {len(entries)}")

    candidates = []
    for e in entries:
        boe_id = boe_id_for(e["circular"], e["boe_pub_date"],
                            e["clf_id"])
        if boe_id is None:
            e["status"] = "UNRESOLVED_BOE_ID"
            continue
        e["boe_id"] = boe_id
        if boe_id in seen:
            e["status"] = "SEEN"
            continue
        xml = capture(f"boe_diario_xml__{boe_id}.xml",
                      DIARIO_XML.format(boe_id), "application/xml")
        if xml is None:
            e["status"] = "XML_UNAVAILABLE"
            continue
        cls = classify(xml)
        e.update(cls)
        e["consolidated"] = consolidated(boe_id)
        if not cls["has_declared_modifier"]:
            e["status"] = "NO_DECLARED_MODIFIER"
        elif e["consolidated"] is None:
            e["status"] = "CONSOLIDADA_UNKNOWN"
        else:
            e["status"] = "ELIGIBLE"
            cell = ("VISUAL" if cls["visual"] else "TEXT") + "x" + \
                   ("CONSOLIDATED" if e["consolidated"]
                    else "NON_CONSOLIDATED")
            e["cell"] = cell
        candidates.append(e)
        print(f"  {e['circular']:>8} {boe_id} {e['status']}"
              f" {e.get('cell', '')}")

    cells: dict[str, list[str]] = {}
    for e in candidates:
        if e["status"] == "ELIGIBLE":
            cells.setdefault(e["cell"], []).append(e["boe_id"])
    for cell, ids in cells.items():
        ids.sort(key=lambda b: hashlib.sha256(
            f"{SEED}|{b}".encode()).hexdigest())
    selection = {"seed": SEED, "rule": "sha256(seed|boe_id) asc",
                 "per_cell": "ranks 1-2 DEV, rank 3 HOLDOUT",
                 "cells": {}}
    for cell, ids in cells.items():
        ranks = {b: i + 1 for i, b in enumerate(ids)}
        selection["cells"][cell] = {
            "ranked": ranks,
            "GENERALIZATION_DEV": ids[:2],
            "SEALED_HOLDOUT": ids[2:3]}
        if len(ids) < 3:
            selection["cells"][cell]["STOP"] = (
                "fewer than 3 eligible candidates")
    (G0G / "candidates.json").write_text(json.dumps(
        {"index_source": INDEX_URL, "entries": candidates},
        indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (G0G / "selection.json").write_text(json.dumps(
        selection, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    MANIFEST.write_text(json.dumps({"entries": _entries},
                                   indent=2, sort_keys=True,
                                   ensure_ascii=False), encoding="utf-8")
    print(json.dumps({c: v.get("SEALED_HOLDOUT", "STOP")
                      for c, v in selection["cells"].items()},
                     indent=2))
    stops = [c for c, v in selection["cells"].items() if "STOP" in v]
    if len(selection["cells"]) < 4 or stops:
        print("STOP: cells underpopulated ->", stops)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
