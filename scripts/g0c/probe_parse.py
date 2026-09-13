"""G0-C discovery: pure parsing helpers over captured official XML.

These functions only read bytes already stored under ``evidence/g0c/raw`` and
transform them into plain Python structures. They contain no network access and
no legal interpretation.

Design rules
------------
* Normalisation is explicit and minimal: NO-BREAK SPACE (U+00A0) becomes an
  ordinary space, runs of whitespace collapse to one space, ends are stripped.
  Accents/case are preserved. This is the basis for every text SHA-256 so the
  hash is reproducible.
* Structure comes from the official XML: ``<metadatos>``, ``<analisis>`` and
  the paragraph ``class`` attributes emitted by BOE (``articulo``,
  ``sangrado``, ``parrafo_2`` ...). No heuristics beyond locating an explicit
  locator sentence.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from probe_common import read_raw_text

NBSP = "\xa0"
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS_RE.sub(" ", text.replace(NBSP, " ")).strip()


def load_root(name: str) -> ET.Element:
    return ET.fromstring(read_raw_text(name))


@dataclass
class Ref:
    direction: str  # "anterior" | "posterior"
    referencia: str
    palabra: str
    palabra_codigo: str
    texto: str


@dataclass
class Document:
    name: str
    metadata: dict
    metadata_eli: dict
    anteriores: list[Ref] = field(default_factory=list)
    posteriores: list[Ref] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    # list of (class, text) for every <p> in <texto>
    paragraphs: list[tuple[str, str]] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    image_srcs: list[str] = field(default_factory=list)


def _refs(container: ET.Element | None) -> list[Ref]:
    out: list[Ref] = []
    if container is None:
        return out
    for direction in ("anterior", "posterior"):
        for el in container.iter(direction):
            palabra_el = el.find("palabra")
            out.append(
                Ref(
                    direction=direction,
                    referencia=el.attrib.get("referencia", ""),
                    palabra=normalize(palabra_el.text or "") if palabra_el is not None else "",
                    palabra_codigo=palabra_el.attrib.get("codigo", "") if palabra_el is not None else "",
                    texto=normalize(el.findtext("texto") or ""),
                )
            )
    return out


def parse_document(name: str) -> Document:
    return parse_root(load_root(name), name)


def parse_root(root: ET.Element, name: str = "<memory>") -> Document:
    meta_el = root.find("metadatos")
    metadata: dict = {}
    if meta_el is not None:
        for el in meta_el:
            if el.tag in ("url_epub", "metadata-eli"):
                continue
            if el.tag == "estado_consolidacion":
                metadata[el.tag] = el.attrib.get("codigo")
            else:
                metadata[el.tag] = normalize(el.text or "")

    metadata_eli: dict = {}
    eli = root.find("metadata-eli")
    if eli is not None:
        for el in eli.iter():
            tag = el.tag.split("}")[-1]
            if tag in ("corrected_by", "version", "id_local", "jurisdiction", "type_document"):
                key = tag
                metadata_eli.setdefault(key, []).append(el.attrib.get(
                    "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource", normalize(el.text or "")
                ))

    analysis = root.find("analisis")
    anteriores: list[Ref] = []
    posteriores: list[Ref] = []
    notas: list[str] = []
    if analysis is not None:
        refs_el = analysis.find("referencias")
        if refs_el is not None:
            anteriores = [r for r in _refs(refs_el) if r.direction == "anterior"]
            posteriores = [r for r in _refs(refs_el) if r.direction == "posterior"]
        notas_el = analysis.find("notas")
        if notas_el is not None:
            notas = [normalize(n.text or "") for n in notas_el.findall("nota")]

    paragraphs: list[tuple[str, str]] = []
    tables: list[str] = []
    image_srcs: list[str] = []
    texto = root.find("texto")
    if texto is not None:
        for p in texto.iter("p"):
            paragraphs.append((p.attrib.get("class", ""), normalize("".join(p.itertext()))))
        for tbl in texto.iter("table"):
            tables.append(normalize(" ".join("".join(c.itertext()) for c in tbl.iter())))
        for img in texto.iter("img"):
            image_srcs.append(img.attrib.get("src", ""))

    return Document(
        name=name,
        metadata=metadata,
        metadata_eli=metadata_eli,
        anteriores=anteriores,
        posteriores=posteriores,
        notas=notas,
        paragraphs=paragraphs,
        tables=tables,
        image_srcs=image_srcs,
    )


def find(paragraphs, pattern, start: int = 0, cls: str | None = None) -> int | None:
    rx = re.compile(pattern)
    for i in range(start, len(paragraphs)):
        klass, text = paragraphs[i]
        if cls is not None and klass != cls:
            continue
        if rx.search(text):
            return i
    return None


def join_span(paragraphs, i: int, j: int) -> str:
    return "\n".join(text for _cls, text in paragraphs[i:j] if text)


def extract_between(paragraphs, start_pattern: str, stop_pattern: str) -> tuple[str, dict]:
    """Return text from the paragraph AFTER ``start_pattern`` up to (not incl.) stop."""
    i = find(paragraphs, start_pattern)
    if i is None:
        raise LookupError(f"start pattern not found: {start_pattern!r}")
    j = find(paragraphs, stop_pattern, start=i + 1)
    if j is None:
        raise LookupError(f"stop pattern not found after start: {stop_pattern!r}")
    return join_span(paragraphs, i + 1, j), {"start_index": i, "stop_index": j}


def extract_heading_block(paragraphs, start_pattern: str, stop_pattern: str, cls: str = "articulo") -> tuple[str, dict]:
    """Return text from the paragraph matching ``start_pattern`` up to stop."""
    i = find(paragraphs, start_pattern, cls=cls)
    if i is None:
        raise LookupError(f"heading not found: {start_pattern!r}")
    j = find(paragraphs, stop_pattern, start=i + 1, cls=cls)
    if j is None:
        raise LookupError(f"stop heading not found: {stop_pattern!r}")
    return join_span(paragraphs, i, j), {"start_index": i, "stop_index": j}


LOCATOR_RE = re.compile(r"^(?:[a-z]\)|\d+\.|[ivxl]+\))\s")
AMEND_VERB_RE = re.compile(
    r"(?i)(se modifican|se modifica|se sustituyen|se sustituye|se suprimen|se suprime|"
    r"se a[nñ]aden|se a[nñ]ade|se eliminan|se elimina|se realizan|se introduce|se introducen)"
)
TARGET_NOUN_RE = re.compile(r"(?i)(En la norma|En el anejo|En el punto|En el estado|En la letra|En el apartado|La norma|El anejo)")


def locator_sentences(paragraphs) -> list[str]:
    out = []
    for _cls, text in paragraphs:
        if LOCATOR_RE.match(text) and AMEND_VERB_RE.search(text) and TARGET_NOUN_RE.search(text):
            out.append(text)
    return out


def corrections(paragraphs) -> list[str]:
    return [text for _cls, text in paragraphs if re.search(r"(?i)donde dice|debe decir|se elimina|se añade", text) and text[:3].strip().rstrip(".").isdigit()]


__all__ = [
    "Document",
    "Ref",
    "corrections",
    "extract_between",
    "extract_heading_block",
    "find",
    "join_span",
    "load_root",
    "locator_sentences",
    "normalize",
    "parse_document",
    "parse_root",
]
