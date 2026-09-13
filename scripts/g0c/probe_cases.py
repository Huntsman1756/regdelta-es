"""G0-C discovery: build the experimental reconstruction cases.

Run:  python scripts/g0c/probe_cases.py

Six cases cover the required diversity:

1. article/norm substitution (Norma 33, BOE-A-2018-17880)
2. first textual modification of an annex (Anejo 9 point 46, BOE-A-2020-15602)
3. later modification of a previously modified block (Anejo 9 point 99:
   BOE-A-2018-17880 then BOE-A-2020-6187)
4. a Circular 1/2025 modification of Circular 4/2017 (Norma 19 apartado 10)
5. financial-statement state substitution (Anejo 4, estado FI 105, BOE-A-2025-26847)
6. an errata correction (BOE-A-2018-2041)

Every case records the old/new text sources, SHA-256 of the normalised spans,
the official evidence URLs and the SHA-256 of the captured raw documents.
``confidence`` is computed structurally (available text on both sides, chain
from a prior modifier, or image-only original) and never by a model.
"""

from __future__ import annotations

import re

from probe_common import EVIDENCE_DIR, dump, load_manifest, sha256_hex
from probe_parse import extract_between, find, join_span, parse_document

TARGET_RAW = "boe_diario_xml__BOE-A-2017-14334"
DIARIO_XML_URL = "https://www.boe.es/diario_boe/xml.php?id={id}"


def h(text: str | None) -> str | None:
    if text is None:
        return None
    return sha256_hex(text.encode("utf-8"))


def raw_sha(name: str) -> str | None:
    entry = load_manifest()["entries"].get(name)
    return entry["sha256"] if entry else None


def preview(text: str | None, limit: int = 300) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit] + " […]"


def base_case(case_id, modifier_id, kind, locator, relation_raw, method, confidence,
              target_locator_expr, old_text, new_text, old_source, new_source,
              old_category, extra_evidence=None):
    modifier_raw = f"boe_diario_xml__{modifier_id}"
    ev_names = [TARGET_RAW, modifier_raw]
    if extra_evidence:
        ev_names += extra_evidence
    return {
        "case_id": case_id,
        "target_instrument": "BOE-A-2017-14334",
        "modifier_instrument": modifier_id,
        "kind": kind,
        "target_locator": locator,
        "target_locator_expr": target_locator_expr,
        "relation_raw": relation_raw,
        "publication_date": None,
        "effective_date": None,
        "old_text_source": old_source,
        "new_text_source": new_source,
        "old_text_source_category": old_category,
        "old_text_available": old_text is not None,
        "new_text_available": new_text is not None,
        "old_text": old_text,
        "new_text": new_text,
        "old_text_preview": preview(old_text),
        "new_text_preview": preview(new_text),
        "old_text_length": len(old_text) if old_text is not None else 0,
        "new_text_length": len(new_text) if new_text is not None else 0,
        "old_text_sha256": h(old_text),
        "new_text_sha256": h(new_text),
        "hash_basis": "sha256(utf-8(normalised_text)); whitespace collapsed, U+00A0 -> space",
        "evidence_urls": [DIARIO_XML_URL.format(id="BOE-A-2017-14334"), DIARIO_XML_URL.format(id=modifier_id)],
        "evidence_raw_names": ev_names,
        "evidence_raw_sha256": [raw_sha(n) for n in ev_names],
        "reconstruction_method": method,
        "confidence": confidence,
        "evidence_class": "OBSERVED text spans + DERIVED confidence from source availability",
    }


def _relation(target, mid):
    for ref in target.posteriores:
        if ref.referencia == mid:
            return {"palabra": ref.palabra, "palabra_codigo": ref.palabra_codigo, "descripcion_texto": ref.texto}
    return None


def main() -> None:
    target = parse_document(TARGET_RAW)
    cases = []

    # ---- Case 1: Norma 33 substituted by BOE-A-2018-17880 ----
    mod = parse_document("boe_diario_xml__BOE-A-2018-17880")
    old, old_meta = _heading_block(target.paragraphs, r"^Norma 33\.", r"^Norma 34\.")
    new, new_meta = extract_between(mod.paragraphs, r"^h\)\s+La norma 33", r"^i\)\s+En la norma 34")
    c = base_case(
        "C1_norma33_substitution", "BOE-A-2018-17880", "MODIFICATION", "Norma 33",
        _relation(target, "BOE-A-2018-17880"),
        "DIRECT_SPAN_OLD_FROM_ORIGINAL_NEW_FROM_MODIFIER", "PROVEN",
        {"old_span": old_meta, "new_span": new_meta},
        old, new,
        "BOE-A-2017-14334 daily XML, body heading class='articulo' 'Norma 33.' -> next 'Norma 34.'",
        "BOE-A-2018-17880 daily XML, operation 'h) La norma 33 ... se sustituye' -> next operation",
        "A_TEXT_ON_BOTH_SIDES",
    )
    _dates(c, mod)
    cases.append(c)

    # ---- Case 2: Anejo 9, point 46 first textual modification ----
    mod = parse_document("boe_diario_xml__BOE-A-2020-15602")
    new, new_meta = extract_between(mod.paragraphs, r"^e\)\s+En el anejo 9", r"^f\)\s+En el anejo 9")
    c = base_case(
        "C2_anejo9_punto46_first_mod", "BOE-A-2020-15602", "MODIFICATION", "Anejo 9, punto 46",
        _relation(target, "BOE-A-2020-15602"),
        "NEW_TEXT_FROM_MODIFIER_OLD_IMAGE_ONLY", "PARTIAL",
        {"new_span": new_meta},
        None, new,
        "UNAVAILABLE: original Anejo 9 is published only as page images in the daily XML "
        f"({len(target.image_srcs)} <img> elements, 0 annex tables)",
        "BOE-A-2020-15602 daily XML, operation 'e) En el anejo 9 ... punto 46'",
        "D_IMAGE_ONLY_OLD",
    )
    _dates(c, mod)
    cases.append(c)

    # ---- Case 3: Anejo 9, point 99 modified twice (2018 then 2020) ----
    mod18 = parse_document("boe_diario_xml__BOE-A-2018-17880")
    mod20 = parse_document("boe_diario_xml__BOE-A-2020-6187")
    old, old_meta = extract_between(
        mod18.paragraphs,
        r"^iii\)\s+Se elimina el tercer párrafo del punto 99",
        r"^iv\)\s+Se modifica el punto 102",
    )
    new, new_meta = extract_between(mod20.paragraphs, r"^c\)\s+En el punto 99", r"^e\)\s+Se modifica el punto 100")
    c = base_case(
        "C3_anejo9_punto99_second_mod", "BOE-A-2020-6187", "MODIFICATION", "Anejo 9, punto 99",
        _relation(target, "BOE-A-2020-6187"),
        "CHAINED_OLD_EQ_PRIOR_MODIFIER_NEW_TEXT", "PROVEN",
        {"old_span_in_prior_modifier": old_meta, "new_span": new_meta},
        old, new,
        "BOE-A-2018-17880 new text for point 99 (the block as restated by the previous modifier); "
        "the pre-2018 original remains image-only",
        "BOE-A-2020-6187 daily XML, operation 'c) En el punto 99'",
        "B_CHAINED_FROM_PRIOR_NEW_TEXT",
        extra_evidence=["boe_diario_xml__BOE-A-2020-6187"],
    )
    _dates(c, mod20)
    cases.append(c)

    # ---- Case 4: Circular 1/2025, Norma 19 apartado 10 ----
    mod25 = parse_document("boe_diario_xml__BOE-A-2025-26847")
    i0 = find(target.paragraphs, r"^Norma 19\.", cls="articulo")
    i = find(target.paragraphs, r"^10\.\s", start=i0)
    j = find(target.paragraphs, r"^Norma 20\.", start=i, cls="articulo")
    old = join_span(target.paragraphs, i, j)
    new, new_meta = extract_between(mod25.paragraphs, r"^b\)\s+En la norma 19", r"^c\)\s+En la norma 22")
    c = base_case(
        "C4_cir1_2025_norma19_ap10", "BOE-A-2025-26847", "MODIFICATION", "Norma 19, apartado 10",
        _relation(target, "BOE-A-2025-26847"),
        "DIRECT_SPAN_OLD_FROM_ORIGINAL_NEW_FROM_MODIFIER", "PROVEN",
        {"old_span": {"start_index": i, "stop_index": j}, "new_span": new_meta},
        old, new,
        "BOE-A-2017-14334 daily XML, body 'Norma 19.' -> apartado '10.' -> next articulo 'Norma 20.'",
        "BOE-A-2025-26847 daily XML, operation 'b) En la norma 19 ... apartado 10'",
        "A_TEXT_ON_BOTH_SIDES",
    )
    _dates(c, mod25)
    cases.append(c)

    # ---- Case 5: Anejo 4, estado FI 105 substitution (image-bound old side) ----
    annex_tables = "\n\n".join(mod25.tables)
    c = base_case(
        "C5_estado_FI105_substitution", "BOE-A-2025-26847", "MODIFICATION", "Anejo 4, estado FI 105",
        _relation(target, "BOE-A-2025-26847"),
        "NEW_TEXT_STRUCTURED_TABLE_OLD_IMAGE_ONLY", "PARTIAL",
        {"new_tables_count": len(mod25.tables)},
        None, annex_tables,
        "UNAVAILABLE: original annexed states are page images with no text and no per-state label; "
        "the mapping image<->estado is not machine-readable",
        "BOE-A-2025-26847 daily XML, <table> elements of the annexed states (DERIVED mapping to FI 105)",
        "D_IMAGE_ONLY_OLD",
    )
    _dates(c, mod25)
    c["evidence_class"] = (
        "OBSERVED new tables; INFERRED/DERIVED table<->estado mapping; old_text NOT available"
    )
    cases.append(c)

    # ---- Case 6: errata correction BOE-A-2018-2041 ----
    corr = parse_document("boe_diario_xml__BOE-A-2018-2041")
    item = next(t for _c, t in corr.paragraphs if t.startswith("1."))
    m = re.search(r"donde dice: «(.+?)», debe decir: «(.+?)»", item)
    old_c = m.group(1) if m else None
    new_c = m.group(2) if m else None
    c = base_case(
        "C6_correction_errata", "BOE-A-2018-2041", "CORRECTION",
        "Norma 64, apartado 9 (BOE p. 119679)",
        _relation(target, "BOE-A-2018-2041"),
        "CORRECTION_PROVIDES_OLD_AND_NEW_LITERAL", "PROVEN",
        {"correction_item": item},
        old_c, new_c,
        "BOE-A-2018-2041 daily XML, item '1. ... donde dice: «norma 54»'",
        "BOE-A-2018-2041 daily XML, item '1. ... debe decir: «norma 53»'",
        "A_TEXT_ON_BOTH_SIDES",
        extra_evidence=["boe_diario_xml__BOE-A-2018-2041"],
    )
    _dates(c, corr)
    c["notes"] = (
        "Corrections are discoverable in <analisis><posteriores> with palabra "
        "'CORRECCIÓN de errores' (codigo 201), have no fecha_vigencia, and alter the "
        "base text; they must be ordered separately from ordinary modifications."
    )
    cases.append(c)

    result = {
        "schema": "regdelta.g0c.cases/v1",
        "target_instrument": "BOE-A-2017-14334",
        "confidence_enum": ["PROVEN", "PARTIAL", "NOT_PROVEN"],
        "confidence_source": "structural source-availability rule, not an LLM",
        "cases": cases,
    }
    dump(result, EVIDENCE_DIR / "cases.json")
    for c in cases:
        print(f"{c['case_id']:38s} {c['modifier_instrument']:20s} {c['confidence']:9s} "
              f"old={c['old_text_available']!s:5s} new={c['new_text_available']!s:5s} "
              f"old_sha={str(c['old_text_sha256'])[:12]}")
    print("wrote", EVIDENCE_DIR / "cases.json")


def _heading_block(paragraphs, start, stop):
    from probe_parse import extract_heading_block

    return extract_heading_block(paragraphs, start, stop, cls="articulo")


def _dates(case, doc):
    case["publication_date"] = doc.metadata.get("fecha_publicacion")
    case["effective_date"] = doc.metadata.get("fecha_vigencia") or None
    case["modifier_title"] = doc.metadata.get("titulo")
    case["modifier_rango"] = doc.metadata.get("rango")


if __name__ == "__main__":
    main()
