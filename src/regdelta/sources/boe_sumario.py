from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from ..util import canonical_date

COMPLETE = "COMPLETE"
INVALID_STRUCTURE = "INVALID_STRUCTURE"

PARSER_NAME = "boe_sumario"
PARSER_VERSION = "v1"


@dataclass
class ParseResult:
    parse_status: str
    parse_error: str | None
    source_date: str | None
    items: list = field(default_factory=list)


@dataclass(frozen=True)
class SumarioItem:
    identificador: str
    titulo: str
    control: str | None
    url_xml: str | None
    url_html: str | None
    url_pdf: str | None
    seccion_codigo: str
    seccion_nombre: str
    departamento_codigo: str
    departamento_nombre: str
    epigrafe: str
    fecha_sumario: str


def _invalid(message: str) -> ParseResult:
    return ParseResult(INVALID_STRUCTURE, message, None, [])


def is_bde_departamento(codigo: str, nombre: str) -> bool:
    return codigo == "1020" or "BANCO DE ESPA" in nombre.upper()


def parse_sumario(body: bytes, requested_date: str) -> ParseResult:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        return _invalid(f"xml parse error: {exc}")

    if root.tag != "response":
        return _invalid(f"root tag is {root.tag!r}, expected 'response'")

    code_el = root.find("./status/code")
    if code_el is not None and code_el.text is not None and code_el.text.strip() != "200":
        return _invalid(f"api status code {code_el.text.strip()}")

    sumario = root.find("./data/sumario")
    if sumario is None:
        return _invalid("data/sumario node missing")

    meta = sumario.find("./metadatos")
    if meta is None:
        return _invalid("metadatos node missing")

    raw_date = meta.findtext("fecha_publicacion")
    source_date = canonical_date(raw_date) if raw_date else None
    if source_date is None:
        return _invalid("fecha_publicacion missing or invalid")
    if source_date != requested_date:
        return _invalid(f"sumario date {source_date} != requested {requested_date}")

    secciones = list(sumario.iter("seccion"))
    if not secciones:
        return _invalid("no seccion nodes")

    items: list[SumarioItem] = []
    for seccion in secciones:
        seccion_codigo = seccion.get("codigo")
        seccion_nombre = seccion.get("nombre")
        if not seccion_codigo or not seccion_nombre:
            return _invalid("seccion missing codigo or nombre")
        for departamento in seccion.findall("departamento"):
            dept_codigo = departamento.get("codigo") or ""
            dept_nombre = departamento.get("nombre") or ""
            if not dept_nombre:
                return _invalid("departamento missing nombre")
            if not is_bde_departamento(dept_codigo, dept_nombre):
                continue
            parents = {}
            parents = {child: parent for parent in departamento.iter() for child in parent}
            for item in departamento.iter("item"):
                identificador = (item.findtext("identificador") or "").strip()
                titulo = (item.findtext("titulo") or "").strip()
                if not identificador or not titulo:
                    return _invalid("item missing identificador or titulo")
                epigrafe_el = parents.get(item)
                epigrafe = epigrafe_el.get("nombre") or "" if epigrafe_el is not None else ""
                items.append(
                    SumarioItem(
                        identificador=identificador,
                        titulo=titulo,
                        control=(item.findtext("control") or "").strip() or None,
                        url_xml=item.findtext("url_xml"),
                        url_html=item.findtext("url_html"),
                        url_pdf=item.findtext("url_pdf"),
                        seccion_codigo=seccion_codigo,
                        seccion_nombre=seccion_nombre,
                        departamento_codigo=dept_codigo,
                        departamento_nombre=dept_nombre,
                        epigrafe=epigrafe,
                        fecha_sumario=source_date,
                    )
                )
    return ParseResult(COMPLETE, None, source_date, items)
