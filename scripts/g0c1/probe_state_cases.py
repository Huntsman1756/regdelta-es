"""G0-C.1 discovery: representation-level old->new chains for annexed states.

Run:  python scripts/g0c1/probe_state_cases.py

G0-C classified annex/estado old text as NOT_PROVEN because the daily XML
carries page images. G0-C.1 reframes this: the old *textual* representation
is absent, but the old *official* representation is PROVEN (the BOE page
image, fetched and SHA-256'd), and the change itself is declared textually
by the modifier. This probe builds six representation-level chain fichas:

  estado -> old official representation (image, SHA) -> MODIFIED_BY
         -> modifier -> new official representation (text/table/image, SHA)

without OCR. Diff levels:

* TEXT_DIFF_PROVEN            - structured text on both sides
* VISUAL_PREDECESSOR_PROVEN   - old side bound to official page image
* DECLARED_CHANGE_PROVEN      - modifier declares the change literally
                                (corrections, literal substitutions)
* SEMANTIC_DIFF_NOT_AVAILABLE - no textual old->new diff can be produced
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g0c"))
from probe_common import (  # noqa: E402
    EVIDENCE_DIR, dump, load_manifest, read_raw_text, sha256_hex,
)
from probe_parse import extract_between, normalize, parse_document  # noqa: E402

G0C1_DIR = Path(__file__).resolve().parents[2] / "evidence" / "g0c1"
TARGET_RAW = "boe_diario_xml__BOE-A-2017-14334"
DIARIO_XML_URL = "https://www.boe.es/diario_boe/xml.php?id={id}"


def h_bytes(data: bytes) -> str:
    return sha256_hex(data)


def h(text: str | None) -> str | None:
    return sha256_hex(text.encode("utf-8")) if text is not None else None


def g0c_sha(name: str) -> str | None:
    e = load_manifest()["entries"].get(name)
    return e["sha256"] if e else None


def g0c1_entry(name: str) -> dict | None:
    m = json.loads((G0C1_DIR / "raw" / "manifest.json").read_text(encoding="utf-8"))
    return m["entries"].get(name)


def image_repr(name: str, estado: str, page: int) -> dict:
    e = g0c1_entry(name)
    return {
        "kind": "IMAGE",
        "artifact_url": e["url"],
        "boe_page": page,
        "sha256": e["sha256"],
        "size_bytes": e["size_bytes"],
        "raw_name": name,
        "binding": (
            "DERIVED-anchored: doc.php alt sequence -> BOE page; validated by "
            "correction-cited pages (annex-map.json, 10/10 anchors) and by "
            "the PDF embedded text layer naming the estado on the page"
        ),
        "granularity_note": (
            f"page-level: the image is the whole BOE page containing {estado}; "
            "sub-page regions are not separable without rendering"
        ),
    }


def table_repr(raw_name: str, doc_id: str, kid_indexes: list[int], label: str) -> dict:
    """Hash the canonical serialization of the given <texto> children."""
    root = ET.fromstring(read_raw_text(raw_name))
    kids = list(root.find("texto"))
    blob = b"\n".join(ET.tostring(kids[i]) for i in kid_indexes)
    text = "\n".join(normalize(" ".join(kids[i].itertext())) for i in kid_indexes)
    return {
        "kind": "TABLE" if any(kids[i].tag == "table" for i in kid_indexes) else "TEXT",
        "source": f"{doc_id} daily XML, <texto> children {kid_indexes} ({label})",
        "sha256": h_bytes(blob),
        "text_sha256": h("\n".join(t for t in text.split("\n") if t)),
        "size_bytes": len(blob),
        "raw_name": raw_name,
        "preview": text[:240],
    }


def main() -> None:
    target = parse_document(TARGET_RAW)
    amap = json.loads((G0C1_DIR / "annex-map.json").read_text(encoding="utf-8"))

    def relation(mid: str) -> dict | None:
        for ref in target.posteriores:
            if ref.referencia == mid:
                return {"palabra": ref.palabra, "texto": ref.texto}
        return None

    cases = []

    # ---- S1: FI 102-2 — correction deleting lines (page anchor 119824) ----
    corr = parse_document("boe_diario_xml__BOE-A-2018-2041")
    item5 = next(t for _c, t in corr.paragraphs if t.startswith("5."))
    cases.append({
        "case_id": "S1_estado_FI102-2_correction",
        "target_instrument": "BOE-A-2017-14334",
        "modifier_instrument": "BOE-A-2018-2041",
        "kind": "CORRECTION",
        "target_locator": "Anejo 4, estado FI 102-2",
        "relation_raw": relation("BOE-A-2018-2041"),
        "operation_raw": item5,
        "publication_date": corr.metadata.get("fecha_publicacion"),
        "effective_date": corr.metadata.get("fecha_vigencia") or None,
        "old_representation": image_repr(
            "boe_annex_img__119824__alt109", "FI 102-2", 119824),
        "new_representation": {
            "kind": "TEXT_DECLARATION",
            "source": "BOE-A-2018-2041 item 5: lines literally named are deleted",
            "text_sha256": h(item5),
            "deleted_lines_literal": re.findall(r"«([^»]+)»", item5),
        },
        "change_declaration": item5,
        "diff_level": ["DECLARED_CHANGE_PROVEN", "VISUAL_PREDECESSOR_PROVEN",
                       "SEMANTIC_DIFF_NOT_AVAILABLE"],
        "anchor": (
            "OBSERVED: the correction itself cites 'página 119824 ... estado "
            "FI 102-2'; the PDF text layer on that page shows 'FI 102-2' and "
            "the image bound to it shows the FI 102-2 form"
        ),
        "confidence": "PROVEN",
        "evidence_urls": [DIARIO_XML_URL.format(id="BOE-A-2018-2041"),
                          "https://www.boe.es/datos/imagenes/disp/2017/296/14334_50444.png"],
    })

    # ---- S2: FI 131-2.2 — correction adding nota (b) (page anchor 119865) ----
    item9, note9 = None, None
    for i, (_c, t) in enumerate(corr.paragraphs):
        if t.startswith("9."):
            item9 = t
            note9 = corr.paragraphs[i + 1][1]
            break
    cases.append({
        "case_id": "S2_estado_FI131-2.2_correction",
        "target_instrument": "BOE-A-2017-14334",
        "modifier_instrument": "BOE-A-2018-2041",
        "kind": "CORRECTION",
        "target_locator": "Anejo 4, estado FI 131-2.2",
        "relation_raw": relation("BOE-A-2018-2041"),
        "operation_raw": item9 + " " + (note9 or ""),
        "publication_date": corr.metadata.get("fecha_publicacion"),
        "effective_date": corr.metadata.get("fecha_vigencia") or None,
        "old_representation": image_repr(
            "boe_annex_img__119865__alt150", "FI 131-2.2", 119865),
        "new_representation": {
            "kind": "TEXT",
            "source": "BOE-A-2018-2041 item 9: literal nota (b) added",
            "text": note9,
            "text_sha256": h(note9),
        },
        "change_declaration": item9,
        "diff_level": ["DECLARED_CHANGE_PROVEN", "VISUAL_PREDECESSOR_PROVEN",
                       "SEMANTIC_DIFF_NOT_AVAILABLE"],
        "anchor": "OBSERVED: correction cites 'página 119865 ... estado FI 131-2.2'",
        "confidence": "PROVEN",
        "evidence_urls": [DIARIO_XML_URL.format(id="BOE-A-2018-2041"),
                          "https://www.boe.es/datos/imagenes/disp/2017/296/14334_51761.png"],
    })

    # ---- S3: FI 142-1.1 — chained substitution (2/2018 then 1/2025) ----
    mod18 = parse_document("boe_diario_xml__BOE-A-2018-17880")
    mod25 = parse_document("boe_diario_xml__BOE-A-2025-26847")
    loc_vi, _ = extract_between(mod18.paragraphs, r"^vi\)\s+Se sustituye el estado FI 142-1\.1",
                                r"^vii\)\s+En el estado FI 150-8")
    loc_ii, _ = extract_between(mod25.paragraphs, r"^ii\)\s+Se sustituyen los estados FI 105 y FI 142-1\.1",
                                r"^iii\)\s")
    hop1_new = table_repr("boe_diario_xml__BOE-A-2018-17880", "BOE-A-2018-17880",
                          list(range(527, 540)), "anejo: FI 142-1.1 header + table + notes")
    hop2_new = table_repr("boe_diario_xml__BOE-A-2025-26847", "BOE-A-2025-26847",
                          [216, 217], "anejo: FI 142-1.1 header + table")
    cases.append({
        "case_id": "S3_estado_FI142-1.1_chained",
        "target_instrument": "BOE-A-2017-14334",
        "kind": "MODIFICATION_CHAIN",
        "target_locator": "Anejo 4, estado FI 142-1.1",
        "hops": [
            {
                "modifier_instrument": "BOE-A-2018-17880",
                "operation_raw": loc_vi,
                "publication_date": mod18.metadata.get("fecha_publicacion"),
                "effective_date": mod18.metadata.get("fecha_vigencia") or None,
                "old_representation": image_repr(
                    "boe_annex_img__119907__alt192", "FI 142-1.1", 119907),
                "new_representation": hop1_new,
                "diff_level": ["VISUAL_PREDECESSOR_PROVEN",
                               "SEMANTIC_DIFF_NOT_AVAILABLE"],
            },
            {
                "modifier_instrument": "BOE-A-2025-26847",
                "operation_raw": loc_ii,
                "publication_date": mod25.metadata.get("fecha_publicacion"),
                "effective_date": mod25.metadata.get("fecha_vigencia") or None,
                "old_representation": {
                    "kind": "TABLE",
                    "source": "BOE-A-2018-17880 annexed FI 142-1.1 (chained: prior new becomes current old)",
                    "sha256": hop1_new["sha256"],
                    "text_sha256": hop1_new["text_sha256"],
                    "raw_name": "boe_diario_xml__BOE-A-2018-17880",
                },
                "new_representation": hop2_new,
                "diff_level": ["TEXT_DIFF_PROVEN"],
            },
        ],
        "relation_raw": [relation("BOE-A-2018-17880"), relation("BOE-A-2025-26847")],
        "confidence": "PROVEN",
        "note": (
            "hop 2 is fully textual on both sides because the 2018 modifier "
            "republished the estado as a structured table; the image-bound "
            "predecessor only limits hop 1"
        ),
        "evidence_urls": [
            DIARIO_XML_URL.format(id="BOE-A-2018-17880"),
            DIARIO_XML_URL.format(id="BOE-A-2025-26847"),
            "https://www.boe.es/datos/imagenes/disp/2017/296/14334_53108.png",
        ],
        "evidence_raw_sha256": [
            g0c_sha("boe_diario_xml__BOE-A-2018-17880"),
            g0c_sha("boe_diario_xml__BOE-A-2025-26847"),
            g0c1_entry("boe_annex_img__119907__alt192")["sha256"],
        ],
    })

    # ---- S4: FI 105 — substitution by Circular 1/2025 ----
    new_fi105 = table_repr("boe_diario_xml__BOE-A-2025-26847", "BOE-A-2025-26847",
                           [212, 213], "anejo: FI 105 header + table")
    cases.append({
        "case_id": "S4_estado_FI105_substitution",
        "target_instrument": "BOE-A-2017-14334",
        "modifier_instrument": "BOE-A-2025-26847",
        "kind": "MODIFICATION",
        "target_locator": "Anejo 4, estado FI 105",
        "relation_raw": relation("BOE-A-2025-26847"),
        "operation_raw": loc_ii,
        "publication_date": mod25.metadata.get("fecha_publicacion"),
        "effective_date": mod25.metadata.get("fecha_vigencia") or None,
        "old_representation": {
            "kind": "IMAGE",
            "pages": [image_repr("boe_annex_img__119835__alt120", "FI 105-1", 119835),
                      image_repr("boe_annex_img__119836__alt121", "FI 105-2", 119836)],
            "page_span": amap["estados"]["FI 105"]["page_span"],
        },
        "new_representation": new_fi105,
        "diff_level": ["VISUAL_PREDECESSOR_PROVEN", "SEMANTIC_DIFF_NOT_AVAILABLE"],
        "confidence": "PROVEN",
        "evidence_urls": [DIARIO_XML_URL.format(id="BOE-A-2025-26847")],
        "evidence_raw_sha256": [
            g0c_sha("boe_diario_xml__BOE-A-2025-26847"),
            g0c1_entry("boe_annex_img__119835__alt120")["sha256"],
            g0c1_entry("boe_annex_img__119836__alt121")["sha256"],
        ],
    })

    # ---- S5: FI 100-14 — substitution by Circular 2/2020 (image -> image) ----
    mod20 = parse_document("boe_diario_xml__BOE-A-2020-6186")
    loc_vii, _ = extract_between(mod20.paragraphs, r"^vii\)\s+Se sustituye el estado FI 100-14",
                                 r"^viii\)")
    new_img = g0c1_entry("boe_annex_img__2020-6186__alt005")
    cases.append({
        "case_id": "S5_estado_FI100-14_substitution",
        "target_instrument": "BOE-A-2017-14334",
        "modifier_instrument": "BOE-A-2020-6186",
        "kind": "MODIFICATION",
        "target_locator": "Anejo 4, estado FI 100-14",
        "relation_raw": relation("BOE-A-2020-6186"),
        "operation_raw": loc_vii,
        "publication_date": mod20.metadata.get("fecha_publicacion"),
        "effective_date": mod20.metadata.get("fecha_vigencia") or None,
        "old_representation": image_repr(
            "boe_annex_img__119818__alt103", "FI 100-14", 119818),
        "new_representation": {
            "kind": "IMAGE",
            "artifact_url": new_img["url"],
            "boe_page": 40313,
            "sha256": new_img["sha256"],
            "size_bytes": new_img["size_bytes"],
            "raw_name": "boe_annex_img__2020-6186__alt005",
            "binding": (
                "DERIVED-anchored: BOE-A-2020-6186 doc.php alt sequence -> BOE "
                "page (signature ends p.40308; PDF text layer on p.40313 shows "
                "'FI 100-14'); visually verified"
            ),
        },
        "diff_level": ["VISUAL_PREDECESSOR_PROVEN", "SEMANTIC_DIFF_NOT_AVAILABLE"],
        "confidence": "PROVEN",
        "note": (
            "image -> image: even the *modifier* publishes the new estado as a "
            "page image; the chain is still fully representable at artifact level"
        ),
        "evidence_urls": [DIARIO_XML_URL.format(id="BOE-A-2020-6186")],
        "evidence_raw_sha256": [
            g0c_sha("boe_diario_xml__BOE-A-2020-6186"),
            g0c1_entry("boe_annex_img__119818__alt103")["sha256"],
            new_img["sha256"],
        ],
    })

    # ---- S6: FI 106-1.1 — nota (a) modified inside an image page ----
    loc_iii, _ = extract_between(mod18.paragraphs,
                                 r"^iii\)\s+En el estado FI 106-1\.1",
                                 r"^iv\)\s+En el estado FI 106-2\.1")
    cases.append({
        "case_id": "S6_estado_FI106-1.1_note_mod",
        "target_instrument": "BOE-A-2017-14334",
        "modifier_instrument": "BOE-A-2018-17880",
        "kind": "MODIFICATION",
        "target_locator": "Anejo 4, estado FI 106-1.1, nota (a), primer párrafo",
        "relation_raw": relation("BOE-A-2018-17880"),
        "operation_raw": loc_iii,
        "publication_date": mod18.metadata.get("fecha_publicacion"),
        "effective_date": mod18.metadata.get("fecha_vigencia") or None,
        "old_representation": image_repr(
            "boe_annex_img__119837__alt122", "FI 106-1.1", 119837),
        "new_representation": {
            "kind": "TEXT",
            "source": "BOE-A-2018-17880, paragraph following locator iii)",
            "text_sha256": h(loc_iii),
        },
        "diff_level": ["DECLARED_CHANGE_PROVEN", "VISUAL_PREDECESSOR_PROVEN",
                       "SEMANTIC_DIFF_NOT_AVAILABLE"],
        "confidence": "PROVEN",
        "note": (
            "region-level change inside a page image: the new text is literal "
            "and auditable; the old note lives inside the page image (region "
            "not separable below page granularity)"
        ),
        "evidence_urls": [DIARIO_XML_URL.format(id="BOE-A-2018-17880")],
        "evidence_raw_sha256": [
            g0c_sha("boe_diario_xml__BOE-A-2018-17880"),
            g0c1_entry("boe_annex_img__119837__alt122")["sha256"],
        ],
    })

    result = {
        "schema": "regdelta.g0c1.state-cases/v1",
        "target_instrument": "BOE-A-2017-14334",
        "diff_level_enum": [
            "TEXT_DIFF_PROVEN", "VISUAL_PREDECESSOR_PROVEN",
            "DECLARED_CHANGE_PROVEN", "SEMANTIC_DIFF_NOT_AVAILABLE",
        ],
        "confidence_source": "structural source-availability rule, not an LLM",
        "cases": cases,
    }
    path = G0C1_DIR / "state-cases.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    for c in cases:
        hops = c.get("hops")
        if hops:
            for i, hp in enumerate(hops, 1):
                print(f"{c['case_id']} hop{i}: {hp['modifier_instrument']} "
                      f"old={hp['old_representation']['kind']} new={hp['new_representation']['kind']} "
                      f"{hp['diff_level']}")
        else:
            print(f"{c['case_id']}: {c['modifier_instrument']} "
                  f"old={c['old_representation']['kind']} "
                  f"new={c['new_representation']['kind']} {c['diff_level']}")
    print("wrote", path)


if __name__ == "__main__":
    main()
