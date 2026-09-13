"""G0-C.1 discovery: minimal page->text map for the official BOE daily PDF.

Run:  python scripts/g0c1/probe_pdfmap.py

Question: can each of the 326 annex page images of Circular 4/2017 be bound
deterministically to a BOE page number and to the anejo/estado printed on it,
without OCR?

This module extracts the *text layer already embedded in the official PDF*
(no OCR performed by us) using only the standard library:

* plain (non object-stream) PDF objects are located with ``N 0 obj``;
* the true page order is obtained by walking the ``/Pages`` ``/Kids`` tree
  from the document catalog (file order of objects is NOT page order);
* each page's ``/Contents`` stream is zlib-decompressed and its literal
  strings ``(...)`` decoded with PDF literal-string escape rules
  (octal escapes cover Latin-1 accents).

Output: ``evidence/g0c1/page-map.json`` — for every PDF page (1-indexed, tree
order) the extracted text plus the derived BOE page number
(``pagina_inicial`` 119454 + index - 1; observed in the official sumario and
in the daily XML ``<metadatos>``).
"""

from __future__ import annotations

import re
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g0c"))
from probe_common import dump, read_raw  # noqa: E402

G0C1_DIR = Path(__file__).resolve().parents[2] / "evidence" / "g0c1"
PDF_RAW = "boe_dias_pdf__BOE-A-2017-14334"
PAGINA_INICIAL = 119454  # OBSERVED: sumario + <metadatos> of the daily XML

OBJ_RE = re.compile(rb"(\d+)\s+0\s+obj\b")
PAGE_RE = re.compile(rb"/Type\s*/Page[^s]")
CONTENTS_RE = re.compile(rb"/Contents\s+(?:\[\s*)?(\d+)\s+0\s+R")
CONTENTS_LIST_RE = re.compile(rb"/Contents\s*\[([^\]]+)\]")
STREAM_RE = re.compile(rb"stream\r?\n")
LIT_STR_RE = re.compile(rb"\(((?:[^()\\]|\\.)*)\)")
OCTAL_RE = re.compile(r"\\([0-7]{3})")
KIDS_RE = re.compile(rb"/Kids\s*\[([^\]]+)\]")
REF_RE = re.compile(rb"(\d+)\s+0\s+R")
ROOT_RE = re.compile(rb"/Root\s+(\d+)\s+0\s+R")
PAGES_RE = re.compile(rb"/Pages\s+(\d+)\s+0\s+R")


def _decode_literal(raw: bytes) -> str:
    s = raw.decode("latin-1")
    s = OCTAL_RE.sub(lambda m: chr(int(m.group(1), 8)), s)
    return (
        s.replace("\\(", "(")
        .replace("\\)", ")")
        .replace("\\n", " ")
        .replace("\\r", " ")
    )


class PdfMap:
    def __init__(self, pdf_bytes: bytes):
        self.data = pdf_bytes
        self.objects: dict[int, int] = {}
        for m in OBJ_RE.finditer(pdf_bytes):
            self.objects[int(m.group(1))] = m.end()
        self.pages: list[int] = self._page_order()

    def _object_body(self, objnum: int) -> bytes:
        start = self.objects[objnum]
        end = self.data.find(b"endobj", start)
        return self.data[start:end]

    def _page_order(self) -> list[int]:
        root = int(ROOT_RE.findall(self.data)[-1])
        pages_ref = int(PAGES_RE.search(self._object_body(root)).group(1))
        ordered: list[int] = []
        stack = [pages_ref]
        while stack:
            node = stack.pop(0)
            if PAGE_RE.search(self._object_body(node)[:400]):
                ordered.append(node)
            else:
                km = KIDS_RE.search(self._object_body(node))
                if km:
                    kids = [int(x) for x in REF_RE.findall(km.group(1))]
                    stack[0:0] = kids
        return ordered

    def _stream(self, objnum: int) -> bytes | None:
        body = self._object_body(objnum)
        sm = STREAM_RE.search(body)
        if not sm:
            return None
        sstart = self.objects[objnum] + sm.end()
        send = self.data.find(b"endstream", sstart)
        raw = self.data[sstart:send]
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return raw

    def page_text(self, page_index: int) -> str:
        """Return extracted text-layer text for a 0-indexed page."""
        body = self._object_body(self.pages[page_index])
        refs = []
        lm = CONTENTS_LIST_RE.search(body)
        if lm:
            refs = [int(x) for x in REF_RE.findall(lm.group(1))]
        else:
            cm = CONTENTS_RE.search(body)
            if cm:
                refs = [int(cm.group(1))]
        parts = []
        for ref in refs:
            dec = self._stream(ref) or b""
            parts.extend(LIT_STR_RE.findall(dec))
        return " ".join(_decode_literal(p) for p in parts)


def main() -> None:
    pdf = PdfMap(read_raw(PDF_RAW))
    total = len(pdf.pages)
    page_map = []
    for idx in range(total):
        text = pdf.page_text(idx)
        page_map.append({
            "pdf_page": idx + 1,
            "boe_page": PAGINA_INICIAL + idx,
            "text_length": len(text),
            "text": text,
        })
    out = {
        "schema": "regdelta.g0c1.page-map/v1",
        "pdf_raw": PDF_RAW,
        "pagina_inicial": PAGINA_INICIAL,
        "pdf_pages": total,
        "boe_page_span": [PAGINA_INICIAL, PAGINA_INICIAL + total - 1],
        "pages": page_map,
    }
    dump(out, G0C1_DIR / "page-map.json")
    print(f"pdf pages: {total}; boe pages {PAGINA_INICIAL}..{PAGINA_INICIAL + total - 1}")
    for idx in (0, 261, 262, 263, total - 1):
        print(f"  page {idx + 1:4d}: {page_map[idx]['text'][:100]!r}")


if __name__ == "__main__":
    main()
