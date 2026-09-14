"""G1 §36: operation-owned content link classification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from regdelta import operations
from regdelta.sources.boe_diario import DiarioDoc, Node


def doc(*nodes) -> DiarioDoc:
    return DiarioDoc(nodes=[Node(i, *n) for i, n in enumerate(nodes)])


def parse(d):
    return operations.parse_operations(d, None)


def test_inline_quoted_content():
    d = doc(
        ("p", "articulo", "Artículo primero. Modificación."),
        ("blockquote", "cita",
         "a) Se modifica la norma 4, que queda redactada: «Texto "
         "nuevo completo»."))
    ops = [o for o in parse(d).operations if not o.is_container]
    assert ops
    assert ops[0].content_link_method == "INLINE_QUOTED_CONTENT"


def test_colon_following_block_explicit():
    d = doc(
        ("p", "articulo", "Artículo primero. Modificación de la "
                          "Circular 4/2017."),
        ("p", "parrafo",
         "a) El apartado 4 de la norma quinta queda redactado en los "
         "siguientes términos:"),
        ("p", "sangrado", "4. Nuevo contenido del apartado."),
        ("p", "parrafo", "b) Se suprime la norma sexta."))
    ops = parse(d).operations
    leaf = [o for o in ops if not o.is_container]
    assert leaf[0].content_link_method == "EXPLICIT_FOLLOWING_CONTENT"


def test_sibling_op_blocks_following_content():
    """A following paragraph that belongs to a sibling operation is
    never claimed as content (§18.4)."""
    d = doc(
        ("p", "articulo", "Artículo primero. Modificación de la "
                          "Circular 4/2017."),
        ("p", "parrafo", "a) Se suprime la norma cuarta."),
        ("p", "parrafo", "b) Se modifica la norma quinta."))
    leaf = [o for o in parse(d).operations if not o.is_container]
    assert leaf[0].operation_kind == "DELETE"
    # DELETE has no after; the next paragraph is the sibling locator
    assert leaf[0].content_link_method in (
        "NO_PROVEN_CONTENT", "DECLARED_LITERAL_ONLY")


def test_literals_only_declared():
    d = doc(
        ("p", "articulo", "Artículo primero. Corrección."),
        ("p", "parrafo",
         "1. En la norma 4, donde dice: «donde», debe decir: "
         "«debe»."))
    leaf = [o for o in parse(d).operations if not o.is_container]
    assert leaf[0].literals
    assert leaf[0].content_link_method == "DECLARED_LITERAL_ONLY"


def test_no_pointer_no_content():
    """A bare amendment clause with no pointer and no colon never owns
    the following nodes (§18.1)."""
    d = doc(
        ("p", "articulo", "Artículo primero. Modificación de la "
                          "Circular 4/2017."),
        ("p", "parrafo", "a) Se modifica la norma cuarta."),
        ("p", "parrafo", "Este párrafo no es contenido de la "
                         "operación."),
        ("p", "parrafo", "b) Se suprime la norma quinta."))
    leaf = [o for o in parse(d).operations if not o.is_container]
    assert leaf[0].content_link_method == "NO_PROVEN_CONTENT"


def test_annex_ref_method():
    d = doc(
        ("p", "articulo", "Artículo primero. Modificación de la "
                          "Circular 4/2017."),
        ("p", "parrafo",
         "a) Se modifica el fichero «X», por el que figura en el "
         "anejo de esta circular."))
    leaf = [o for o in parse(d).operations if not o.is_container]
    assert leaf[0].annex_ref
    assert leaf[0].content_link_method == "EXPLICIT_ANNEX_REFERENCE"
