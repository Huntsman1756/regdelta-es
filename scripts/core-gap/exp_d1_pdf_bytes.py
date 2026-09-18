#!/usr/bin/env python
"""CORE-GAP WS-D / EXP-D1: pypdf byte-equality experiment.

Question (preregistered): can an official signed BOE PDF representation
be bound deterministically and byte-faithfully to the representation
evidence RegDelta records (the served /datos/imagenes/disp PNGs)?

Method:
  1. sha256 the captured official PDF blob.
  2. Enumerate every /Image XObject reachable from each page —
     page /Resources, Form XObject /Resources (recursive), and
     inline images inside content streams (BI...ID...EI) — via pypdf
     raw object access. No decode-for-evidence, no rasterization,
     no OCR.
  3. Record per-image: page index, indirect object ref, raw stream
     sha256, decoded stream sha256 (derivative only), /Filter,
     /ColorSpace, /SMask, dimensions.
  4. sha256 every captured official PNG asset for the same document
     (/datos/imagenes/disp channel, declared in doc.html).
  5. Classify per the preregistered outcome vocabulary.
  6. Record page->boe-page mapping so representation association can
     be scored separately from byte equality.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pypdf  # noqa: E402

PDF = ROOT / "evidence" / "g0c" / "raw" / "boe_dias_pdf__BOE-A-2017-14334.pdf"
DOC_ID = "BOE-A-2017-14334"
MANIFEST = ROOT / "evidence" / "g2" / "dev" / "manifest.json"

_BI = re.compile(rb"\bBI\s")
_BOE_PAGE = re.compile(r"g\.\s*(\d{5,6})")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _image_records(obj, page_index, name, ref_id, seen):
    if ref_id is not None and ref_id in seen:
        return None
    if ref_id is not None:
        seen.add(ref_id)
    raw = getattr(obj, "_data", None)
    raw = bytes(raw) if raw is not None else None
    try:
        dec = obj.get_data()
    except Exception:
        dec = None
    smask = obj.get("/SMask")
    return {
        "page_index": page_index,
        "xobject_name": name,
        "ref": ref_id,
        "filter": str(obj.get("/Filter")),
        "colorspace": str(obj.get("/ColorSpace")),
        "bpc": str(obj.get("/BitsPerComponent")),
        "width": int(obj.get("/Width", 0)),
        "height": int(obj.get("/Height", 0)),
        "smask": str(smask) if smask is not None else None,
        "raw_sha256": sha256(raw) if raw is not None else None,
        "raw_len": len(raw) if raw is not None else 0,
        "decoded_sha256": sha256(dec) if dec is not None else None,
        "decoded_len": len(dec) if dec is not None else 0,
    }


def _walk_xobjects(xo_dict, page_index, seen, out, depth=0):
    if depth > 8:
        return
    for name, ref in xo_dict.items():
        try:
            obj = ref.get_object()
        except Exception:
            continue
        st = obj.get("/Subtype")
        ref_id = (str(getattr(ref, "idnum", "?")) + " "
                  + str(getattr(ref, "generation", "?")) + " R")
        if st == "/Image":
            rec = _image_records(obj, page_index, name, ref_id, seen)
            if rec:
                out.append(rec)
        elif st == "/Form":
            sub = obj.get("/Resources")
            if sub is not None:
                sub_xo = sub.get("/XObject")
                if sub_xo is not None:
                    _walk_xobjects(sub_xo.get_object(), page_index,
                                   seen, out, depth + 1)


def collect_images(reader) -> list[dict]:
    out = []
    seen = set()
    for pi, page in enumerate(reader.pages):
        res = page.get("/Resources")
        if res is None:
            continue
        xo = res.get("/XObject")
        if xo is not None:
            _walk_xobjects(xo.get_object(), pi, seen, out)
    return out


def inline_image_pages(reader) -> dict[int, int]:
    """Count BI markers per page content stream (inline images)."""
    counts = {}
    for pi, page in enumerate(reader.pages):
        try:
            data = page.get_contents().get_data()
        except Exception:
            continue
        n = len(_BI.findall(data))
        if n:
            counts[pi] = n
    return counts


def boe_page_map(reader) -> dict[int, int]:
    """diario page index -> boe page number from the printed header."""
    m = {}
    for pi, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception:
            continue
        g = _BOE_PAGE.search(t[:300])
        if g:
            m[pi] = int(g.group(1))
    return m


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / "evidence" / "core-gap" / "wsd" / "exp-d1")
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_bytes = PDF.read_bytes()
    reader = pypdf.PdfReader(str(PDF))
    images = collect_images(reader)
    inline = inline_image_pages(reader)
    page_map = boe_page_map(reader)

    man = json.load(open(MANIFEST, encoding="utf-8"))
    doc_pngs = {}
    for key, e in man["entries"].items():
        url = e.get("url", "")
        if "/datos/imagenes/disp/" in url and "14334_" in url:
            p = ROOT / e["path"]
            if p.exists():
                doc_pngs[url.split("/")[-1]] = {
                    "entry": key, "url": url,
                    "sha256": sha256(p.read_bytes()),
                    "len": p.stat().st_size}

    png_by_hash = {}
    for name, rec in doc_pngs.items():
        png_by_hash.setdefault(rec["sha256"], []).append(name)

    exact_raw = [i for i in images if i["raw_sha256"] in png_by_hash]
    exact_dec = [i for i in images if i["decoded_sha256"] in png_by_hash]

    # annex pages of the document inside this diario pdf: the doc's
    # annexes sit on boe pages 119940..119996 per the annex map
    annex_pi = sorted(pi for pi, bp in page_map.items()
                      if 119940 <= bp <= 120020)
    annex_xobjects = [i for i in images if i["page_index"] in annex_pi]
    annex_inline = {pi: inline[pi] for pi in annex_pi if pi in inline}

    ledger = {
        "experiment": "EXP-D1 pypdf byte-equality",
        "document": DOC_ID,
        "pypdf_version": pypdf.__version__,
        "pdf": {"path": str(PDF), "sha256": sha256(pdf_bytes),
                "len": len(pdf_bytes), "pages": len(reader.pages)},
        "xobjects_total": len(images),
        "xobjects_unique_refs": len({i["ref"] for i in images}),
        "xobjects_with_raw": sum(1 for i in images if i["raw_sha256"]),
        "xobjects_decoded": sum(1 for i in images
                                if i["decoded_sha256"]),
        "inline_image_pages_total": len(inline),
        "official_png_assets": len(doc_pngs),
        "exact_raw_matches": [
            {"ref": i["ref"], "page": i["page_index"],
             "matched_pngs": png_by_hash[i["raw_sha256"]]}
            for i in exact_raw],
        "exact_decoded_matches": [
            {"ref": i["ref"], "page": i["page_index"],
             "matched_pngs": png_by_hash[i["decoded_sha256"]]}
            for i in exact_dec],
        "filters": sorted({i["filter"] for i in images}),
        "colorspaces": sorted({i["colorspace"] for i in images}),
        "with_smask": sum(1 for i in images if i["smask"]),
        "annex_pages_diario_index": annex_pi,
        "annex_page_xobjects": annex_xobjects,
        "annex_page_inline_images": annex_inline,
        "images": images,
        "png_assets": doc_pngs,
    }
    (out_dir / "exp-d1-ledger.json").write_text(
        json.dumps(ledger, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: v for k, v in ledger.items()
                      if k not in ("images", "png_assets")}, indent=1))


if __name__ == "__main__":
    main()
