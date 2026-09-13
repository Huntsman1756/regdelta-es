"""G0-C.1 discovery: annex image inventory + selective capture.

Run:  python scripts/g0c1/probe_images.py

Builds the deterministic image inventory of Circular 4/2017's annexes:

* the daily XML ``<texto>`` holds 326 consecutive ``<p class="imagen">`` after
  the signature block — OBSERVED;
* ``doc.php`` marks each ``<img>`` with ``alt="1..326"`` — an explicit
  sequence number OBSERVED in the official HTML;
* the sumario/``<metadatos>`` give ``pagina_inicial=119454`` /
  ``pagina_final=120041`` (588 pages) — OBSERVED;
* the PDF page tree has exactly 588 pages and its text layer shows the
  signature block ends on BOE page 119715, so annex image ``alt=N``
  corresponds to BOE page ``119715 + N`` — DERIVED, anchored by two
  independent official references (correction items cite BOE pages 119824
  for estado FI 102-2 and 119865 for estado FI 131-2.2, and the PDF text
  layer on exactly those pages names those estados).

The probe fetches a bounded sample of annex page images (the pages of the
estados exercised in the experimental cases plus boundary images) and stores
them under ``evidence/g0c1/raw`` with a dedicated SHA-256 manifest.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g0c"))
from probe_common import fetch, now_utc_iso, sha256_hex  # noqa: E402
from probe_parse import parse_document  # noqa: E402

G0C1_DIR = Path(__file__).resolve().parents[2] / "evidence" / "g0c1"
RAW_DIR = G0C1_DIR / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"

TARGET_RAW = "boe_diario_xml__BOE-A-2017-14334"
DOC_RAW = "boe_doc_html__BOE-A-2017-14334"
BOE_HOST = "https://www.boe.es"
FIRST_ANNEX_PAGE = 119716  # DERIVED-anchored: signature page is BOE 119715

# BOE pages to capture as image evidence: the experimental-case estado pages
# plus the first and last annex page as boundary checks.
PAGES_TO_FETCH = [
    119716,          # first annex page (anejo 1 index) — boundary
    119818,          # FI 100-14 (substituted by Circular 2/2020)
    119823, 119824,  # FI 102-1 / FI 102-2 (correction anchor 1)
    119835, 119836,  # FI 105 (substituted by Circular 1/2025)
    119837,          # FI 106-1.1 (nota modified by Circular 2/2018)
    119843,          # FI 106-3 (nota modified by Circular 2/2018)
    119865,          # FI 131-2.2 (correction anchor 2)
    119907,          # FI 142-1.1 (substituted by 2/2018 and 1/2025)
    119916,          # FI 150-8 (line modified 2018, substituted 2020)
    120041,          # last annex page — boundary
]


def _manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"schema": "regdelta.g0c1.raw_manifest/v1", "entries": {}}


def _save(manifest: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def image_inventory() -> list[dict]:
    """alt -> src -> derived BOE page, for all 326 annex images."""
    from probe_common import read_raw_text

    html = read_raw_text(DOC_RAW)
    pairs = re.findall(
        r'<img src="(/datos/imagenes/disp/[^"]+)"[^>]*alt="(\d+)"', html
    )
    inv = []
    for src, alt in pairs:
        n = int(alt)
        inv.append({
            "alt": n,
            "src": src,
            "url": BOE_HOST + src,
            "boe_page": FIRST_ANNEX_PAGE + n - 1,
        })
    return inv


def capture_image(item: dict) -> dict:
    name = f"boe_annex_img__{item['boe_page']}__alt{item['alt']:03d}"
    result = fetch(item["url"])
    entry = {
        "name": name,
        "url": item["url"],
        "accept": "*/*",
        "retrieved_at": now_utc_iso(),
        "http_status": result.http_status,
        "content_type": result.content_type,
        "error_class": result.error_class,
        "error_message": result.error_message,
        "sha256": None,
        "size_bytes": 0,
        "path": None,
        "boe_page": item["boe_page"],
        "alt": item["alt"],
    }
    if result.body is not None:
        path = RAW_DIR / f"{name}.png"
        path.write_bytes(result.body)
        entry["sha256"] = sha256_hex(result.body)
        entry["size_bytes"] = len(result.body)
        entry["path"] = str(path.relative_to(G0C1_DIR.parents[1])).replace("\\", "/")
    manifest = _manifest()
    manifest["entries"][name] = entry
    _save(manifest)
    return entry


def main() -> None:
    doc = parse_document(TARGET_RAW)
    inv = image_inventory()
    inventory_path = G0C1_DIR / "image-inventory.json"
    inventory_path.write_text(
        json.dumps(
            {
                "schema": "regdelta.g0c1.image-inventory/v1",
                "target": "BOE-A-2017-14334",
                "image_count_xml": len(doc.image_srcs),
                "image_count_html_alt": len(inv),
                "alt_sequential": [i["alt"] for i in inv] == list(range(1, len(inv) + 1)),
                "first_annex_boe_page": FIRST_ANNEX_PAGE,
                "binding_rule": (
                    "DERIVED: alt=N -> BOE page 119715+N. Anchors: PDF page tree "
                    "has 588 pages = pagina_inicial..pagina_final; signature ends "
                    "p.119715; corrections cite p.119824 (FI 102-2) and p.119865 "
                    "(FI 131-2.2) and the PDF text layer names those estados on "
                    "exactly those pages."
                ),
                "images": inv,
            },
            ensure_ascii=False, indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"inventory: {len(inv)} images; alt sequential: "
          f"{[i['alt'] for i in inv] == list(range(1, 327))}")
    print("wrote", inventory_path)

    by_page = {i["boe_page"]: i for i in inv}
    for page in PAGES_TO_FETCH:
        item = by_page.get(page)
        if item is None:
            print(f"  !! no image for BOE page {page}")
            continue
        entry = capture_image(item)
        print(f"  {entry['http_status']!s:>4}  {entry['size_bytes']:>8}  "
              f"{str(entry['sha256'])[:12]}  {entry['name']}")


if __name__ == "__main__":
    main()
