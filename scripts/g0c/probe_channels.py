"""G0-C discovery: capture every reasonable official channel as raw evidence.

Run:  python scripts/g0c/probe_channels.py

This performs GET requests only and writes bytes + a SHA-256 manifest to
``evidence/g0c/raw/``. It intentionally captures HTTP failures (e.g. the
consolidated-legislation API 404s) because the failure is evidence for the
channel comparison.
"""

from __future__ import annotations

from probe_common import (
    ACCEPT_HTML,
    ACCEPT_PDF,
    ACCEPT_XML,
    capture,
)

# --- Channel A: original BOE publication of Circular 4/2017 -------------------
PUBLICATION_URLS = [
    # official BOE "documento" viewer (buscar/doc.php)
    ("boe_doc_html__BOE-A-2017-14334",
     "https://www.boe.es/buscar/doc.php?id=BOE-A-2017-14334", ACCEPT_HTML, "html"),
    # structured official XML of the daily publication (diario_boe)
    ("boe_diario_xml__BOE-A-2017-14334",
     "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2017-14334", ACCEPT_XML, "xml"),
    # HTML rendering of the daily publication text
    ("boe_diario_txt_html__BOE-A-2017-14334",
     "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2017-14334", ACCEPT_HTML, "html"),
    # official PDF of the daily publication (large; structured XML preferred)
    ("boe_dias_pdf__BOE-A-2017-14334",
     "https://www.boe.es/boe/dias/2017/12/06/pdfs/BOE-A-2017-14334.pdf", ACCEPT_PDF, "pdf"),
]

# --- Channel B: ELI representations -------------------------------------------
ELI_URLS = [
    ("boe_eli_html__C4-2017",
     "https://www.boe.es/eli/es/cir/2017/11/27/4", ACCEPT_HTML, "html"),
    ("boe_eli_dof_html__C4-2017",
     "https://www.boe.es/eli/es/cir/2017/11/27/4/dof", ACCEPT_HTML, "html"),
    ("boe_eli_dof_spa_xml__C4-2017",
     "https://www.boe.es/eli/es/cir/2017/11/27/4/dof/spa/xml", ACCEPT_XML, "xml"),
    ("boe_eli_dof_spa_html__C4-2017",
     "https://www.boe.es/eli/es/cir/2017/11/27/4/dof/spa/html", ACCEPT_HTML, "html"),
    ("boe_eli_corrigendum_html__C4-2017",
     "https://www.boe.es/eli/es/cir/2017/11/27/4/corrigendum/20180215/dof", ACCEPT_HTML, "html"),
]

# --- Channel E: official BOE analysis API (negative evidence + control) -------
# These are the endpoints that G0-A/B recorded as unavailable. Capturing them
# keeps the negative result reproducible.
ANALYSIS_API_URLS = []
# Negative evidence: instruments absent from the consolidated collection.
for _id in ("BOE-A-2017-14334", "BOE-A-2025-26847", "BOE-A-2023-5481"):
    for _suffix, _name in (
        ("/metadatos", "metadatos"),
        ("/analisis", "analisis"),
        ("/texto/indice", "texto_indice"),
    ):
        ANALYSIS_API_URLS.append(
            (
                f"boe_api_consolidada_{_name}__{_id}",
                f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{_id}{_suffix}",
                ACCEPT_XML,
                "xml",
            )
        )
# Positive controls: two BdE circulars that ARE in the consolidated collection
# (estado_consolidacion = 3 "Finalizado").
for _id in ("BOE-A-2020-6187", "BOE-A-2020-15602"):
    for _suffix, _name in (
        ("/metadatos", "metadatos"),
        ("/analisis", "analisis"),
        ("/texto/indice", "texto_indice"),
    ):
        ANALYSIS_API_URLS.append(
            (
                f"boe_api_consolidada_{_name}__{_id}",
                f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{_id}{_suffix}",
                ACCEPT_XML,
                "xml",
            )
        )

# --- Channel D/E: modifier instruments declared in the analysis ----------------
MODIFIER_IDS = [
    "BOE-A-2018-2041",   # Corrección de errores (15-02-2018)
    "BOE-A-2018-17880",  # Circular de 21-12-2018
    "BOE-A-2020-6186",   # Circular 2/2020
    "BOE-A-2020-6187",   # Circular 3/2020
    "BOE-A-2020-15602",  # Circular de 25-11-2020
    "BOE-A-2021-21666",  # Circular 6/2021
    "BOE-A-2023-5481",   # Circular 1/2023
    "BOE-A-2025-26847",  # Circular 1/2025
]
MODIFIER_URLS = [
    (
        f"boe_diario_xml__{mid}",
        f"https://www.boe.es/diario_boe/xml.php?id={mid}",
        ACCEPT_XML,
        "xml",
    )
    for mid in MODIFIER_IDS
]

# --- Secondary target: Circular 1/2025 publication itself ----------------------
CIR1_2025_URLS = [
    ("boe_doc_html__BOE-A-2025-26847",
     "https://www.boe.es/buscar/doc.php?id=BOE-A-2025-26847", ACCEPT_HTML, "html"),
    ("boe_eli_html__C1-2025",
     "https://www.boe.es/eli/es/cir/2025/12/19/1", ACCEPT_HTML, "html"),
]

# HTML consolidated view for a positive-control modifier (act.php, not doc.php).
CONSOLIDATION_CONTROL_URLS = [
    ("boe_buscar_act_html__BOE-A-2020-6187",
     "https://www.boe.es/buscar/act.php?id=BOE-A-2020-6187", ACCEPT_HTML, "html"),
]

ALL_CAPTURES = (
    PUBLICATION_URLS + ELI_URLS + ANALYSIS_API_URLS + MODIFIER_URLS
    + CIR1_2025_URLS + CONSOLIDATION_CONTROL_URLS
)


def main() -> None:
    for name, url, accept, extension in ALL_CAPTURES:
        entry = capture(name, url, accept, extension)
        print(
            f"{entry['http_status']!s:>5}  {entry['size_bytes']:>10}  "
            f"{str(entry['sha256'])[:16]}  {name}"
        )


if __name__ == "__main__":
    main()
