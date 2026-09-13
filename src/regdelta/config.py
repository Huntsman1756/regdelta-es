from __future__ import annotations

from dataclasses import dataclass

BOE_SUMARIO_URL_TEMPLATE = "https://www.boe.es/datosabiertos/api/boe/sumario/{yyyymmdd}"
BDE_CONSULTAS_URL = "https://www.bde.es/wbe/es/punto-informacion/contenidos/consultas-publicas/"

ACCEPT_XML = "application/xml"
ACCEPT_HTML = "text/html"


@dataclass(frozen=True)
class Source:
    source_id: str


BOE_SUMARIO = Source("boe_sumario")
BDE_CONSULTAS = Source("bde_consultas")


def boe_sumario_url(date_iso: str) -> str:
    compact = date_iso.replace("-", "")
    return BOE_SUMARIO_URL_TEMPLATE.format(yyyymmdd=compact)
