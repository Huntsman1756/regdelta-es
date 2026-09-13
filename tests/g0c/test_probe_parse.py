"""Offline unit tests for the G0-C parsing/extraction helpers.

These tests never touch the network. They exercise normalisation, analysis
parsing and span extraction on small synthetic documents that mirror the BOE
XML shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "g0c"))

from probe_parse import (  # noqa: E402
    extract_between,
    extract_heading_block,
    find,
    join_span,
    normalize,
    parse_root,
)

SYNTHETIC = """<?xml version="1.0" encoding="UTF-8"?>
<documento fecha_actualizacion="20260101000000">
  <metadatos>
    <identificador>BOE-A-TEST-0001</identificador>
    <fecha_publicacion>20200102</fecha_publicacion>
    <fecha_vigencia>20200103</fecha_vigencia>
    <estado_consolidacion codigo="0"/>
  </metadatos>
  <analisis>
    <referencias>
      <anteriores>
        <anterior referencia="BOE-A-OLD"><palabra codigo="210">DEROGA</palabra>
          <texto>la norma anterior</texto></anterior>
      </anteriores>
      <posteriores>
        <posterior referencia="BOE-A-NEW"><palabra codigo="270">SE MODIFICA</palabra>
          <texto>la norma 4, por otra circular</texto></posterior>
      </posteriores>
    </referencias>
  </analisis>
  <texto>
    <p class="articulo">Norma 4. Otra informaci&#243;n.</p>
    <p class="parrafo">1.&#160;Primer apartado.</p>
    <p class="parrafo">2.&#160;Segundo apartado.</p>
    <p class="articulo">Norma 5. Siguiente.</p>
    <p class="parrafo">3. Texto de la norma 5.</p>
  </texto>
</documento>
"""


def _doc():
    import xml.etree.ElementTree as ET

    return parse_root(ET.fromstring(SYNTHETIC), "synthetic")


def test_normalize_collapses_nbsp_and_whitespace():
    assert normalize("  a\u00a0\u00a0b\n c  ") == "a b c"


def test_metadata_and_analysis_are_parsed():
    doc = _doc()
    assert doc.metadata["identificador"] == "BOE-A-TEST-0001"
    assert doc.metadata["fecha_vigencia"] == "20200103"
    assert doc.metadata["estado_consolidacion"] == "0"
    assert [r.referencia for r in doc.posteriores] == ["BOE-A-NEW"]
    assert doc.posteriores[0].palabra == "SE MODIFICA"
    assert doc.posteriores[0].palabra_codigo == "270"
    assert doc.anteriores[0].referencia == "BOE-A-OLD"


def test_heading_block_extraction():
    doc = _doc()
    text, span = extract_heading_block(doc.paragraphs, r"^Norma 4\.", r"^Norma 5\.", cls="articulo")
    assert text.startswith("Norma 4.")
    assert "Segundo apartado." in text
    assert "Norma 5." not in text
    assert span == {"start_index": 0, "stop_index": 3}


def test_extract_between_excludes_the_locator_line():
    doc = _doc()
    text, _ = extract_between(doc.paragraphs, r"^Norma 4\.", r"^Norma 5\.")
    assert text == "1. Primer apartado.\n2. Segundo apartado."


def test_find_and_join_span():
    doc = _doc()
    assert find(doc.paragraphs, r"^3\.\s") == 4
    assert join_span(doc.paragraphs, 0, 2) == "Norma 4. Otra información.\n1. Primer apartado."


def test_extract_between_missing_pattern_raises():
    doc = _doc()
    with pytest.raises(LookupError):
        extract_between(doc.paragraphs, r"^DOES NOT EXIST", r"^Norma 5\.")
