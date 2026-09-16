"""Canonical document/node contract (C-033): the typed stream every
source parser produces and every core engine consumes.

Source-specific parsers (profile package, e.g. ``sources/boe_diario``)
fill these shapes; the shapes themselves — and the meaning of their
fields — are core-owned so that a second source can emit the same
contract without core knowing the raw source format.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ref:
    direction: str  # "anterior" | "posterior"
    referencia: str
    palabra: str
    palabra_codigo: str
    texto: str


@dataclass(frozen=True)
class Node:
    """One direct child of the document body in document order.

    kind/cls spellings are source-recognized vocabulary (profile
    document_model); the shape and ordering guarantee are the core
    contract.
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
