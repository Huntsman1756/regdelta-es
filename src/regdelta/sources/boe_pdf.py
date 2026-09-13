"""Extractor for the embedded text layer of official BOE daily PDFs.

Ported from the G0-C.1 probe (``scripts/g0c1/probe_pdfmap.py``). This is NOT
OCR: the official PDF artifact already embeds a text layer produced by the
BOE; we only decode what is there.

Only the standard library is used:

* plain (non object-stream) PDF objects are located with ``N 0 obj``;
* true page order comes from walking the ``/Pages`` ``/Kids`` tree from the
  document catalog (file order of objects is NOT page order);
* each page's ``/Contents`` stream is zlib-decompressed and its literal
  strings ``(...)`` decoded with PDF literal-string rules (octal escapes
  cover Latin-1 accents).

Limitations are deliberate: font ``ToUnicode`` maps are not applied, so some
glyphs decode imperfectly. The layer is used exclusively for *locating*
estados on pages — it is never promoted to ``text_content`` of a
representation (that would blur the line between official text and a
rendering artifact).
"""

from __future__ import annotations

import re
import zlib

PARSER_NAME = "boe_pdf_textlayer"
PARSER_VERSION = "v1"

_OBJ_RE = re.compile(rb"(\d+)\s+0\s+obj\b")
_PAGE_RE = re.compile(rb"/Type\s*/Page[^s]")
_CONTENTS_RE = re.compile(rb"/Contents\s+(?:\[\s*)?(\d+)\s+0\s+R")
_CONTENTS_LIST_RE = re.compile(rb"/Contents\s*\[([^\]]+)\]")
_STREAM_RE = re.compile(rb"stream\r?\n")
_LIT_STR_RE = re.compile(rb"\(((?:[^()\\]|\\.)*)\)")
_OCTAL_RE = re.compile(r"\\([0-7]{3})")
_KIDS_RE = re.compile(rb"/Kids\s*\[([^\]]+)\]")
_REF_RE = re.compile(rb"(\d+)\s+0\s+R")
_ROOT_RE = re.compile(rb"/Root\s+(\d+)\s+0\s+R")
_PAGES_RE = re.compile(rb"/Pages\s+(\d+)\s+0\s+R")


def _decode_literal(raw: bytes) -> str:
    s = raw.decode("latin-1")
    s = _OCTAL_RE.sub(lambda m: chr(int(m.group(1), 8)), s)
    return (
        s.replace("\\(", "(")
        .replace("\\)", ")")
        .replace("\\n", " ")
        .replace("\\r", " ")
    )


class PdfTextLayer:
    def __init__(self, pdf_bytes: bytes):
        self.data = pdf_bytes
        self.objects: dict[int, int] = {}
        for m in _OBJ_RE.finditer(pdf_bytes):
            self.objects[int(m.group(1))] = m.end()
        self.pages: list[int] = self._page_order()

    def _object_body(self, objnum: int) -> bytes:
        start = self.objects[objnum]
        end = self.data.find(b"endobj", start)
        return self.data[start:end]

    def _page_order(self) -> list[int]:
        roots = _ROOT_RE.findall(self.data)
        if not roots:
            return []
        root = int(roots[-1])
        pages_ref = int(_PAGES_RE.search(self._object_body(root)).group(1))
        ordered: list[int] = []
        stack = [pages_ref]
        while stack:
            node = stack.pop(0)
            if _PAGE_RE.search(self._object_body(node)[:400]):
                ordered.append(node)
            else:
                km = _KIDS_RE.search(self._object_body(node))
                if km:
                    kids = [int(x) for x in _REF_RE.findall(km.group(1))]
                    stack[0:0] = kids
        return ordered

    def _stream(self, objnum: int) -> bytes | None:
        body = self._object_body(objnum)
        sm = _STREAM_RE.search(body)
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
        """Extracted text-layer text for a 0-indexed page."""
        body = self._object_body(self.pages[page_index])
        refs: list[int] = []
        lm = _CONTENTS_LIST_RE.search(body)
        if lm:
            refs = [int(x) for x in _REF_RE.findall(lm.group(1))]
        else:
            cm = _CONTENTS_RE.search(body)
            if cm:
                refs = [int(cm.group(1))]
        parts = []
        for ref in refs:
            dec = self._stream(ref) or b""
            parts.extend(_LIT_STR_RE.findall(dec))
        return " ".join(_decode_literal(p) for p in parts)

    def page_texts(self) -> list[str]:
        return [self.page_text(i) for i in range(len(self.pages))]
