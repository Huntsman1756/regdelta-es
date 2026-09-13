"""G0-C.1 discovery: estado -> BOE page -> image binding for Circular 4/2017.

Run:  python scripts/g0c1/probe_annexmap.py

Inputs (all previously captured, hashed raw artifacts):
* ``evidence/g0c1/page-map.json`` — embedded text layer of the official
  daily PDF, in true page order (no OCR performed by us);
* ``evidence/g0c1/image-inventory.json`` — alt -> src -> BOE page;
* the correction BOE-A-2018-2041 raw XML — its items cite BOE page numbers
  and estado codes literally, giving independent OBSERVED anchors.

Output: ``evidence/g0c1/annex-map.json`` — for each detected estado code the
BOE page span and image ``alt`` numbers, plus the result of cross-checking
every correction-cited page against the page-map code detected there.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g0c"))
from probe_parse import parse_document  # noqa: E402

G0C1_DIR = Path(__file__).resolve().parents[2] / "evidence" / "g0c1"
CORRECTION_RAW = "boe_diario_xml__BOE-A-2018-2041"
FIRST_ANNEX_PAGE = 119716

# Estado/sub-state code at the start of a page's text layer, e.g.
# "FI 105-1", "FI 142-1.1", "FC 201-2", "UEM 3", "PI 1-1", "ANEJO 7".
# OCR glitches like "FI 100-1 4" are normalized by removing spaces inside
# the numeric tail.
# The OCR layer sometimes letter-spaces codes ("F I  101"); the prefix
# pattern tolerates optional spaces between letters, and all spaces are
# stripped before normalization.
CODE_RE = re.compile(
    r"\b(F\s*I|F\s*C|P\s*I|P\s*C|P\s*A|U\s*E\s*M|A\s*V\s*E|A\s*N\s*E\s*J\s*O)"
    r"\s+(\d[\d\- .]*\d|\d)"
)
CORR_ITEM_RE = re.compile(
    r"p[áa]gina\s+(\d{6}).{0,80}?estado\s+((?:FI|FC|UEM)\s*[\d\- .]*\d)",
    re.IGNORECASE,
)


def _normalize_code(prefix: str, tail: str) -> str:
    prefix = re.sub(r"\s+", "", prefix)
    tail = re.sub(r"\s+", "", tail)
    return f"{prefix} {tail}"


def estado_root(code: str) -> str:
    """'FI 105-1' -> 'FI 105'; 'FI 142-1.1' -> 'FI 142'; 'UEM 3' -> 'UEM 3'."""
    m = re.match(r"([A-Z]+)\s*(\d+)", code)
    if m and m.group(1) in {"FI", "FC", "PI", "PC", "PA", "AVE"}:
        return f"{m.group(1)} {m.group(2)}"
    return code.split("-")[0].strip()


# An "índice" (index) page lists dozens of estado codes; a content page
# carries only its own header code(s). Empirically index pages contain
# >= 10 distinct codes, content pages <= 5.
INDEX_CODE_THRESHOLD = 10


def distinct_codes(text: str) -> list[str]:
    seen: list[str] = []
    for m in CODE_RE.finditer(text):
        c = _normalize_code(m.group(1), m.group(2))
        if c not in seen:
            seen.append(c)
    return seen


def first_code(text: str) -> str | None:
    m = CODE_RE.search(text[:600])
    if not m:
        return None
    return _normalize_code(m.group(1), m.group(2))


def main() -> None:
    page_map = json.loads((G0C1_DIR / "page-map.json").read_text(encoding="utf-8"))
    inventory = json.loads(
        (G0C1_DIR / "image-inventory.json").read_text(encoding="utf-8")
    )
    img_by_page = {i["boe_page"]: i["alt"] for i in inventory["images"]}

    pages = []
    for p in page_map["pages"]:
        boe = p["boe_page"]
        if boe < FIRST_ANNEX_PAGE:
            continue
        codes = distinct_codes(p["text"])
        kind = (
            "INDEX" if len(codes) >= INDEX_CODE_THRESHOLD
            else "CONTENT" if codes
            else "CONTINUATION"
        )
        code = first_code(p["text"]) if kind == "CONTENT" else None
        pages.append({
            "boe_page": boe,
            "img_alt": img_by_page.get(boe),
            "kind": kind,
            "code_detected": code,
            "estado_root": estado_root(code) if code else None,
        })

    # Estado page spans: a content-page code opens a span closed by the next
    # different root; continuation pages attach to the open span; index
    # pages break the current span without opening a new one.
    estados: dict[str, dict] = {}
    current_root = None
    for pg in pages:
        if pg["kind"] == "INDEX":
            current_root = None
            continue
        root = pg["estado_root"]
        if root and root != current_root:
            current_root = root
            estados.setdefault(root, {"pages": [], "codes_seen": []})
        if current_root:
            pg["span_root"] = current_root
            estados[current_root]["pages"].append(pg["boe_page"])
            if pg["code_detected"] and pg["code_detected"] not in estados[current_root]["codes_seen"]:
                estados[current_root]["codes_seen"].append(pg["code_detected"])
        else:
            pg["span_root"] = None

    for root, info in estados.items():
        info["img_alts"] = [img_by_page[p] for p in info["pages"] if p in img_by_page]
        info["page_span"] = [info["pages"][0], info["pages"][-1]]

    # Independent anchors: correction items cite (page, estado) literally.
    corr = parse_document(CORRECTION_RAW)
    anchors = []
    for _cls, text in corr.paragraphs:
        for page, code in CORR_ITEM_RE.findall(text):
            code = re.sub(r"(?<=\d)\s+(?=\d)", "", code).strip()
            boe = int(page)
            pg = next((p for p in pages if p["boe_page"] == boe), None)
            detected = pg["code_detected"] if pg else None
            span = pg.get("span_root") if pg else None
            anchors.append({
                "correction_page": boe,
                "correction_code": code,
                "pagemap_code": detected,
                "span_root": span,
                "img_alt": img_by_page.get(boe),
                "match": (
                    (detected is not None and estado_root(detected) == estado_root(code))
                    or (span is not None and span == estado_root(code))
                ),
            })

    out = {
        "schema": "regdelta.g0c1.annex-map/v1",
        "target": "BOE-A-2017-14334",
        "method": {
            "page_detection": (
                "DERIVED: first estado code in the PDF embedded text layer "
                "(official BOE OCR text, no OCR by us), first 600 chars/page"
            ),
            "page_binding": "DERIVED-anchored: see image-inventory.json",
            "anchors": (
                "OBSERVED: correction BOE-A-2018-2041 cites (BOE page, estado "
                "code) literally; every cited page is cross-checked against "
                "the code detected in the PDF text layer"
            ),
        },
        "estado_count": len(estados),
        "estados": {
            root: {
                "page_span": info["page_span"],
                "img_alts": info["img_alts"],
                "codes_seen": info["codes_seen"],
            }
            for root, info in estados.items()
        },
        "correction_anchors": anchors,
        "anchors_matching": sum(1 for a in anchors if a["match"]),
        "anchors_total": len(anchors),
        "pages": pages,
    }
    path = G0C1_DIR / "annex-map.json"
    path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"estados detected: {len(estados)}")
    print(f"correction anchors: {out['anchors_matching']}/{out['anchors_total']} match")
    for a in anchors:
        flag = "OK " if a["match"] else "!! "
        print(f"  {flag}p.{a['correction_page']} corr={a['correction_code']!r} "
              f"pagemap={a['pagemap_code']!r} img=#{a['img_alt']}")
    print("wrote", path)


if __name__ == "__main__":
    main()
