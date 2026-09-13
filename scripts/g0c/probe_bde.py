"""G0-C discovery: capture complementary Banco de España (BdE) sources.

Run:  python scripts/g0c/probe_bde.py

BdE is treated as a complementary channel only. Two BdE surfaces are captured:

* the chronological index of Banco de España circulars (discovery aid);
* the "Consulta de Legislación Financiera" (CLF, app.bde.es/clf_www) which
  renders a text adapted to the modifications in force, i.e. a BdE-maintained
  consolidated view;
* the reporting-templates page for Circular 4/2017.
"""

from __future__ import annotations

import re

from probe_common import ACCEPT_HTML, RAW_DIR, capture, read_raw_text

BDE_URLS = [
    ("bde_indice_cronologico_circulares",
     "https://www.bde.es/wbe/es/areas-actuacion/normativa/circulares-banco-de-espana/circulares-banco-espana-indice-cronologico/",
     ACCEPT_HTML, "html"),
    ("bde_clf_leyes_art__163763",
     "https://app.bde.es/clf_www/leyes.jsp?normaAFecha=S&id=163651&idart=163763&fc=13-09-2026&mh=1",
     ACCEPT_HTML, "html"),
    ("bde_info_banco_espana_c4_2017",
     "https://www.bde.es/wbe/es/punto-informacion/contenidos/informacion-financiera-a-remitir-entidades-supervisadas/entidades-credito/informacion-periodica-entidades-credito/contabilidad/informacion-al-banco-espana/",
     ACCEPT_HTML, "html"),
    # "Norma completa" (current consolidated view maintained by BdE, adapted text)
    ("bde_clf_norma_completa__163651__current",
     "https://app.bde.es/clf_www/leyes.jsp?id=163651&fc=13-09-2026&tipoEnt=0",
     ACCEPT_HTML, "html"),
    # "Norma a una Fecha" at 2018-01-01 -> BdE internal error (no historical version)
    ("bde_clf_norma_a_fecha__163651__2018-01-01",
     "https://app.bde.es/clf_www/leyes.jsp?id=163651&fc=01-01-2018&tipoEnt=0",
     ACCEPT_HTML, "html"),
    # previous version link for anejo 6 (fc just before Circular 1/2025 in force)
    ("bde_clf_art_prev__163763__2025-12-29",
     "https://app.bde.es/clf_www/leyes.jsp?normaAFecha=S&id=163651&idart=163763&fc=29-12-2025&mh=1",
     ACCEPT_HTML, "html"),
]


def main() -> None:
    for name, url, accept, extension in BDE_URLS:
        entry = capture(name, url, accept, extension)
        print(f"{entry['http_status']!s:>5}  {entry['size_bytes']:>10}  {name}")

    # Light structural probe of the CLF article page (no interpretation).
    html = read_raw_text("bde_clf_leyes_art__163763")
    links = sorted(set(re.findall(r'(leyes\.jsp\?[^"\']+)', html)))
    print("\nCLF links discovered:", len(links))
    for link in links[:40]:
        print("  ", link[:160])


if __name__ == "__main__":
    main()
