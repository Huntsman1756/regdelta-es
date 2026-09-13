"""Capture the extra evidence needed for G0-C.2 reconstruction.

Serves already-captured evidence (g0c, g0c1) to the runtime fetch function;
anything missing is fetched live from the BOE and appended to
``evidence/g0c2/raw`` + ``manifest.json``. The image set is computed by the
reconstruction itself (whatever pages the parsed operations bind), not by a
hand-maintained list.

Usage: .venv/Scripts/python.exe -X utf8 scripts/g0c2/capture.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from regdelta import db as dbm, history
from regdelta.http import FetchResult, http_fetch

ROOT = Path(__file__).resolve().parents[2]
G0C2 = ROOT / "evidence" / "g0c2"
RAW = G0C2 / "raw"
MANIFEST = RAW / "manifest.json"

PRIOR = [ROOT / "evidence" / "g0c" / "raw" / "manifest.json",
         ROOT / "evidence" / "g0c1" / "raw" / "manifest.json"]

TARGET = "BOE-A-2017-14334"


def load_prior() -> dict[str, tuple[str, dict]]:
    """url -> (logical_name, manifest_entry)"""
    by_url = {}
    for mp in PRIOR:
        m = json.loads(mp.read_text(encoding="utf-8"))
        for name, e in m["entries"].items():
            data = (ROOT / e["path"]).read_bytes()
            by_url[e["url"]] = (name, e, data)
    return by_url


def main() -> int:
    prior = load_prior()
    new_entries: dict[str, dict] = {}
    fetched = {"n": 0}

    if MANIFEST.exists():
        prev = json.loads(MANIFEST.read_text(encoding="utf-8"))
        new_entries.update(prev.get("entries", {}))
    by_url_new = {e["url"]: n for n, e in new_entries.items()}

    def fetch_fn(url: str, accept: str) -> FetchResult:
        if url in prior:
            name, e, data = prior[url]
            return FetchResult(url, 200, "application/octet-stream", data,
                               None, None)
        if url in by_url_new:
            e = new_entries[by_url_new[url]]
            data = (RAW / Path(e["path"]).name).read_bytes()
            return FetchResult(url, 200, "application/octet-stream", data,
                               None, None)
        res = http_fetch(url, accept)
        if res.body is None:
            print(f"  FETCH FAIL {url}: {res.error_message}", flush=True)
            return res
        from regdelta.util import sha256_hex, now_utc_iso
        sha = sha256_hex(res.body)
        ext = (".png" if "imagenes" in url else
               ".pdf" if url.endswith(".pdf") else
               ".xml" if "xml.php" in url else ".html")
        # logical name mirrors earlier evidence conventions
        if "xml.php" in url:
            name = f"boe_diario_xml__{url.split('id=')[-1]}"
        elif "doc.php" in url:
            name = f"boe_doc_html__{url.split('id=')[-1]}"
        elif "/pdfs/" in url:
            name = f"boe_dias_pdf__{url.rsplit('/', 1)[-1][:-4]}"
        else:
            name = f"boe_imagen__{sha[:12]}"
        path = f"evidence/g0c2/raw/{name}{ext}"
        (RAW).mkdir(parents=True, exist_ok=True)
        (RAW / f"{name}{ext}").write_bytes(res.body)
        new_entries[name] = {
            "path": path, "url": url, "sha256": sha,
            "retrieved_at": now_utc_iso(), "size_bytes": len(res.body),
        }
        by_url_new[url] = name
        fetched["n"] += 1
        print(f"  +{fetched['n']:3d} {name}{ext} ({len(res.body)} B)",
              flush=True)
        time.sleep(0.15)
        return res

    data_dir = G0C2 / "_tmp_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "regdelta.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = dbm.connect(db_path)
    try:
        report = history.reconstruct(conn, data_dir, TARGET, fetch_fn)
        conn.commit()
    finally:
        conn.close()

    MANIFEST.write_text(json.dumps(
        {"entries": new_entries}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
