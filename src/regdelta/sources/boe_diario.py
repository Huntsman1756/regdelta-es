"""Parser for the official BOE daily XML (``diario_boe/xml.php?id=...``).

Pure bytes -> structure. The proven mechanism from G0-C discovery is ported
here verbatim in semantics: ``<metadatos>`` fields, ``<analisis>`` legal
references (``<anteriores>``/``<posteriores>``), ``<notas>``, and the ``<texto>``
body as an ordered node list.

Node order matters: amendment operations and annexed artifacts are bound by
document position, so unlike the G0-C probe (which kept paragraphs and tables
apart) this parser preserves the interleaved order of the direct children of
``<texto>``. ``<blockquote>`` containers are flattened to a single text node:
their content is *quoted* new text and must never be mistaken for a locator.

No network, no file IO, no LLM.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

PARSER_NAME = "boe_diario_xml"
PARSER_VERSION = "v1"

NBSP = "\xa0"
_WS_RE = re.compile(r"\s+")

COMPLETE = "COMPLETE"
INVALID_STRUCTURE = "INVALID_STRUCTURE"


def normalize(text: str) -> str:
    """Hash-stable normalization: NBSP -> space, whitespace runs collapse."""
    return _WS_RE.sub(" ", text.replace(NBSP, " ")).strip()


@dataclass(frozen=True)
class Ref:
    direction: str  # "anterior" | "posterior"
    referencia: str
    palabra: str
    palabra_codigo: str
    texto: str


@dataclass(frozen=True)
class Node:
    """One direct child of ``<texto>`` in document order.

    kind: 'p' | 'table' | 'img' | 'blockquote'
    cls:  the ``class`` attribute (e.g. 'articulo', 'parrafo', 'imagen',
          'anexo', 'anexo_num', 'centro_negrita')
    text: normalized visible text ('' for images)
    img_src: image path for kind='img' (or imagen-class <p> wrapping <img>)
    blob: canonical serialization for kind='table' (used for content_sha256)
    """

    index: int
    kind: str
    cls: str
    text: str
    img_src: str | None = None
    blob: bytes | None = None
    rows: tuple = ()


@dataclass
class DiarioDoc:
    metadata: dict = field(default_factory=dict)
    metadata_eli: dict = field(default_factory=dict)
    anteriores: list[Ref] = field(default_factory=list)
    posteriores: list[Ref] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)

    def paragraphs(self) -> list[Node]:
        return [n for n in self.nodes if n.kind in ("p", "blockquote")]

    def images(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "img"]

    def tables(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "table"]


@dataclass
class DiarioParseResult:
    parse_status: str
    parse_error: str | None
    doc: DiarioDoc | None


def _refs(container: ET.Element | None, direction: str) -> list[Ref]:
    out: list[Ref] = []
    if container is None:
        return out
    for el in container.iter(direction):
        palabra_el = el.find("palabra")
        out.append(
            Ref(
                direction=direction,
                referencia=el.attrib.get("referencia", ""),
                palabra=normalize(palabra_el.text or "") if palabra_el is not None else "",
                palabra_codigo=(
                    palabra_el.attrib.get("codigo", "") if palabra_el is not None else ""
                ),
                texto=normalize(el.findtext("texto") or ""),
            )
        )
    return out


def _node_from(child: ET.Element, index: int) -> Node:
    if child.tag == "table":
        flat = normalize(" ".join("".join(c.itertext()) for c in child.iter()))
        rows = tuple(
            tuple(normalize("".join(c.itertext())) for c in tr)
            for tr in child.iter("tr")
        )
        return Node(index, "table", child.attrib.get("class", ""), flat,
                    blob=ET.tostring(child), rows=rows)
    img = child.find(".//img")
    if child.tag == "img" or (img is not None and child.attrib.get("class", "").startswith("imagen")):
        src = child.attrib.get("src") if child.tag == "img" else img.attrib.get("src")
        return Node(index, "img", child.attrib.get("class", ""), "", img_src=src)
    if child.tag == "blockquote":
        text = normalize(" ".join("".join(e.itertext()) for e in child.iter()))
        return Node(index, "blockquote", child.attrib.get("class", ""), text)
    return Node(index, "p", child.attrib.get("class", ""),
                normalize("".join(child.itertext())))


def parse_diario(body: bytes) -> DiarioParseResult:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        return DiarioParseResult(INVALID_STRUCTURE, f"xml parse error: {exc}", None)

    meta_el = root.find("metadatos")
    if meta_el is None:
        return DiarioParseResult(INVALID_STRUCTURE, "metadatos node missing", None)

    metadata: dict = {}
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
                metadata_eli.setdefault(tag, []).append(
                    el.attrib.get(
                        "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource",
                        normalize(el.text or ""),
                    )
                )

    analysis = root.find("analisis")
    anteriores: list[Ref] = []
    posteriores: list[Ref] = []
    notas: list[str] = []
    if analysis is not None:
        refs_el = analysis.find("referencias")
        if refs_el is not None:
            anteriores = _refs(refs_el.find("anteriores"), "anterior")
            posteriores = _refs(refs_el.find("posteriores"), "posterior")
        notas_el = analysis.find("notas")
        if notas_el is not None:
            notas = [normalize(n.text or "") for n in notas_el.findall("nota")]

    nodes: list[Node] = []
    texto = root.find("texto")
    if texto is not None:
        for i, child in enumerate(texto):
            nodes.append(_node_from(child, i))

    doc = DiarioDoc(
        metadata=metadata,
        metadata_eli=metadata_eli,
        anteriores=anteriores,
        posteriores=posteriores,
        notas=notas,
        nodes=nodes,
    )
    return DiarioParseResult(COMPLETE, None, doc)
