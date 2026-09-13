from __future__ import annotations

import pytest

from regdelta.sources import boe_sumario
from conftest import load


def test_sum_20251229_completes_with_26847():
    result = boe_sumario.parse_sumario(load("sum_20251229.xml"), "2025-12-29")
    assert result.parse_status == boe_sumario.COMPLETE
    assert result.source_date == "2025-12-29"
    ids = {item.identificador: item for item in result.items}
    assert "BOE-A-2025-26847" in ids
    item = ids["BOE-A-2025-26847"]
    assert item.seccion_codigo == "1"
    assert item.departamento_codigo == "1020"
    assert "Circular 1/2025" in item.titulo
    assert item.fecha_sumario == "2025-12-29"


def test_sum_20171206_captures_two_sections():
    result = boe_sumario.parse_sumario(load("sum_20171206.xml"), "2017-12-06")
    assert result.parse_status == boe_sumario.COMPLETE
    by_id = {item.identificador: item for item in result.items}
    assert by_id["BOE-A-2017-14334"].seccion_codigo == "1"
    assert by_id["BOE-A-2017-14370"].seccion_codigo == "3"


def test_sum_20260912_captures_section_three():
    result = boe_sumario.parse_sumario(load("sum_20260912.xml"), "2026-09-12")
    assert result.parse_status == boe_sumario.COMPLETE
    by_id = {item.identificador: item for item in result.items}
    assert by_id["BOE-A-2026-19113"].seccion_codigo == "3"


def test_requested_date_mismatch_is_rejected():
    result = boe_sumario.parse_sumario(load("sum_20251229.xml"), "2020-01-01")
    assert result.parse_status == boe_sumario.INVALID_STRUCTURE
    assert "requested" in result.parse_error


def test_non_xml_is_rejected():
    result = boe_sumario.parse_sumario(b"this is not xml", "2025-12-29")
    assert result.parse_status == boe_sumario.INVALID_STRUCTURE


def test_missing_sumario_node_is_rejected():
    body = b"<?xml version='1.0'?><response><status><code>200</code></status><data/></response>"
    result = boe_sumario.parse_sumario(body, "2025-12-29")
    assert result.parse_status == boe_sumario.INVALID_STRUCTURE
