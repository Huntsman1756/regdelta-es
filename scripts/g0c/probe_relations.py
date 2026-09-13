"""G0-C discovery: modifier discovery from official BOE analysis.

Run:  python scripts/g0c/probe_relations.py

Discovery question 1: is there a deterministic, non-manual method to obtain the
explicit modifications of Circular 4/2017?

Channel used: the official daily-publication XML
``https://www.boe.es/diario_boe/xml.php?id=BOE-A-2017-14334`` exposes
``<analisis><referencias><posteriores>``. Each ``<posterior>`` carries the
instrument identifier, the relation word (``<palabra>``) and a free-text
description. The modifier instrument itself can be fetched and its own
``<anteriores>`` re-read, giving a symmetric cross-check.

Output: evidence/g0c/modifiers.json
"""

from __future__ import annotations

from probe_common import EVIDENCE_DIR, dump, load_manifest
from probe_parse import parse_document

TARGET_ID = "BOE-A-2017-14334"
TARGET_RAW = f"boe_diario_xml__{TARGET_ID}"
DIARIO_XML_URL = "https://www.boe.es/diario_boe/xml.php?id={id}"


def _raw_sha(name: str) -> str | None:
    entry = load_manifest()["entries"].get(name)
    return entry["sha256"] if entry else None


def main() -> None:
    manifest = load_manifest()["entries"]
    target = parse_document(TARGET_RAW)

    modifiers = []
    for ref in target.posteriores:
        mid = ref.referencia
        raw_name = f"boe_diario_xml__{mid}"
        kind = "CORRECTION" if "CORRECCI" in ref.palabra.upper() else "MODIFICATION"
        entry: dict = {
            "modifier_instrument": mid,
            "kind": kind,
            "relation_raw": {
                "palabra": ref.palabra,
                "palabra_codigo": ref.palabra_codigo,
                "descripcion_texto": ref.texto,
            },
            "declared_by": "OBSERVED: target <analisis><referencias><posteriores>",
            "modifier_xml_url": DIARIO_XML_URL.format(id=mid),
            "modifier_publication_date": None,
            "modifier_effective_date": None,
            "modifier_title": None,
            "modifier_rango": None,
            "cross_check": None,
            "locators": [],
            "locator_count": 0,
            "evidence_raw_names": [TARGET_RAW],
            "evidence_raw_sha256": [_raw_sha(TARGET_RAW)],
        }
        if raw_name in manifest:
            doc = parse_document(raw_name)
            entry["modifier_publication_date"] = doc.metadata.get("fecha_publicacion")
            entry["modifier_effective_date"] = doc.metadata.get("fecha_vigencia")
            entry["modifier_title"] = doc.metadata.get("titulo")
            entry["modifier_rango"] = doc.metadata.get("rango")
            entry["locators"] = _locators(doc)
            entry["locator_count"] = len(entry["locators"])
            back = [
                r for r in doc.anteriores if r.referencia == TARGET_ID
            ]
            entry["cross_check"] = {
                "target_declared_as_anterior": bool(back),
                "relations": [
                    {"palabra": r.palabra, "palabra_codigo": r.palabra_codigo, "texto": r.texto}
                    for r in back
                ],
                "note": "DERIVED: symmetric relation read from the modifier's own <anteriores>.",
            }
            entry["evidence_raw_names"].append(raw_name)
            entry["evidence_raw_sha256"].append(_raw_sha(raw_name))
        modifiers.append(entry)

    result = {
        "schema": "regdelta.g0c.modifiers/v1",
        "target": {
            "instrument": TARGET_ID,
            "title": target.metadata.get("titulo"),
            "publication_date": target.metadata.get("fecha_publicacion"),
            "effective_date": target.metadata.get("fecha_vigencia"),
            "estado_consolidacion_codigo": target.metadata.get("estado_consolidacion"),
            "analysis_raw_name": TARGET_RAW,
            "analysis_raw_sha256": _raw_sha(TARGET_RAW),
        },
        "discovery_channel": (
            "OBSERVED: <analisis><referencias><posteriores> of "
            "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2017-14334"
        ),
        "modifiers": modifiers,
        "coverage_statement": (
            "OBSERVED: BOE's own analysis enumerates the explicit relationships "
            "recorded for the instrument. It cannot be independently proven "
            "exhaustive from a second official source without scanning every "
            "later norm; tacit legal effects are out of scope by construction."
        ),
    }
    dump(result, EVIDENCE_DIR / "modifiers.json")
    print(f"target posteriores: {len(target.posteriores)}")
    for m in modifiers:
        print(f"  {m['kind']:12s} {m['modifier_instrument']:20s} "
              f"pub={m['modifier_publication_date']} eff={m['modifier_effective_date']} "
              f"locators={m['locator_count']} cross={m['cross_check'] and m['cross_check']['target_declared_as_anterior']}")
    print("wrote", EVIDENCE_DIR / "modifiers.json")


def _locators(doc) -> list[str]:
    from probe_parse import locator_sentences

    return locator_sentences(doc.paragraphs)


if __name__ == "__main__":
    main()
