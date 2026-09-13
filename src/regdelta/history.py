"""Historical reconstruction orchestrator (G0-C.2).

Chains, for one target instrument:

    instrument -> subjects -> representations -> modification_relations

Every persisted row traces to ``source_snapshots`` -> ``source_blobs`` ->
sha256 -> raw official bytes. No OCR, no LLM, no applicability inference.

Fetch is injectable: production passes ``http.http_fetch``; tests pass a
fixture-backed function serving evidence imports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import annexmap, operations
from .rawstore import store_blob
from .sources import boe_diario, boe_doc, boe_pdf
from .util import canonical_date, sha256_hex, sha256_hex_text

PARSER_NAME = "history"
PARSER_VERSION = "v1"

BOE_BASE = "https://www.boe.es"
XML_URL = BOE_BASE + "/diario_boe/xml.php?id={boe}"
DOC_URL = BOE_BASE + "/buscar/doc.php?id={boe}"
PDF_URL = BOE_BASE + "/boe/dias/{y}/{m}/{d}/pdfs/{boe}.pdf"

_CIRCULAR_RE = re.compile(r"Circular\s+(\d+)\s*/\s*(\d{4})", re.IGNORECASE)
_ANNEX_CODE_HEADER_RE = re.compile(
    r"^(FI|FC|PI|PC|PA|UEM|AVE)\s+(\d[\d.\-]*)")

ANOMALY_FETCH = "FETCH_ERROR"
ANOMALY_ANCHOR = "ANCHOR_MISMATCH"
ANOMALY_UNBOUND = "UNBOUND_SUBJECT"
ANOMALY_ANNEX = "ANNEX_REFERENCE_UNRESOLVED"


# ---------------------------------------------------------------------------
# identity helpers
# ---------------------------------------------------------------------------


def instrument_id(boe_id: str) -> str:
    return sha256_hex_text(f"instrument|{boe_id}")


def subject_id(boe_id: str, locator_key: str) -> str:
    return sha256_hex_text(f"subject|{boe_id}|{locator_key}")


def _canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def representation_id(subject: str, kind: str, content_sha: str,
                      locator: dict) -> str:
    return sha256_hex_text(
        f"repr|{subject}|{kind}|{content_sha}|{_canonical_json(locator)}")


def modification_relation_id(modifier_boe: str, subject_key: str,
                             locator_raw: str, before: str | None,
                             after: str | None) -> str:
    return sha256_hex_text(
        f"mrel|{modifier_boe}|{subject_key}|{locator_raw}|"
        f"{before or '-'}|{after or '-'}")


# ---------------------------------------------------------------------------
# acquisition
# ---------------------------------------------------------------------------


@dataclass
class Artifact:
    snapshot_id: str
    blob_sha256: str
    body: bytes


class Acquirer:
    """url -> (snapshot, blob, body) via fetch_fn + rawstore."""

    def __init__(self, conn, data_dir: Path, fetch_fn):
        self.conn = conn
        self.data_dir = Path(data_dir)
        self.fetch_fn = fetch_fn
        self.cache: dict[str, Artifact | None] = {}
        self.errors: list[dict] = []

    def get(self, source_id: str, url: str, accept: str,
            parser_name: str, parser_version: str,
            checked_at: str) -> Artifact | None:
        if url in self.cache:
            return self.cache[url]
        result = self.fetch_fn(url, accept)
        if result.body is None or result.error_class or (
                result.http_status is not None and result.http_status != 200):
            self.errors.append({"url": url, "error": result.error_message,
                                "class": result.error_class})
            self.cache[url] = None
            return None
        sha, _ = store_blob(self.data_dir, result.body)
        self.conn.execute(
            "INSERT OR IGNORE INTO source_blobs (sha256, size_bytes, stored_at)"
            " VALUES (?,?,?)", (sha, len(result.body), checked_at))
        snap = sha256_hex_text(f"snap|{source_id}|{url}|{sha}")
        self.conn.execute(
            "INSERT OR IGNORE INTO source_snapshots (snapshot_id, source_id,"
            " source_url, blob_sha256, source_date, source_updated_at,"
            " parse_status, parse_error, parser_name, parser_version,"
            " has_anomalies, first_checked_at)"
            " VALUES (?,?,?,?,?,NULL,'COMPLETE',NULL,?,?,0,?)",
            (snap, source_id, url, sha, None,
             parser_name, parser_version, checked_at))
        art = Artifact(snap, sha, result.body)
        self.cache[url] = art
        return art


# ---------------------------------------------------------------------------
# text region extraction (before-side TEXT bindings)
# ---------------------------------------------------------------------------


def _norma_span(doc: boe_diario.DiarioDoc, num: str) -> tuple[int, int] | None:
    start = None
    for n in doc.nodes:
        if n.cls == "articulo" and re.match(rf"Norma\s+{num}\b", n.text):
            start = n.index
        elif start is not None and n.cls == "articulo":
            return (start, n.index)
    return (start, len(doc.nodes)) if start is not None else None


def _disp_span(doc: boe_diario.DiarioDoc, tipo: str,
               ordinal: str) -> tuple[int, int] | None:
    pat = re.compile(
        rf"Disposici[oó]n\s+{tipo}\s+{ordinal}\b", re.IGNORECASE)
    start = None
    for n in doc.nodes:
        if n.cls == "articulo" and pat.search(n.text):
            start = n.index
        elif start is not None and n.cls == "articulo":
            return (start, n.index)
    return (start, len(doc.nodes)) if start is not None else None


def _sub_region(doc: boe_diario.DiarioDoc, span: tuple[int, int],
                pattern: re.Pattern) -> tuple[int, int] | None:
    """First node matching ``pattern`` inside span, until the next sibling
    marker (a numbered/lettered paragraph) or span end."""
    start = None
    for i in range(*span):
        n = doc.nodes[i]
        if n.kind != "p":
            continue
        if start is None:
            if pattern.match(n.text):
                start = i
        elif re.match(r"^(?:\d+\.|[a-z]\)|[ivxlcdm]+\s*[.)])",
                      n.text, re.IGNORECASE):
            return (start, i)
    return (start, span[1]) if start is not None else None


def text_region(doc: boe_diario.DiarioDoc,
                locator_key: str) -> tuple[int, int] | None:
    """Node span of a textual subject in the target document."""
    parts = locator_key.split(".")
    head = parts[0]
    if head.startswith("norma:"):
        span = _norma_span(doc, head[6:])
    elif head.startswith("disp:"):
        tipo, _, ordinal = head[5:].partition(".")
        span = _disp_span(doc, tipo, ordinal)
    else:
        return None
    if span is None:
        return None
    for part in parts[1:]:
        kind, _, val = part.partition(":")
        if kind == "apartado":
            span = _sub_region(doc, span,
                               re.compile(rf"^{re.escape(val)}\s*\."))
        elif kind == "letra":
            span = _sub_region(doc, span,
                               re.compile(rf"^{re.escape(val)}\)"))
        elif kind == "numeral":
            span = _sub_region(
                doc, span,
                re.compile(rf"^{re.escape(val)}\s*[.)]", re.IGNORECASE))
        elif kind == "nota":
            span = _sub_region(doc, span, re.compile(
                rf"^[«(]+\s*\(?{re.escape(val)}\)?", re.IGNORECASE))
        else:
            return None
        if span is None:
            return None
    return span


def region_text(doc: boe_diario.DiarioDoc,
                span: tuple[int, int]) -> tuple[str, str]:
    """(kind, serialized text) for a node span: TABLE iff it contains a
    table node, else TEXT."""
    texts: list[str] = []
    has_table = False
    for i in range(*span):
        n = doc.nodes[i]
        if n.kind == "table":
            has_table = True
            for row in n.rows:
                texts.append(" | ".join(row))
        elif n.text:
            texts.append(n.text)
    return ("TABLE" if has_table else "TEXT"), "\n".join(texts)


# ---------------------------------------------------------------------------
# modifier annex handling
# ---------------------------------------------------------------------------


def structured_annex(doc: boe_diario.DiarioDoc) -> dict[str, tuple[int, int]]:
    """Estado-code -> node span inside the modifier's own annex.

    A state region opens at a paragraph whose text starts with a state code
    (``FI 105 DESGLOSE ...`` — ``anexo`` or ``centro_*`` classes in the
    corpus) and closes at the next such paragraph. Regions are DECLARED by
    the document structure itself.
    """
    annex_start = None
    for n in doc.nodes:
        if n.cls == "anexo" or (
                n.kind == "p" and n.text.strip() == "ANEJO"):
            annex_start = n.index
            break
    if annex_start is None:
        return {}
    starts: list[tuple[int, str]] = []
    for i in range(annex_start, len(doc.nodes)):
        n = doc.nodes[i]
        if n.kind == "p" and _ANNEX_CODE_HEADER_RE.match(n.text):
            m = _ANNEX_CODE_HEADER_RE.match(n.text)
            code = annexmap._norm_code(m.group(1), m.group(2))
            starts.append((i, code))
    regions: dict[str, tuple[int, int]] = {}
    for pos, (i, code) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(doc.nodes)
        regions.setdefault(code, (i, end))
    return regions


# ---------------------------------------------------------------------------
# reconstruction
# ---------------------------------------------------------------------------


@dataclass
class _Ctx:
    conn: object
    acquirer: Acquirer
    checked_at: str
    instruments: dict = field(default_factory=dict)
    annex_maps: dict = field(default_factory=dict)
    doc_images: dict = field(default_factory=dict)
    pending_anchors: dict = field(default_factory=dict)
    anomalies: list = field(default_factory=list)


def _upsert_instrument(ctx: _Ctx, boe_id: str, titulo: str,
                       doc: boe_diario.DiarioDoc | None,
                       snapshot_id: str | None) -> str:
    iid = instrument_id(boe_id)
    if iid in ctx.instruments:
        return iid
    meta = doc.metadata if doc else {}
    ctx.conn.execute(
        "INSERT OR IGNORE INTO instruments (instrument_id, boe_id, titulo,"
        " rango, fecha_disposicion, fecha_publicacion, fecha_vigencia,"
        " estado_consolidacion, origin, snapshot_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (iid, boe_id, titulo or meta.get("titulo", ""),
         meta.get("rango"), canonical_date(meta.get("fecha_disposicion", "")),
         canonical_date(meta.get("fecha_publicacion", "")),
         canonical_date(meta.get("fecha_vigencia", "")),
         meta.get("estado_consolidacion"),
         "PARSED" if doc else "REFERENCED", snapshot_id))
    ctx.instruments[iid] = doc
    return iid


def _insert_instrument_relations(ctx: _Ctx, iid: str,
                                 doc: boe_diario.DiarioDoc,
                                 snapshot_id: str) -> None:
    for ref in doc.anteriores + doc.posteriores:
        other_iid = instrument_id(ref.referencia)
        ctx.conn.execute(
            "INSERT OR IGNORE INTO instruments (instrument_id, boe_id,"
            " titulo, origin, snapshot_id) VALUES (?,?,?,'REFERENCED',NULL)",
            (other_iid, ref.referencia, ref.texto))
        rel_id = sha256_hex_text(
            f"irel|{iid}|{ref.direction}|{ref.referencia}|{ref.palabra}")
        ctx.conn.execute(
            "INSERT OR IGNORE INTO instrument_relations"
            " (instrument_relation_id, declaring_instrument_id, direction,"
            " other_boe_id, other_instrument_id, palabra, palabra_codigo,"
            " descripcion, source_snapshot_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (rel_id, iid,
             "ANTERIOR" if ref.direction == "anterior" else "POSTERIOR",
             ref.referencia, other_iid, ref.palabra, ref.palabra_codigo,
             ref.texto, snapshot_id))


def _upsert_subject(ctx: _Ctx, boe_id: str, key: str, label: str,
                    kind: str) -> str:
    sid = subject_id(boe_id, key)
    ctx.conn.execute(
        "INSERT OR IGNORE INTO subjects (subject_id, instrument_id,"
        " locator_key, label, subject_kind) VALUES (?,?,?,?,?)",
        (sid, instrument_id(boe_id), key, label,
         kind if kind in ("NORMA", "ESTADO", "ANEJO", "PUNTO", "APARTADO",
                          "INDICE", "DISPOSICION", "NOTA", "INSTRUMENT")
         else "APARTADO"))
    return sid


def _insert_representation(ctx: _Ctx, sid: str, kind: str,
                           text_content: str | None, locator: dict,
                           snapshot_id: str, binding: str,
                           binding_evidence: dict) -> str:
    if kind in ("TEXT", "TABLE"):
        content_sha = sha256_hex((text_content or "").encode("utf-8"))
    else:
        content_sha = sha256_hex(_canonical_json(locator).encode("utf-8"))
    rid = representation_id(sid, kind, content_sha, locator)
    ctx.conn.execute(
        "INSERT OR IGNORE INTO representations (representation_id,"
        " subject_id, representation_kind, content_sha256, text_content,"
        " artifact_locator, source_snapshot_id, binding, binding_evidence,"
        " parser_name, parser_version) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (rid, sid, kind, content_sha, text_content,
         _canonical_json(locator), snapshot_id, binding,
         json.dumps(binding_evidence, ensure_ascii=False, sort_keys=True),
         PARSER_NAME, PARSER_VERSION))
    return rid


def _image_representation(ctx: _Ctx, sid: str, boe_id: str,
                          pages: list[int], amap: annexmap.AnnexMap,
                          binding: str, anchor_note: dict) -> str | None:
    """IMAGE repr: one row whose locator lists every bound page-image."""
    imgs = ctx.doc_images.get(boe_id) or []
    entries = []
    snaps = []
    for page in pages:
        alt = amap.img_by_page.get(page)
        if alt is None or alt > len(imgs):
            return None
        src = imgs[alt - 1].src
        art = ctx.acquirer.get("boe_imagen", BOE_BASE + src, "image/*",
                               "boe_imagen", "v1", ctx.checked_at)
        if art is None:
            return None
        snaps.append(art.snapshot_id)
        entries.append({"boe_page": page, "img_alt": alt,
                        "url": BOE_BASE + src, "blob_sha256": art.blob_sha256})
    if not entries:
        return None
    locator = {"instrument": boe_id, "type": "image_pages", "pages": entries}
    evidence = dict(anchor_note)
    evidence["image_snapshots"] = snaps
    return _insert_representation(ctx, sid, "IMAGE", None, locator,
                                  snaps[0], binding, evidence)


def _structured_annex_repr(ctx: _Ctx, sid: str, modifier_boe: str,
                           mdoc: boe_diario.DiarioDoc, code: str,
                           snapshot_id: str) -> str | None:
    regions = structured_annex(mdoc)
    span = regions.get(code)
    if span is None:
        # try root code ("FI 142" annex header serving "FI 142-1.1")
        span = regions.get(annexmap.estado_root(code))
    if span is None:
        return None
    kind, text = region_text(mdoc, span)
    locator = {"instrument": modifier_boe, "type": "xml_nodes",
               "node_span": [span[0], span[1]]}
    return _insert_representation(
        ctx, sid, kind, text, locator, snapshot_id, "DECLARED",
        {"rule": "estado code header in modifier annex",
         "node_span": list(span)})


def _target_annex_map(ctx: _Ctx, boe_id: str,
                      doc: boe_diario.DiarioDoc) -> annexmap.AnnexMap | None:
    if boe_id in ctx.annex_maps:
        return ctx.annex_maps[boe_id]
    doc_art = ctx.acquirer.get("boe_doc", DOC_URL.format(boe=boe_id),
                               "text/html", boe_doc.PARSER_NAME,
                               boe_doc.PARSER_VERSION, ctx.checked_at)
    pdf_url = doc.metadata.get("url_pdf") or ""
    if pdf_url.startswith("/"):
        pdf_url = BOE_BASE + pdf_url
    if not pdf_url:
        pub = canonical_date(doc.metadata.get("fecha_publicacion", "") or "")
        if pub:
            y, m, d = pub.split("-")
            pdf_url = PDF_URL.format(y=y, m=m, d=d, boe=boe_id)
    pdf_art = None
    if pdf_url:
        pdf_art = ctx.acquirer.get(
            "boe_pdf", pdf_url,
            "application/pdf", boe_pdf.PARSER_NAME, boe_pdf.PARSER_VERSION,
            ctx.checked_at)
    if doc_art is None or pdf_art is None:
        ctx.annex_maps[boe_id] = None
        return None
    images = boe_doc.parse_doc_images(doc_art.body)
    ctx.doc_images[boe_id] = images
    texts = boe_pdf.PdfTextLayer(pdf_art.body).page_texts()
    start = int(doc.metadata.get("pagina_inicial") or 0)
    amap = annexmap.build_annex_map(texts, start, len(images),
                                    ctx.pending_anchors.get(boe_id, []))
    ctx.annex_maps[boe_id] = amap
    return amap


def reconstruct(conn, data_dir: Path, target_boe_id: str, fetch_fn,
                checked_at: str = "import") -> dict:
    """Rebuild the factual modification history of ``target_boe_id``."""
    ctx = _Ctx(conn=conn, acquirer=Acquirer(conn, data_dir, fetch_fn),
               checked_at=checked_at)

    xml_art = ctx.acquirer.get("boe_diario", XML_URL.format(boe=target_boe_id),
                               "application/xml", boe_diario.PARSER_NAME,
                               boe_diario.PARSER_VERSION, checked_at)
    if xml_art is None:
        return {"error": "target xml unavailable",
                    "fetch_errors": ctx.acquirer.errors}
    target_res = boe_diario.parse_diario(xml_art.body)
    if target_res.parse_status != boe_diario.COMPLETE or not target_res.doc:
        return {"error": f"target xml parse: {target_res.parse_error}"}
    target = target_res.doc
    target_iid = _upsert_instrument(ctx, target_boe_id,
                                    target.metadata.get("titulo", ""),
                                    target, xml_art.snapshot_id)
    _insert_instrument_relations(ctx, target_iid, target,
                                 xml_art.snapshot_id)

    m = _CIRCULAR_RE.search(target.metadata.get("titulo", ""))
    target_ref = (int(m.group(1)), int(m.group(2))) if m else None

    # --- modifier discovery -------------------------------------------------
    posteriores = target.posteriores
    modifiers = []          # (boe_id, kind, ref)
    for ref in posteriores:
        kind = ("CORRECTION" if "CORREG" in ref.palabra.upper()
                or "CORREC" in ref.palabra.upper() else "MODIFICATION")
        modifiers.append((ref.referencia, kind, ref))

    # --- parse every modifier first: correction anchors feed the target map -
    parsed_mods: list[dict] = []
    anchors: list[tuple[int, str]] = []
    for boe_id, kind, ref in modifiers:
        art = ctx.acquirer.get("boe_diario", XML_URL.format(boe=boe_id),
                               "application/xml", boe_diario.PARSER_NAME,
                               boe_diario.PARSER_VERSION, checked_at)
        if art is None:
            ctx.anomalies.append(
                {"kind": ANOMALY_FETCH, "detail": {"modifier": boe_id}})
            parsed_mods.append({"boe_id": boe_id, "kind": kind, "ref": ref,
                                "doc": None, "ops": [], "snapshot": None})
            continue
        mres = boe_diario.parse_diario(art.body)
        if mres.parse_status != boe_diario.COMPLETE or not mres.doc:
            ctx.anomalies.append({
                "kind": ANOMALY_FETCH,
                "detail": {"modifier": boe_id, "parse": mres.parse_error}})
            parsed_mods.append({"boe_id": boe_id, "kind": kind, "ref": ref,
                                "doc": None, "ops": [], "snapshot": None})
            continue
        mdoc = mres.doc
        _upsert_instrument(ctx, boe_id, mdoc.metadata.get("titulo", ""),
                           mdoc, art.snapshot_id)
        _insert_instrument_relations(
            ctx, instrument_id(boe_id), mdoc, art.snapshot_id)
        # a correction instrument names its target in prose, not in
        # section headings: match every section (whole-body fallback) only
        # when the title confirms it is this target's correction
        if kind == "CORRECTION":
            names = [(int(a), int(b)) for a, b in
                     _CIRCULAR_RE.findall(mdoc.metadata.get("titulo", ""))]
            tref = None if target_ref in names else target_ref
        else:
            tref = target_ref
        result = operations.parse_operations(mdoc, tref)
        if result.out_of_target_ops:
            ctx.anomalies.append({
                "kind": "OUT_OF_TARGET_OPS",
                "detail": {"modifier": boe_id,
                           "count": result.out_of_target_ops}})
        parsed_mods.append({"boe_id": boe_id, "kind": kind, "ref": ref,
                            "doc": mdoc, "ops": result.operations,
                            "snapshot": art.snapshot_id,
                            "pub": canonical_date(
                                mdoc.metadata.get("fecha_publicacion", "")
                                or ""),
                            "vigencia": canonical_date(
                                mdoc.metadata.get("fecha_vigencia") or "")})
        if kind == "CORRECTION":
            for op in result.operations:
                for s in op.subjects:
                    if s.page_ref and s.locator_key.startswith("estado:"):
                        anchors.append((s.page_ref, s.locator_key[7:]))

    # --- target annex map (anchored by the correction citations) -----------
    ctx.pending_anchors[target_boe_id] = anchors
    amap = _target_annex_map(ctx, target_boe_id, target)
    target_binding = ("ANCHORED_DERIVED" if (amap and amap.anchored)
                      else "UNANCHORED_DERIVED")
    if amap:
        for a in amap.anchors:
            if not a["match"]:
                ctx.anomalies.append({"kind": ANOMALY_ANCHOR, "detail": a})

    # --- relations -----------------------------------------------------------
    ordered = sorted(
        (pm for pm in parsed_mods if pm["doc"] is not None),
        key=lambda pm: (pm["pub"], pm["boe_id"]))
    current: dict[str, str | None] = {}   # subject key -> repr id | None
    stats = {"relations": 0, "representations": 0}

    for pm in ordered:
        mboe = pm["boe_id"]
        mdoc = pm["doc"]
        annex_regions = structured_annex(mdoc)
        modifier_map: annexmap.AnnexMap | None = None
        modifier_map_done = False

        for op in pm["ops"]:
            if op.is_container or not op.subjects:
                continue
            for sub in op.subjects:
                key = sub.locator_key
                sid = _upsert_subject(ctx, target_boe_id, key, sub.label,
                                      sub.kind)
                op_kind = operations.subject_operation_kind(
                    op.clause_text, key, op.operation_kind)
                snaps = [pm["snapshot"], xml_art.snapshot_id]

                # ----- before representation ------------------------------
                before_id = None
                before_kind = None
                if key in current:
                    before_id = current[key]
                    if before_id:
                        row = conn.execute(
                            "SELECT representation_kind FROM representations"
                            " WHERE representation_id=?",
                            (before_id,)).fetchone()
                        before_kind = row[0] if row else None
                else:
                    pages = amap.subject_pages(key) if amap else None
                    if pages:
                        before_id = _image_representation(
                            ctx, sid, target_boe_id, pages, amap,
                            target_binding,
                            {"rule": "alt sequence + /Pages order + "
                                     "embedded page numbers",
                             "anchors": len(amap.anchors),
                             "anchors_matching": sum(
                                 1 for a in amap.anchors if a["match"])})
                        before_kind = "IMAGE" if before_id else None
                        if before_id is None:
                            ctx.anomalies.append({
                                "kind": ANOMALY_UNBOUND,
                                "detail": {"subject": key,
                                           "reason": "image fetch failed"}})
                    else:
                        span = text_region(target, key)
                        if span is not None:
                            kind_, text = region_text(target, span)
                            before_id = _insert_representation(
                                ctx, sid, kind_, text,
                                {"instrument": target_boe_id,
                                 "type": "xml_nodes",
                                 "node_span": [span[0], span[1]]},
                                xml_art.snapshot_id, "DECLARED",
                                {"rule": "locator resolved in target xml",
                                 "node_span": list(span)})
                            before_kind = kind_

                # ----- after representation -------------------------------
                after_id = None
                after_kind = None
                if op_kind == "DELETE":
                    pass
                elif op.annex_ref:
                    code = (key[7:] if key.startswith("estado:")
                            else key[6:] if key.startswith("anejo:")
                            else None)
                    if code and annex_regions:
                        after_id = _structured_annex_repr(
                            ctx, sid, mboe, mdoc, code, pm["snapshot"])
                        if after_id:
                            row = conn.execute(
                                "SELECT representation_kind FROM"
                                " representations WHERE representation_id=?",
                                (after_id,)).fetchone()
                            after_kind = row[0] if row else None
                    if after_id is None and not modifier_map_done:
                        modifier_map_done = True
                        modifier_map = _target_annex_map(ctx, mboe, mdoc)
                    if after_id is None and modifier_map is not None:
                        mpages = modifier_map.subject_pages(key)
                        if mpages:
                            after_id = _image_representation(
                                ctx, sid, mboe, mpages, modifier_map,
                                "UNANCHORED_DERIVED",
                                {"rule": "modifier annex images; no "
                                         "independent anchors",
                                 "anchors": 0})
                            after_kind = "IMAGE" if after_id else None
                    if after_id is None:
                        ctx.anomalies.append({
                            "kind": ANOMALY_ANNEX,
                            "detail": {"subject": key, "modifier": mboe,
                                       "clause": op.clause_text[:200]}})
                else:
                    s, e = op.content_span
                    if e > s:
                        kind_, text = region_text(mdoc, (s, e))
                        if text:
                            after_id = _insert_representation(
                                ctx, sid, kind_, text,
                                {"instrument": mboe, "type": "xml_nodes",
                                 "node_span": [s, e]},
                                pm["snapshot"], "DECLARED",
                                {"rule": "operation content span",
                                 "node_span": [s, e]})
                            after_kind = kind_

                # ----- relation --------------------------------------------
                literals = op.literals or None
                levels = []
                if before_kind in ("TEXT", "TABLE") and after_kind in (
                        "TEXT", "TABLE"):
                    levels.append("TEXT_DIFF_PROVEN")
                if literals or op_kind in ("SUBSTITUTE", "DELETE"):
                    levels.append("DECLARED_CHANGE_PROVEN")
                if before_kind in ("IMAGE", "PDF_PAGE"):
                    levels.append("VISUAL_PREDECESSOR_PROVEN")
                if not (before_kind in ("TEXT", "TABLE")
                        and after_kind in ("TEXT", "TABLE")):
                    levels.append("SEMANTIC_DIFF_NOT_AVAILABLE")

                if before_id and (after_id or op_kind == "DELETE"
                                  or literals):
                    resolution = "RESOLVED"
                elif before_id or after_id:
                    resolution = "PARTIAL"
                else:
                    resolution = "UNRESOLVED"
                    ctx.anomalies.append({
                        "kind": ANOMALY_UNBOUND,
                        "detail": {"subject": key, "modifier": mboe,
                                   "clause": op.clause_text[:200]}})

                rid = modification_relation_id(
                    mboe, key, op.clause_text, before_id, after_id)
                conn.execute(
                    "INSERT OR IGNORE INTO modification_relations"
                    " (relation_id, kind, operation_kind, target_subject_id,"
                    " modifier_instrument_id, locator_raw, relation_raw,"
                    " before_representation_id, after_representation_id,"
                    " publication_date, effective_date, declared_literals,"
                    " diff_levels, resolution, resolution_notes,"
                    " source_snapshot_ids, parser_name, parser_version)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, pm["kind"], op_kind, sid,
                     instrument_id(mboe), op.clause_text, pm["ref"].texto,
                     before_id, after_id, pm["pub"],
                     pm["vigencia"] if pm["kind"] == "MODIFICATION" else None,
                     json.dumps(literals, ensure_ascii=False)
                     if literals else None,
                     json.dumps(levels), resolution,
                     None, json.dumps(snaps), PARSER_NAME, PARSER_VERSION))
                stats["relations"] += 1

                # ----- chain update -----------------------------------------
                if op_kind == "DELETE":
                    current[key] = None
                elif after_id is not None:
                    current[key] = after_id
                # ops producing no new representation leave the last proven
                # representation standing (the declared change is recorded
                # in the relation itself)

    stats["representations"] = conn.execute(
        "SELECT COUNT(*) FROM representations").fetchone()[0]
    stats["subjects"] = conn.execute(
        "SELECT COUNT(*) FROM subjects").fetchone()[0]
    stats["instruments"] = conn.execute(
        "SELECT COUNT(*) FROM instruments").fetchone()[0]
    stats["instrument_relations"] = conn.execute(
        "SELECT COUNT(*) FROM instrument_relations").fetchone()[0]
    stats["anomalies"] = len(ctx.anomalies)
    return {
        "target": target_boe_id,
        "modifiers": [{"boe_id": b, "kind": k} for b, k, _ in modifiers],
        "target_annex_anchored": bool(amap and amap.anchored),
        "anchors": len(amap.anchors) if amap else 0,
        "fetch_errors": ctx.acquirer.errors,
        "anomalies": ctx.anomalies,
        **stats,
    }
