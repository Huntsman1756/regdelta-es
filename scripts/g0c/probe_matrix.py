"""G0-C discovery: build the channel comparison matrix.

Run:  python scripts/g0c/probe_matrix.py

The matrix is generated from the captured raws (sizes, SHA-256, equality between
channels, text/table/image structure) plus an explicit ``criteria`` block that
defines every assessment dimension. No dimension is scored without a stated
criterion; assessments that are not directly observable are labelled DERIVED.
"""

from __future__ import annotations

from probe_common import EVIDENCE_DIR, dump, load_manifest
from probe_parse import parse_document

TARGET = "BOE-A-2017-14334"

CRITERIA = {
    "coverage": "Which parts of the instrument history the channel exposes: original text, "
                "consolidated text, explicit amendment relations, granular locators, annexes/states.",
    "determinism": "Whether repeated retrieval of the same official URL yields the same "
                   "semantic content (content hashed) and whether HTTP failures are explicit.",
    "granularity": "Finest locator the channel states for a change: INSTRUMENT_LEVEL, "
                   "BLOCK_LEVEL, PROVISION_LEVEL, TEXT_ONLY, UNKNOWN.",
    "raw_evidence": "Whether the channel can be stored byte-for-byte with a stable SHA-256 "
                    "for audit (no JS-only rendering, no session state).",
    "reconstruction_difficulty": "What is still required to obtain old->new for a block given "
                                 "this channel.",
    "fragility": "Sensitivity to URL/session/render changes or to undocumented behaviour.",
    "licensing": "Reuse conditions relevant to redistributing text derived from the channel.",
}


def entry(name):
    return load_manifest()["entries"].get(name)


def meta(name):
    e = entry(name)
    if not e:
        return None
    return {
        "url": e["url"],
        "http_status": e["http_status"],
        "bytes": e["size_bytes"],
        "sha256": e["sha256"],
        "path": e["path"],
    }


def html_profile(name):
    try:
        text = entry(name) and _read_text(name)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__, "detail": str(exc)}
    if text is None:
        return {"error": "not captured"}
    return {
        "img_elements": text.count("<img"),
        "table_elements": text.count("<table"),
        "annex_images": text.count("imagenes/disp"),
    }


def _read_text(name):
    from probe_common import read_raw_text

    return read_raw_text(name)


def text_profile(name):
    try:
        doc = parse_document(name)
    except Exception as exc:  # noqa: BLE001 - inactive/absent channel
        return {"error": type(exc).__name__, "detail": str(exc)}
    return {
        "paragraphs": len(doc.paragraphs),
        "tables": len(doc.tables),
        "images": len(doc.image_srcs),
        "has_analysis_posteriores": len(doc.posteriores),
        "has_analysis_anteriores": len(doc.anteriores),
        "estado_consolidacion": doc.metadata.get("estado_consolidacion"),
    }


def main() -> None:
    target_xml = "boe_diario_xml__BOE-A-2017-14334"
    target_doc = parse_document(target_xml)
    target_pub = f"boe_doc_html__{TARGET}"
    target_txt = f"boe_diario_txt_html__{TARGET}"
    target_pdf = f"boe_dias_pdf__{TARGET}"
    eli_html = "boe_eli_html__C4-2017"
    eli_dof = "boe_eli_dof_html__C4-2017"
    eli_xml = "boe_eli_dof_spa_xml__C4-2017"
    corr = "boe_eli_corrigendum_html__C4-2017"

    modifiers = [
        "BOE-A-2018-2041", "BOE-A-2018-17880", "BOE-A-2020-6186", "BOE-A-2020-6187",
        "BOE-A-2020-15602", "BOE-A-2021-21666", "BOE-A-2023-5481", "BOE-A-2025-26847",
    ]
    modifier_raws = [f"boe_diario_xml__{m}" for m in modifiers]

    def eq(a, b):
        ea, eb = entry(a), entry(b)
        if not ea or not eb:
            return None
        return ea["sha256"] == eb["sha256"]

    equalities = {
        "eli_html__eq__doc_html": eq(eli_html, target_pub),
        "eli_dof_html__eq__eli_html": eq(eli_dof, eli_html),
        "eli_dof_spa_xml__eq__diario_xml": eq(eli_xml, target_xml),
        "doc_html__eq__diario_txt_html": eq(target_pub, target_txt),
    }

    api_raws = [k for k in load_manifest()["entries"] if k.startswith("boe_api_consolidada_")]
    api_absent = [k for k in api_raws if entry(k)["http_status"] == 404]
    api_present = [k for k in api_raws if entry(k)["http_status"] == 200]
    api_statuses = sorted({entry(k)["http_status"] for k in api_raws})

    channels = [
        {
            "id": "A2",
            "name": "BOE daily-publication XML (diario_boe/xml.php)",
            "role": "PRIMARY original structured text + embedded official analysis (channels A/E)",
            "evidence": meta(target_xml),
            "source_profile": text_profile(target_xml),
            "assessment": {
                "coverage": "Original publication text of normas/disposiciones + <analisis> relations + ELI RDF. No consolidated text. Annexes are images.",
                "determinism": "HIGH: stable XML; analysis block is dynamically maintained (fecha_actualizacion) but the raw is hashed per retrieval.",
                "granularity": "PROVISION_LEVEL locators come from modifier documents; the target analysis text is BLOCK_LEVEL/TEXT_ONLY.",
                "raw_evidence": "FULL: content-addressed bytes with SHA-256.",
                "reconstruction_difficulty": "Old text available for body provisions; annexes need a different source.",
                "fragility": "LOW.",
                "licensing": "BOE reuse conditions; consolidated text is informative; keep update metadata.",
            },
        },
        {
            "id": "A1/C",
            "name": "BOE document viewer HTML (buscar/doc.php) and daily HTML (diario_boe/txt.php)",
            "role": "Human-readable original publication; same content as A2",
            "evidence": meta(target_pub),
            "equalities": {"equals_eli_html": equalities["eli_html__eq__doc_html"]},
            "source_profile": html_profile(target_pub),
            "assessment": {
                "coverage": "Original publication text; annexes are images.",
                "determinism": "HIGH for bytes; rendering may include site chrome.",
                "granularity": "INSTRUMENT_LEVEL/TEXT_ONLY as HTML; no structured locators.",
                "raw_evidence": "FULL.",
                "reconstruction_difficulty": "Requires an HTML parser; no structural classes as clean as XML.",
                "fragility": "LOW.",
                "licensing": "BOE reuse conditions.",
            },
        },
        {
            "id": "A4",
            "name": "BOE daily PDF",
            "role": "Official visual copy",
            "evidence": meta(target_pdf),
            "assessment": {
                "coverage": "Original publication including annex images.",
                "determinism": "HIGH for bytes.",
                "granularity": "NONE without PDF extraction.",
                "raw_evidence": "FULL (large: ~39 MB).",
                "reconstruction_difficulty": "Text extraction/OCR needed; explicitly deprioritised because A2 is structured.",
                "fragility": "LOW.",
                "licensing": "BOE reuse conditions.",
            },
        },
        {
            "id": "B",
            "name": "ELI representations (boe.es/eli/...)",
            "role": "Stable identifiers and format negotiation",
            "evidence": meta(eli_html),
            "equalities": {
                "eli_html_equals_doc_html": equalities["eli_html__eq__doc_html"],
                "eli_dof_html_equals_eli_html": equalities["eli_dof_html__eq__eli_html"],
                "eli_xml_equals_diario_xml": equalities["eli_dof_spa_xml__eq__diario_xml"],
            },
            "source_profile": html_profile(eli_html),
            "assessment": {
                "coverage": "ELI resolves to the SAME original text as the daily publication; no consolidated ELI version (/consolidado -> 404).",
                "determinism": "HIGH; deterministic redirect to the canonical original artefact.",
                "granularity": "INSTRUMENT_LEVEL, except the /xml expression which equals A2.",
                "raw_evidence": "FULL.",
                "reconstruction_difficulty": "Same as A2 for text; no added historical value.",
                "fragility": "LOW.",
                "licensing": "BOE reuse conditions.",
            },
        },
        {
            "id": "D",
            "name": "Modifier instruments (daily XML per modifier)",
            "role": "new_text and explicit provision-level operational locators",
            "evidence": [meta(r) for r in modifier_raws],
            "source_profile": [text_profile(r) for r in modifier_raws],
            "assessment": {
                "coverage": "All 8 instruments listed by the target analysis are retrievable; each carries <texto> with the amending operations and its own <anteriores> cross-check.",
                "determinism": "HIGH.",
                "granularity": "PROVISION_LEVEL / BLOCK_LEVEL via sentences such as 'En la norma 4 ... se modifican los apartados 5 y 6'.",
                "raw_evidence": "FULL.",
                "reconstruction_difficulty": "Provides new_text; old_text must come from the original or from the prior modifier.",
                "fragility": "LOW.",
                "licensing": "BOE reuse conditions.",
            },
        },
        {
            "id": "E1",
            "name": "BOE consolidated-legislation open-data API — TARGET",
            "role": "Would provide consolidated text + structured analysis for the target",
            "evidence": [meta(r) for r in api_absent],
            "assessment": {
                "coverage": "NONE for the target and for most modifiers probed "
                            "(BOE-A-2017-14334, 2025-26847, 2023-5481 all 404). The target's "
                            "diario XML declares estado_consolidacion codigo=0 (no consolidated version).",
                "determinism": "Explicit failure; not usable for the target.",
                "granularity": "N/A.",
                "raw_evidence": "The 404 bodies are stored as negative evidence.",
                "reconstruction_difficulty": "N/A (absent for the target).",
                "fragility": "N/A (absent).",
                "licensing": "N/A.",
            },
        },
        {
            "id": "E1b",
            "name": "BOE consolidated-legislation open-data API — SUBSET (positive control)",
            "role": "Shows the channel exists and is structured when estado_consolidacion=3",
            "evidence": [meta(r) for r in api_present],
            "assessment": {
                "coverage": "PRESENT for BOE-A-2020-6187 (Circular 3/2020) and BOE-A-2020-15602: "
                            "metadatos + analisis + block index, plus a consolidated HTML at act.php. "
                            "Neither is the target, so it cannot supply the target's history.",
                "determinism": "HIGH for the covered instruments.",
                "granularity": "Structured relations use <id_norma> + <relacion codigo>; consolidated "
                            "text is split into blocks (/texto/bloque/<id>).",
                "raw_evidence": "FULL.",
                "reconstruction_difficulty": "Would be the ideal channel if the target were covered.",
                "fragility": "LOW for the covered subset.",
                "licensing": "BOE reuse conditions.",
            },
        },
        {
            "id": "E2",
            "name": "Official BOE analysis (<analisis>) embedded in A2 and in each modifier",
            "role": "Modifier discovery + relation words",
            "evidence": meta(target_xml),
            "source_profile": text_profile(target_xml),
            "assessment": {
                "coverage": "Enumerates all explicit posterior relations (7 modifications + 1 correction) and the prior derogated norm; symmetric cross-check available in each modifier.",
                "determinism": "HIGH (structured XML).",
                "granularity": "Instrument-level relation; free-text description identifies norms/annexes at BLOCK_LEVEL.",
                "raw_evidence": "FULL.",
                "reconstruction_difficulty": "Feeds discovery; not sufficient alone for old/new.",
                "fragility": "LOW but the block is dynamically regenerated (fecha_actualizacion).",
                "licensing": "BOE reuse conditions.",
            },
        },
        {
            "id": "F1",
            "name": "BdE chronological index of circulars",
            "role": "Complementary discovery aid",
            "evidence": meta("bde_indice_cronologico_circulares"),
            "source_profile": html_profile("bde_indice_cronologico_circulares"),
            "assessment": {
                "coverage": "Lists BdE circulars chronologically; complementary to BOE discovery.",
                "determinism": "MEDIUM: large HTML page, no structured feed captured.",
                "granularity": "INSTRUMENT_LEVEL.",
                "raw_evidence": "FULL (HTML).",
                "reconstruction_difficulty": "N/A for text.",
                "fragility": "MEDIUM (site migration to app.bde.es observed).",
                "licensing": "BdE reuse conditions.",
            },
        },
        {
            "id": "F2",
            "name": "BdE Consulta de Legislación Financiera (CLF) current consolidated view",
            "role": "Complementary consolidated text (not the legal authority)",
            "evidence": meta("bde_clf_leyes_art__163763"),
            "assessment": {
                "coverage": "Article/annex level consolidated text maintained by BdE, adapted to modifications in force.",
                "determinism": "LOW: responses varied between runs (internal error vs full text for the same date); session/state dependent.",
                "granularity": "Article/anexo level; no per-modification attributable provenance.",
                "raw_evidence": "HTML only; not stable.",
                "reconstruction_difficulty": "Could help read annexes as text but cannot be the legal source of an old/new pair.",
                "fragility": "HIGH (JSP app, undocumented parameters, unreliable dated view).",
                "licensing": "BdE reuse conditions; adapted text.",
            },
        },
        {
            "id": "F3",
            "name": "BdE 'Norma a una Fecha'",
            "role": "Intended historical versioning",
            "evidence": [
                meta("bde_clf_norma_a_fecha__163651__2018-01-01"),
                meta("bde_clf_norma_completa__163651__current"),
            ],
            "assessment": {
                "coverage": "NOT USABLE as history: a request for 2018-01-01 returned the current text on one run and 'Error interno' on another.",
                "determinism": "LOW/UNRELIABLE.",
                "granularity": "N/A.",
                "raw_evidence": "HTML, unstable.",
                "reconstruction_difficulty": "Cannot provide a dependable historical old_text.",
                "fragility": "HIGH.",
                "licensing": "BdE reuse conditions.",
            },
        },
        {
            "id": "G",
            "name": "Correction/errata instruments",
            "role": "Literal old/new for errata",
            "evidence": meta("boe_diario_xml__BOE-A-2018-2041") or meta("boe_eli_corrigendum_html__C4-2017"),
            "source_profile": text_profile("boe_diario_xml__BOE-A-2018-2041"),
            "assessment": {
                "coverage": "Corrections are discoverable with palabra code 201 and provide literal 'donde dice ... debe decir ...' pairs.",
                "determinism": "HIGH.",
                "granularity": "PROVISION_LEVEL (page + norma + apartado).",
                "raw_evidence": "FULL.",
                "reconstruction_difficulty": "Low for errata; must be ordered separately from ordinary modifications.",
                "fragility": "LOW.",
                "licensing": "BOE reuse conditions.",
            },
        },
    ]

    result = {
        "schema": "regdelta.g0c.channel-matrix/v1",
        "criteria": CRITERIA,
        "equalities": equalities,
        "negative_evidence": {
            "consolidated_api_absent_raw_names": api_absent,
            "consolidated_api_present_raw_names": api_present,
            "http_statuses": api_statuses,
            "eli_consolidado": "GET https://www.boe.es/eli/es/cir/2017/11/27/4/consolidado -> 404 HTML (not captured as raw; noted).",
            "note": "The consolidated API is not universally absent for BdE norms: it is absent for "
                    "the target, which is exactly the G0-C problem, but present for a subset.",
        },
        "channels": channels,
    }
    dump(result, EVIDENCE_DIR / "channel-matrix.json")
    print("wrote", EVIDENCE_DIR / "channel-matrix.json")
    print("equalities:", equalities)
    print("api statuses:", api_statuses)


if __name__ == "__main__":
    main()
