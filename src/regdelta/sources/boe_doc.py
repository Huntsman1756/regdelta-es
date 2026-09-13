"""Parser for the official BOE ``buscar/doc.php?id=...`` HTML page.

Only one extraction is supported and it is the one proven in G0-C.1: the
sequence of annex page images. The official HTML marks each ``<img>`` of the
annex with ``alt="N"`` (a sequence number, global for some documents and
restarted per annex for others — the caller must therefore use *document
order*, not the alt value, for page binding).

Pure bytes -> structure. No network, no file IO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PARSER_NAME = "boe_doc"
PARSER_VERSION = "v1"

_IMG_RE = re.compile(
    r'<img[^>]+src="(?P<src>/datos/imagenes/disp/[^"]+)"[^>]*alt="(?P<alt>\d+)"',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DocImage:
    index: int       # 0-based position in document order
    src: str         # path under https://www.boe.es
    alt: str         # official sequence label (may restart per annex)


def parse_doc_images(body: bytes) -> list[DocImage]:
    text = body.decode("utf-8", errors="replace")
    return [
        DocImage(i, m.group("src"), m.group("alt"))
        for i, m in enumerate(_IMG_RE.finditer(text))
    ]
