from __future__ import annotations

from regdelta.sources import bde_consultas
from conftest import load


def parse_fixture():
    return bde_consultas.parse_consultas(load("bde_pi.html"), None)


def test_fixture_completes_with_three_entries():
    result = parse_fixture()
    assert result.parse_status == bde_consultas.COMPLETE
    assert len(result.entries) == 3


def test_dates_extracted_from_html():
    entries = parse_fixture().entries
    contables = [e for e in entries if "contables" in e.title_raw][0]
    cir = [e for e in entries if "(CIR)" in e.title_raw][0]
    reporte = [e for e in entries if "información financiera y prudencial" in e.title_raw][0]
    assert (contables.published_on, contables.consultation_end_on) == ("2026-09-04", "2026-09-25")
    assert (cir.published_on, cir.consultation_end_on) == ("2026-06-08", "2026-06-29")
    assert (reporte.published_on, reporte.consultation_end_on) == ("2026-06-08", "2026-06-29")


def test_diacritics_preserved_in_title_raw():
    reporte = [e for e in parse_fixture().entries if "información" in e.title_raw]
    assert reporte, "diacritics must survive decoding"


def test_pdf_classification():
    entries = parse_fixture().entries
    contables = [e for e in entries if "contables" in e.title_raw][0]
    reporte = [e for e in entries if "información financiera y prudencial" in e.title_raw][0]
    assert len(contables.anuncio_pdf_urls) == 1
    assert any("Anuncio_0426.pdf" in u for u in contables.anuncio_pdf_urls)
    assert any("Proyecto_0426.pdf" in u for u in contables.project_pdf_urls)
    assert any("Anuncio_Proyecto_CBE_Reporte.pdf" in u for u in reporte.anuncio_pdf_urls)
    assert any("Proyecto_CBE_Reporte.pdf" in u for u in reporte.project_pdf_urls)
    assert any("Anejo-Proyecto_CBE_Reporte.pdf" in u for u in reporte.other_document_urls)


def test_shell_without_table_is_invalid():
    result = bde_consultas.parse_consultas(b"<html><body>anti-bot shell</body></html>", None)
    assert result.parse_status == bde_consultas.INVALID_STRUCTURE


def test_wrong_headers_are_invalid():
    body = (
        b"<html><table><tr><th>Otra</th><th>Tabla</th></tr>"
        b"<tr><td><strong>X</strong></td><td>01/01/2026</td><td>02/01/2026</td></tr></table></html>"
    )
    result = bde_consultas.parse_consultas(body, None)
    assert result.parse_status == bde_consultas.INVALID_STRUCTURE
