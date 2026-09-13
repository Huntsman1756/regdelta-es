"""G0-C.1 discovery: generic official-source capture into the g0c1 manifest.

Run:  python scripts/g0c1/probe_fetch.py

Fetches the small set of additional official artifacts needed by the
annex/state cases (the BOE-A-2020-6186 daily PDF and its annex page images)
and records them under ``evidence/g0c1/raw`` with SHA-256, mirroring the
G0-C manifest schema.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g0c"))
from probe_common import fetch, now_utc_iso, sha256_hex  # noqa: E402

G0C1_DIR = Path(__file__).resolve().parents[2] / "evidence" / "g0c1"
RAW_DIR = G0C1_DIR / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"

ARTIFACTS = [
    {
        "name": "boe_dias_pdf__BOE-A-2020-6186",
        "url": "https://www.boe.es/boe/dias/2020/06/16/pdfs/BOE-A-2020-6186.pdf",
        "ext": "pdf",
        "note": "daily PDF of Circular 2/2020; its anejos 4-5 are page images",
    },
    {
        "name": "boe_doc_html__BOE-A-2020-6186",
        "url": "https://www.boe.es/buscar/doc.php?id=BOE-A-2020-6186",
        "ext": "html",
        "note": "doc.php of Circular 2/2020; img alt sequence for annex binding",
    },
]
# Annex images of BOE-A-2020-6186 (observed in its daily XML <p class=imagen>)
for i, src in enumerate([
    "06186_5694", "06186_5812", "06186_5885", "06186_5958", "06186_6032",
    "06186_6105", "06186_6179", "06186_6253", "06186_6393",
], start=1):
    ARTIFACTS.append({
        "name": f"boe_annex_img__2020-6186__alt{i:03d}",
        "url": f"https://www.boe.es/datos/imagenes/disp/2020/168/{src}.png",
        "ext": "png",
        "note": f"annex page image alt={i} of BOE-A-2020-6186",
    })


def main() -> None:
    manifest = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if MANIFEST_PATH.exists()
        else {"schema": "regdelta.g0c1.raw_manifest/v1", "entries": {}}
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for art in ARTIFACTS:
        result = fetch(art["url"])
        entry = {
            "name": art["name"],
            "url": art["url"],
            "accept": "*/*",
            "retrieved_at": now_utc_iso(),
            "http_status": result.http_status,
            "content_type": result.content_type,
            "error_class": result.error_class,
            "error_message": result.error_message,
            "note": art["note"],
            "sha256": None,
            "size_bytes": 0,
            "path": None,
        }
        if result.body is not None:
            path = RAW_DIR / f"{art['name']}.{art['ext']}"
            path.write_bytes(result.body)
            entry["sha256"] = sha256_hex(result.body)
            entry["size_bytes"] = len(result.body)
            entry["path"] = str(path.relative_to(G0C1_DIR.parents[1])).replace("\\", "/")
        manifest["entries"][art["name"]] = entry
        print(f"{entry['http_status']!s:>4}  {entry['size_bytes']:>9}  "
              f"{str(entry['sha256'])[:12]}  {art['name']}")
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("wrote", MANIFEST_PATH)


if __name__ == "__main__":
    main()
