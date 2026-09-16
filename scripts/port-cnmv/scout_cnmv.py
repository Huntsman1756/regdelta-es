"""PORT-CNMV-0 — metadata-only CNMV corpus scout & sealed split.

Discovery logic ported from esdata@80b9eb0
``apps/workers/cnmv.py::_discover_cnmv_circulares`` (same index ->
year-range -> BOE link flow, same URL constants; stdlib port).

Inspection boundary (prereg): reads ONLY ``<metadatos>`` and
``<analisis>/<referencias>`` — issuer, rango, dates, canonical id,
anteriores/posteriores. Never parses ``<texto>``, annex content or
operative clauses. Runtime: zero changes to ``src/regdelta``.

Usage:
    PYTHONPATH=src python scripts/port-cnmv/scout_cnmv.py \
        --output evidence/port-cnmv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- discovery constants (ported verbatim from esdata@80b9eb0) --------
CNMV_CIRCULARES_MAIN_URL = \
    "https://www.cnmv.es/portal/Legislacion/Circulares.aspx"
CNMV_CIRCULARES_PATTERN = re.compile(
    r"/Portal/Legislacion/Circulares-(\d{4})-(\d{4})\.aspx", re.IGNORECASE)
CNMV_ISSUER = "Comisión Nacional del Mercado de Valores"

BOE_BASE = "https://www.boe.es"
XML_URL = BOE_BASE + "/diario_boe/xml.php?id={boe}"
DOC_URL = BOE_BASE + "/buscar/doc.php?id={boe}"
BOE_ID_RE = re.compile(r"BOE-A-\d{4}-\d+")
HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)

SPLIT_SEED = "regdelta-port-cnmv-v1"
CORRECTION_WORDS = ("CORREG", "CORREC")   # profile correction_palabras
SEMANTIC_SEEN = {"BOE-A-2020-14107"}    # opened during PORT review

UA = {"User-Agent": "regdelta-port-cnmv-scout/0"}
_DELAY = 0.4


def _fetch(url: str) -> bytes | None:
    time.sleep(_DELAY)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=40) as r:
            if r.status != 200:
                return None
            return r.read()
    except Exception:
        return None


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def _join(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        m = re.match(r"(https?://[^/]+)", base)
        return m.group(1) + href
    return base.rsplit("/", 1)[0] + "/" + href


def discover() -> dict[str, str]:
    """CNMV circulars index -> year-range pages -> {boe_id: boe_url}.

    Same flow as esdata@80b9eb0: main index yields the year-range
    pages; each page yields BOE document links.
    """
    out: dict[str, str] = {}
    body = _fetch(CNMV_CIRCULARES_MAIN_URL)
    if body is None:
        raise RuntimeError("CNMV main index unreachable")
    year_ranges = []
    for href in HREF_RE.findall(body.decode("utf-8", "replace")):
        if CNMV_CIRCULARES_PATTERN.search(href):
            u = _join(CNMV_CIRCULARES_MAIN_URL, href)
            if u not in year_ranges:
                year_ranges.append(u)
    for rurl in year_ranges:
        rbody = _fetch(rurl)
        if rbody is None:
            continue
        for href in HREF_RE.findall(rbody.decode("utf-8", "replace")):
            if "boe.es" not in href:
                continue
            m = BOE_ID_RE.search(href)
            if m:
                out.setdefault(m.group(0), _join(rurl, href))
    return out


def inspect_metadata(xml_bytes: bytes) -> dict | None:
    """Parse ONLY metadatos + referencias. Returns None on failure."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    meta_el = root.find("metadatos")
    if meta_el is None:
        return None
    meta = {ch.tag: (ch.text or "").strip() for ch in meta_el}
    anteriores, posteriores = [], []
    refs = root.find("analisis/referencias")
    if refs is not None:
        for tag, acc in (("anterior", anteriores), ("posterior", posteriores)):
            for cont in refs.findall(tag + "s"):
                for el in cont.iter(tag):
                    pal = el.find("palabra")
                    acc.append({
                        "referencia": el.get("referencia", ""),
                        "palabra": (pal.text or "").strip() if pal is not None else "",
                        "palabra_codigo": pal.get("codigo", "") if pal is not None else "",
                    })
    return {"metadata": meta, "anteriores": anteriores,
            "posteriores": posteriores}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--only-inspect", default=None,
                    help="comma-separated boe ids (skip discovery)")
    args = ap.parse_args()
    out_dir: Path = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- discovery ---------------------------------------------------
    if args.only_inspect:
        found = {b.strip(): XML_URL.format(boe=b.strip())
                 for b in args.only_inspect.split(",") if b.strip()}
    else:
        found = discover()
    # the seen fixture is always inspected/captured as DEV-only even
    # if the CNMV index no longer links it
    for b in SEMANTIC_SEEN:
        found.setdefault(b, XML_URL.format(boe=b))
    print(f"discovery: {len(found)} BOE ids from CNMV circular index")

    # --- metadata-only inspection ------------------------------------
    frame = []
    xml_cache: dict[str, bytes] = {}
    for boe_id in sorted(found):
        body = _fetch(XML_URL.format(boe=boe_id))
        if body is None:
            frame.append({"boe_id": boe_id, "discovery_url": found[boe_id],
                          "eligible": False,
                          "exclude_reasons": ["xml_unfetchable"]})
            continue
        xml_cache[boe_id] = body
        info = inspect_metadata(body)
        if info is None:
            frame.append({"boe_id": boe_id, "discovery_url": found[boe_id],
                          "eligible": False,
                          "exclude_reasons": ["xml_unparseable"]})
            continue
        meta = info["metadata"]
        mods = [r for r in info["posteriores"]
                if not any(w in r["palabra"].upper()
                           for w in CORRECTION_WORDS)]
        corr = [r for r in info["posteriores"]
                if any(w in r["palabra"].upper() for w in CORRECTION_WORDS)]
        reasons = []
        if CNMV_ISSUER not in meta.get("departamento", ""):
            reasons.append("issuer_not_cnmv")
        if meta.get("rango", "") != "Circular":
            reasons.append("rango_not_circular")
        if meta.get("identificador", "") != boe_id:
            reasons.append("boe_id_mismatch")
        if not mods:
            reasons.append("no_declared_modifiers")
        frame.append({
            "boe_id": boe_id,
            "discovery_url": found[boe_id],
            "identificador": meta.get("identificador"),
            "departamento": meta.get("departamento"),
            "rango": meta.get("rango"),
            "numero_oficial": meta.get("numero_oficial"),
            "titulo": meta.get("titulo"),
            "fecha_disposicion": meta.get("fecha_disposicion"),
            "fecha_publicacion": meta.get("fecha_publicacion"),
            "url_pdf": meta.get("url_pdf"),
            "url_eli": meta.get("url_eli"),
            "estatus_legislativo": meta.get("estatus_legislativo"),
            "anteriores": info["anteriores"],
            "modification_refs": mods,
            "correction_refs": corr,
            "declared_modifier_count": len(mods),
            "corrigendum_count": len(corr),
            "semantically_seen": boe_id in SEMANTIC_SEEN,
            "eligible": not reasons,
            "exclude_reasons": reasons,
        })
    elig = [e for e in frame if e["eligible"]]
    print(f"frame: {len(frame)} inspected, {len(elig)} eligible")

    # multi-target modifier events: same modifier referencia appearing
    # as a MODIFICATION posterior of >=2 eligible candidates
    mod_count: dict[str, int] = {}
    for e in elig:
        for r in e["modification_refs"]:
            mod_count[r["referencia"]] = mod_count.get(r["referencia"], 0) + 1
    multi_mods = {r for r, n in mod_count.items() if n >= 2}
    for e in frame:
        e["multi_target_modifier_event_count"] = sum(
            1 for r in e.get("modification_refs", [])
            if r["referencia"] in multi_mods)

    # --- stress rank + split -----------------------------------------
    prior_seen = set()
    ss = ROOT / "evidence" / "cov" / "semantic-seen-set.json"
    if ss.exists():
        prior_seen = set(json.loads(ss.read_text())["boe_ids"])
    for e in frame:
        e["unseen"] = not e["semantically_seen"] and e["boe_id"] not in prior_seen

    def rank(e):
        tiebreak = hashlib.sha256(
            (SPLIT_SEED + "|" + e["boe_id"]).encode()).hexdigest()
        return (-e["declared_modifier_count"],
                -e["multi_target_modifier_event_count"],
                -e["corrigendum_count"], tiebreak)

    ranked = sorted([e for e in elig if e["unseen"]], key=rank)
    if len(ranked) < 8:
        result = {
            "terminal": "INSUFFICIENT_CORPUS",
            "unseen_eligible": len(ranked),
            "required": 8,
        }
        (out_dir / "corpus-frame.json").write_text(
            json.dumps(frame, indent=1, ensure_ascii=False))
        (out_dir / "selection.json").write_text(
            json.dumps(result, indent=1, ensure_ascii=False))
        print("INSUFFICIENT_CORPUS", len(ranked))
        return 2

    top8 = ranked[:8]
    dev = [e["boe_id"] for i, e in enumerate(top8) if i % 2 == 0]
    holdout = [e["boe_id"] for i, e in enumerate(top8) if i % 2 == 1]
    dev_extra = [b for b in SEMANTIC_SEEN
                 if any(f["boe_id"] == b for f in frame)]
    selection = {
        "stress_rank": [e["boe_id"] for e in ranked],
        "split_rule": "top 8 unseen by frozen stress rank; "
                      "odd rank -> DEV, even rank -> SEALED_HOLDOUT",
        "dev": dev,
        "sealed_holdout": holdout,
        "dev_extra_seen_fixture": dev_extra,
    }
    print("dev:", dev, "+", dev_extra)
    print("holdout:", holdout)

    # --- capture ------------------------------------------------------
    # official raw artifacts needed by the future probe: diario XML,
    # doc HTML, PDF; plus each declared modifier's diario XML (the
    # reconstruct pipeline parses modifiers for operations).
    by_id = {e["boe_id"]: e for e in frame}

    def capture(targets: list[str], raw_dir: Path, manifest_path: Path):
        raw_dir.mkdir(parents=True, exist_ok=True)
        entries = {}
        wanted = list(targets)
        for t in targets:
            for r in by_id.get(t, {}).get("modification_refs", []):
                if r["referencia"] not in wanted and \
                        BOE_ID_RE.fullmatch(r["referencia"]):
                    wanted.append(r["referencia"])
        for boe in wanted:
            arts = [("boe_diario_xml__" + boe + ".xml",
                     XML_URL.format(boe=boe), "application/xml",
                     xml_cache.get(boe))]
            e = by_id.get(boe)
            if e is not None:
                arts.append(("boe_doc_html__" + boe + ".html",
                             DOC_URL.format(boe=boe), "text/html", None))
                if e.get("url_pdf"):
                    arts.append(("boe_dias_pdf__" + boe + ".pdf",
                                 e["url_pdf"], "application/pdf", None))
            elif boe not in xml_cache:
                # modifier outside frame: diario XML only
                pass
            for name, url, accept, cached in arts:
                body = cached if cached is not None else _fetch(url)
                if body is None:
                    entries[name] = {"name": name, "url": url,
                                     "accept": accept,
                                     "retrieved_at": _now(),
                                     "error_class": "FETCH_ERROR"}
                    continue
                rel = raw_dir.relative_to(ROOT) / name
                (raw_dir / name).write_bytes(body)
                entries[name] = {
                    "name": name, "url": url, "accept": accept,
                    "retrieved_at": _now(),
                    "path": str(rel).replace("\\", "/"),
                    "sha256": _sha(body), "size_bytes": len(body),
                    "http_status": 200,
                }
        manifest_path.write_text(json.dumps(
            {"captured_at": _now(), "entries": entries},
            indent=1, ensure_ascii=False))
        return entries

    dev_entries = capture(dev + dev_extra,
                          out_dir / "dev" / "raw",
                          out_dir / "dev" / "manifest.json")
    hold_entries = capture(holdout,
                           out_dir / "holdout" / "raw",
                           out_dir / "holdout" / "manifest.json")

    # --- seal holdout -------------------------------------------------
    hm_path = out_dir / "holdout" / "manifest.json"
    hm = json.loads(hm_path.read_text())
    hsha = _sha(hm_path.read_bytes())
    total_bytes = sum(e.get("size_bytes", 0) for e in hm["entries"].values())
    agg = hashlib.sha256()
    for name in sorted(hm["entries"]):
        e = hm["entries"][name]
        if "sha256" in e:
            agg.update(bytes.fromhex(e["sha256"]))
    seal = {
        "gate": "PORT-CNMV-0",
        "targets": holdout,
        "manifest_sha256": hsha,
        "artifact_count": len(hm["entries"]),
        "aggregate_bytes": total_bytes,
        "aggregate_sha256": agg.hexdigest(),
        "capture_script_sha256": _sha(Path(__file__).read_bytes()),
        "rule": "no source/test/eval code may read these artifacts "
                "semantically until PORT-CNMV-2 (sealed-runner protocol)",
        "sealed_at_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True,
            text=True, cwd=ROOT).stdout.strip(),
    }
    (out_dir / "holdout" / "SEAL").write_text(
        json.dumps(seal, indent=1, ensure_ascii=False))

    # --- outputs -------------------------------------------------------
    (out_dir / "corpus-frame.json").write_text(
        json.dumps(frame, indent=1, ensure_ascii=False))
    (out_dir / "selection.json").write_text(
        json.dumps(selection, indent=1, ensure_ascii=False))
    (out_dir / "semantic-seen-set.json").write_text(json.dumps({
        "semantically_seen": sorted(SEMANTIC_SEEN),
        "reason": {"BOE-A-2020-14107":
                   "BOE text opened during PORT architecture review; "
                   "DEV-only fixture, never holdout"},
        "prior_gate_seen_set": "evidence/cov/semantic-seen-set.json",
    }, indent=1, ensure_ascii=False))

    print("READY_FOR_CNMV_PROFILE_PROBE")
    print(f"dev artifacts: {len(dev_entries)}, "
          f"holdout artifacts: {len(hold_entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
