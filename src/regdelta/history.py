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
from uuid import uuid4

from . import annexmap, binding, operations
from .http import LIVE_FETCH
from .rawstore import store_blob
from .sources import boe_diario, boe_doc, boe_pdf
from .util import canonical_date, sha256_hex, sha256_hex_text

PARSER_NAME = "history"
PARSER_VERSION = "v3"

BOE_BASE = "https://www.boe.es"
XML_URL = BOE_BASE + "/diario_boe/xml.php?id={boe}"
DOC_URL = BOE_BASE + "/buscar/doc.php?id={boe}"
PDF_URL = BOE_BASE + "/boe/dias/{y}/{m}/{d}/pdfs/{boe}.pdf"

_CIRCULAR_RE = re.compile(r"Circular\s+(\d+)\s*/\s*(\d{4})", re.IGNORECASE)

ANOMALY_FETCH = "FETCH_ERROR"
ANOMALY_PARSE = "PARSE_INVALID"
ANOMALY_ANCHOR = "ANCHOR_MISMATCH"
ANOMALY_UNBOUND = "UNBOUND_SUBJECT"
ANOMALY_ANNEX = "ANNEX_REFERENCE_UNRESOLVED"
ANOMALY_OUT_OF_TARGET = "OUT_OF_TARGET_OPS"
ANOMALY_AMBIGUOUS = "AMBIGUOUS_BINDING"
ANOMALY_BIND_NOT_FOUND = "BINDING_NOT_FOUND"
ANOMALY_NOT_PROVABLE = "BINDING_NOT_PROVABLE"
ANOMALY_CHAIN = "CHAIN_DISCONTINUITY"


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
    """url -> (snapshot, blob, body) via fetch_fn + rawstore.

    A fetch marked ``via=LIVE_FETCH`` is a real HTTP observation and also
    records a ``source_checks`` row (same blob/snapshot may yield many
    checks — checks are events, never deduplicated). A fetch marked
    ``via=EVIDENCE_IMPORT`` replays captured bytes: it produces the same
    blob + snapshot provenance but no check, since no new observation
    happened.
    """

    def __init__(self, conn, data_dir: Path, fetch_fn):
        self.conn = conn
        self.data_dir = Path(data_dir)
        self.fetch_fn = fetch_fn
        self.cache: dict[str, Artifact | None] = {}
        self.errors: list[dict] = []

    def _check(self, source_id: str, url: str, checked_at: str,
               status: str, http_status, media_type, snapshot_id,
               error_class, error_message) -> None:
        check_id = sha256_hex_text(
            f"check|{source_id}|{url}|{checked_at}|{uuid4().hex}")
        self.conn.execute(
            "INSERT INTO source_checks (check_id, source_id, source_url,"
            " checked_at, status, http_status, media_type, snapshot_id,"
            " error_class, error_message) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (check_id, source_id, url, checked_at, status, http_status,
             media_type, snapshot_id, error_class, error_message))

    def get(self, source_id: str, url: str, accept: str,
            parser_name: str, parser_version: str,
            checked_at: str) -> Artifact | None:
        if url in self.cache:
            return self.cache[url]
        result = self.fetch_fn(url, accept)
        live = result.via == LIVE_FETCH
        if result.body is None or result.error_class or (
                result.http_status is not None and result.http_status != 200):
            if live:
                self._check(source_id, url, checked_at, "FETCH_ERROR",
                            result.http_status, result.media_type, None,
                            result.error_class, result.error_message)
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
        if live:
            self._check(source_id, url, checked_at, "OK",
                        result.http_status, result.media_type, snap,
                        None, None)
        art = Artifact(snap, sha, result.body)
        self.cache[url] = art
        return art


# ---------------------------------------------------------------------------
# span materialization
# ---------------------------------------------------------------------------


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
# resolution — binding statuses, not bare presence (G1 §25)
# ---------------------------------------------------------------------------


def _resolution(op_kind: str, before_status: str, after_status: str,
                literals) -> tuple[str, str | None]:
    """RESOLVED only when the bindings this operation class requires are
    BOUND. Notes name the abstention reason (ambiguous / not_provable /
    not_found), not merely 'missing'."""
    has_lit = bool(literals)
    b, a = before_status == "BOUND", after_status == "BOUND"
    if op_kind == "ADD":
        return ("RESOLVED", None) if a else (
            "UNRESOLVED", f"after: {after_status}")
    if op_kind == "DELETE":
        return ("RESOLVED", None) if b else (
            "UNRESOLVED", f"before: {before_status}")
    if op_kind == "SUBSTITUTE":
        if b and a:
            return "RESOLVED", None
        res = "PARTIAL" if (b or a or has_lit) else "UNRESOLVED"
    else:  # MODIFY, CORRECT, or anything else
        if b and (a or has_lit):
            return "RESOLVED", None
        res = "PARTIAL" if (b or a or has_lit) else "UNRESOLVED"
    notes = "; ".join(
        f"{side}: {st}" for side, st in
        (("before", before_status), ("after", after_status))
        if st != "BOUND" and st != "NOT_APPLICABLE")
    if not a and has_lit and not b:
        notes = (notes + "; " if notes else "") + "literals_only"
    return res, notes or None


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
    annex_pdf_snap: dict = field(default_factory=dict)
    doc_images: dict = field(default_factory=dict)
    pending_anchors: dict = field(default_factory=dict)
    # {"kind", "snapshot_id" (nullable), "detail" (dict)} — persisted to
    # the anomalies table at the end of the run
    anomalies: list = field(default_factory=list)


def _anomaly(ctx: _Ctx, kind: str, snapshot_id: str | None,
             detail: dict) -> None:
    ctx.anomalies.append(
        {"kind": kind, "snapshot_id": snapshot_id, "detail": detail})


def _unique_anomalies(anomalies: list) -> list:
    """The run's anomalies deduplicated by their deterministic id —
    what actually persists (identical abstentions collapse to one row)."""
    seen: set[str] = set()
    out = []
    for a in anomalies:
        aid = sha256_hex_text(
            f"anomaly|{a['kind']}|{a['snapshot_id'] or '-'}"
            f"|{_canonical_json(a['detail'])}")
        if aid not in seen:
            seen.add(aid)
            out.append(a)
    return out


def _persist_anomalies(ctx: _Ctx) -> None:
    """Idempotent: the anomaly id derives from kind+snapshot+detail, so a
    deterministic rerun re-encounters the same anomalies and inserts
    nothing new."""
    for a in ctx.anomalies:
        aid = sha256_hex_text(
            f"anomaly|{a['kind']}|{a['snapshot_id'] or '-'}"
            f"|{_canonical_json(a['detail'])}")
        ctx.conn.execute(
            "INSERT OR IGNORE INTO anomalies (anomaly_id, kind, snapshot_id,"
            " detail, detected_at) VALUES (?,?,?,?,?)",
            (aid, a["kind"], a["snapshot_id"],
             _canonical_json(a["detail"]), ctx.checked_at))


def _record_parse(ctx: _Ctx, snapshot_id: str, parse_status: str,
                  parse_error: str | None) -> None:
    """Snapshots are stored at fetch time as COMPLETE; a structured parse
    that fails afterwards corrects the row and any live check recorded for
    this observation."""
    if parse_status == boe_diario.COMPLETE:
        return
    ctx.conn.execute(
        "UPDATE source_snapshots SET parse_status=?, parse_error=?"
        " WHERE snapshot_id=?",
        (parse_status, parse_error, snapshot_id))
    ctx.conn.execute(
        "UPDATE source_checks SET status='PARSE_INVALID'"
        " WHERE snapshot_id=? AND checked_at=? AND status='OK'",
        (snapshot_id, ctx.checked_at))


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


# ---------------------------------------------------------------------------
# G1 binder integration: BindingResult -> persisted representation iff BOUND
# ---------------------------------------------------------------------------


@dataclass
class SubjectState:
    """Chain state per subject (G1 §27): PRESENT carries the proven
    representation; DELETED a proven delete; UNKNOWN a proven operation
    whose new representation could not be proven — a later non-ADD must
    NOT resurrect the old representation."""
    status: str                      # PRESENT | DELETED | UNKNOWN
    representation_id: str | None
    relation_id: str | None


def _xml_candidate(doc: boe_diario.DiarioDoc, boe: str,
                   span: tuple[int, int], scope: str, snap: str,
                   source: str) -> binding.Candidate:
    kind, text = region_text(doc, span)
    return binding.Candidate(
        instrument_boe_id=boe, snapshot_id=snap,
        representation_kind=kind, structural_scope=scope,
        node_span=span,
        locator={"instrument": boe, "type": "xml_nodes",
                 "node_span": [span[0], span[1]]},
        source=source, text=text)


def _materialize(ctx: _Ctx, sid: str, res: binding.BindingResult,
                 key: str, snapshot_id: str,
                 binding_label: str = "DECLARED") -> tuple[str, str] | None:
    """Persist the chosen candidate iff the result is BOUND. Returns
    (representation_id, representation_kind) or None."""
    if res.status != binding.BOUND or res.chosen is None:
        return None
    cand = res.chosen
    if cand.representation_id is not None:
        return cand.representation_id, cand.representation_kind
    text = cand.text
    rid = _insert_representation(
        ctx, sid, cand.representation_kind, text, cand.locator,
        snapshot_id, binding_label,
        {"proof_version": "g1-binding-v1", "status": "BOUND",
         "method": res.method, "requested_locator": key,
         "scope": cand.structural_scope, "candidate_count": 1,
         "chosen_candidate": cand.brief()})
    return rid, cand.representation_kind


def _bind_first_before(ctx: _Ctx, target: boe_diario.DiarioDoc,
                       target_boe: str, key: str, sid: str,
                       amap, snapshot_id: str
                       ) -> binding.BindingResult:
    """First-occurrence before: visual annex mapping, else hierarchical
    textual candidates in the target document (B1/B2)."""
    pages = amap.subject_pages(key) if amap else None
    if pages:
        rid = _image_representation(
            ctx, sid, target_boe, pages, amap,
            "ANCHORED_DERIVED" if amap.anchored else "UNANCHORED_DERIVED",
            {"rule": "alt sequence + /Pages order + embedded page "
                     "numbers",
             "anchors": len(amap.anchors),
             "anchors_matching": sum(
                 1 for a in amap.anchors if a["match"])})
        if rid is None:
            return binding.abstain(
                binding.NOT_PROVABLE, "ANNEX_PAGE_MAPPING", key,
                "image fetch failed")
        loc = conn_locator(ctx.conn, rid)
        cand = binding.Candidate(
            instrument_boe_id=target_boe, snapshot_id=snapshot_id,
            representation_kind="IMAGE", structural_scope="annex_pages",
            node_span=None, locator=loc, source="annex_page_mapping",
            representation_id=rid)
        return binding.BindingResult(
            binding.BOUND, "ANNEX_PAGE_MAPPING", key, 1, (cand,), cand,
            predecessor_representation_id=rid)
    spans: list[tuple[int, int]] = []
    if key.startswith("estado:"):
        spans = binding.annex_code_regions(target).get(key[7:], [])
    else:
        spans = binding.text_region_candidates(target, key)
    cands = [_xml_candidate(target, target_boe, sp, key, snapshot_id,
                            "locator resolved in target xml")
             for sp in spans]
    return binding.decide(cands, "UNIQUE_STRUCTURAL_TARGET", key)


# operative qualifiers that scope an operation below the locator model:
# a clause acting on a módulo/dimensión/cuadro/etc. targets an element
# the locator cannot express, so the recorded (parent) subject's
# representation is not what the operation touches (B3/§32)
_SUB_SCOPE_RE = re.compile(
    r"\b(?:m[oó]dulo|dimensi[oó]n|apartado|letra|punto|numeral|nota|"
    r"secci[oó]n|cuadro|tabla|p[aá]rrafo|[íi]ndice|fila|columna)\b",
    re.IGNORECASE)

# unmodelled ordinal qualifiers that make a recorded locator coarser
# than the actual subject: 'norma 64 bis', 'apartado 2.e)', 'punto 4 ter'
_QUALIFIER_SRC = r"(?:\.\s*[a-z]\b|\s+(?:bis|ter|qu[aá]ter|quinquies|" \
    r"sexies|septies|octies|nonies|decies)\b)"

_KIND_WORDS = {
    "apartado": r"apartados?", "letra": r"letras?", "punto": r"puntos?",
    "numeral": r"numerales?", "nota": r"notas?", "norma": r"normas?",
    "anejo": r"(?:anejos?|anexos?)", "seccion": r"secciones?",
    "indice": r"[íi]ndices?",
}


def _has_unmodelled_qualifier(masked: str, key: str) -> bool:
    """The recorded locator's mention carries a suffix the model cannot
    express — 'norma N ter', 'apartado N.x)' — so the real subject is a
    different (sub-)entity than the recorded parent locator."""
    for part in key.split("."):
        kind, _, val = part.partition(":")
        kind_rx = _KIND_WORDS.get(kind)
        if not val or kind_rx is None:
            continue
        vals = {re.escape(val)}
        if val.isdigit():
            vals |= {re.escape(w) for w, n in
                     operations._ORDINALS.items() if n == int(val)}
        pat = re.compile(rf"\b{kind_rx}\s+(?:{'|'.join(sorted(vals))})"
                         rf"{_QUALIFIER_SRC}", re.IGNORECASE)
        if pat.search(masked):
            return True
    return False


def _masked_clause(text: str) -> str:
    """Quoted spans blanked position-preserving — offsets in the result
    still index the original clause."""
    return operations._QUOTED_SPAN_RE.sub(
        lambda mm: " " * len(mm.group(0)), text)


def _seg_keys(raw: str, masked: str,
              op: operations.Operation) -> list[set[str]]:
    """Composed locator keys per sub-clause, with parser-style context
    threaded across segments ('en la norma 14 ... apartado 1 y a la
    letra b) del apartado 3': the second segment inherits 'norma 14')."""
    ctx = dict(op.context or {})
    out: list[set[str]] = []
    cursor = 0
    for seg in (s for s in operations._SEG_SPLIT_RE.split(masked)
                if s.strip()):
        start = masked.find(seg, cursor)
        raw_seg = raw[start:start + len(seg)]
        cursor = start + len(seg)
        seg_mentions = operations._extract_mentions(raw_seg)
        out.append({s.locator_key for s in
                    operations._compose_keys(seg_mentions, ctx)})
        ctx = operations._context_update(ctx, seg_mentions)
    return out


def _clause_scope_provable(op: operations.Operation, key: str) -> bool:
    """True when the clause demonstrably targets the recorded subject.

    The subject must be named by the clause's own locator mentions
    (inherited context composes them — 'se añade el apartado 4' under a
    'norma N' context composes the norma's apartado-4 key) and the
    sub-clauses governing THIS subject must not introduce operative
    qualifiers the locator cannot express — 'se suprimen las
    dimensiones «X»' under an anejo subject targets a dimension, not
    the anejo, so neither side of the anejo is provable. A qualifier in
    a different sub-clause ('primer párrafo del apartado 1 y a la letra
    b) del apartado 3') does not taint this subject.
    """
    mentions = operations._extract_mentions(op.clause_text)
    keys = {s.locator_key for s in
            operations._compose_keys(mentions, op.context)}
    if key not in keys:
        return False
    masked = _masked_clause(op.clause_text)
    if _has_unmodelled_qualifier(masked, key):
        return False
    key_kinds = {p.split(":", 1)[0] for p in key.split(".")}
    key_kinds |= {"norma", "anejo", "estado", "fichero", "disp",
                  "disposicion", "pagina"}
    segs = [s for s in operations._SEG_SPLIT_RE.split(masked)
            if s.strip()]
    zone = " ".join(s for s, ks in zip(segs, _seg_keys(
        op.clause_text, masked, op)) if key in ks) or masked
    return not any(m.group(0).lower() not in key_kinds
                   for m in _SUB_SCOPE_RE.finditer(zone))


def chain_update(chain: dict[str, "SubjectState"], key: str,
                 op_kind: str, after_status: str, after_id: str | None,
                 relation_id: str, literals) -> None:
    """Subject chain state transition (G1 §28).

    A proven operation whose new representation cannot be proven poisons
    the chain to UNKNOWN — the subject was verifiably replaced by
    something we cannot show, so a later non-ADD must not resurrect the
    old representation. Declared literal corrections do not replace
    representation identity and keep the proven state.
    """
    if op_kind == "DELETE":
        chain[key] = SubjectState("DELETED", None, relation_id)
    elif after_status == binding.BOUND:
        chain[key] = SubjectState("PRESENT", after_id, relation_id)
    elif op_kind == "SUBSTITUTE" or (
            op_kind in ("MODIFY", "CORRECT") and not literals):
        chain[key] = SubjectState("UNKNOWN", None, relation_id)
    elif op_kind == "ADD":
        chain[key] = SubjectState("UNKNOWN", None, relation_id)
    # MODIFY/CORRECT with declared literals keeps the proven state


def conn_locator(conn, rid: str) -> dict:
    row = conn.execute(
        "SELECT artifact_locator FROM representations"
        " WHERE representation_id=?", (rid,)).fetchone()
    return json.loads(row[0]) if row else {}


def _bind_annex_after(ctx: _Ctx, key: str, sid: str, mboe: str,
                      mdoc: boe_diario.DiarioDoc, snap: str,
                      modifier_map_getter) -> binding.BindingResult:
    """after from the modifier's own annex — only when the operation
    explicitly points there (B3/§20). Candidates are enumerated; a
    root-code span alone is NOT_PROVABLE, never silently elevated."""
    if key.startswith("fichero:"):
        spans = binding.fichero_spans(mdoc, key[8:])
        res = binding.decide(
            [_xml_candidate(mdoc, mboe, sp, key, snap,
                            "fichero description block in modifier annex")
             for sp in spans], "EXPLICIT_ANNEX_REFERENCE", key)
        if res.status != binding.NOT_FOUND:
            return res
    code = (key[7:] if key.startswith("estado:")
            else key[6:] if key.startswith("anejo:") else None)
    if code:
        regions = binding.annex_code_regions(mdoc)
        spans = regions.get(code, [])
        res = binding.decide(
            [_xml_candidate(mdoc, mboe, sp, key, snap,
                            "estado code header in modifier annex")
             for sp in spans], "EXPLICIT_ANNEX_REFERENCE", key)
        if res.status != binding.NOT_FOUND:
            return res
        root = annexmap.estado_root(code)
        if root != code and regions.get(root):
            return binding.abstain(
                binding.NOT_PROVABLE, "EXPLICIT_ANNEX_REFERENCE", key,
                "only broader root annex span provable")
    # visual fallback inside the modifier annex (deterministic page map)
    mmap = modifier_map_getter()
    if mmap is not None:
        mpages = mmap.subject_pages(key)
        if mpages:
            rid = _image_representation(
                ctx, sid, mboe, mpages, mmap, "UNANCHORED_DERIVED",
                {"rule": "modifier annex images; no independent anchors",
                 "anchors": 0})
            if rid is None:
                return binding.abstain(
                    binding.NOT_PROVABLE, "MODIFIER_ANNEX_PAGES", key,
                    "image fetch failed")
            cand = binding.Candidate(
                instrument_boe_id=mboe, snapshot_id=snap,
                representation_kind="IMAGE",
                structural_scope="modifier_annex_pages", node_span=None,
                locator=conn_locator(ctx.conn, rid),
                source="modifier_annex_page_mapping",
                representation_id=rid)
            return binding.BindingResult(
                binding.BOUND, "MODIFIER_ANNEX_PAGES", key, 1,
                (cand,), cand)
        return binding.abstain(
            binding.NOT_FOUND, "MODIFIER_ANNEX_PAGES", key,
            "no annex candidates")
    return binding.abstain(binding.NOT_FOUND, "EXPLICIT_ANNEX_REFERENCE",
                         key, "no annex candidates")


def _subject_owns_content(op: operations.Operation, key: str,
                          pos: int) -> bool:
    """The content pointer (or inline quote) at *pos* is owned by the
    subject mentioned in its own sub-clause. In a mixed clause —
    'en la letra a) se sustituye X; se modifica la letra c) y se añade
    la letra e), que quedan redactadas' — the quoted block belongs to
    c)/e), not a) (B3/§18). When the pointer's segment names no
    subject, ownership falls to the nearest preceding subject segment.
    """
    masked = _masked_clause(op.clause_text)
    segs = [s for s in operations._SEG_SPLIT_RE.split(masked)
            if s.strip()]
    seg_keys = _seg_keys(op.clause_text, masked, op)
    cursor = 0
    pointer_seg = len(segs) - 1
    for i, seg in enumerate(segs):
        start = masked.find(seg, cursor)
        if start <= pos < start + len(seg):
            pointer_seg = i
        cursor = start + len(seg)
    owner = pointer_seg
    while owner >= 0 and not seg_keys[owner]:
        owner -= 1
    return owner >= 0 and key in seg_keys[owner]


def _bind_content_after(ctx: _Ctx, key: str, sid: str, mboe: str,
                        mdoc: boe_diario.DiarioDoc,
                        op: operations.Operation,
                        snap: str) -> binding.BindingResult:
    """after from operation-owned content only (B3). A modifier-global
    lookup for the same locator is never used."""
    method = op.content_link_method
    s, e = op.content_span
    if method in ("INLINE_QUOTED_CONTENT", "EXPLICIT_FOLLOWING_CONTENT"):
        masked = _masked_clause(op.clause_text)
        pm = operations._CONTENT_POINTER_RE.search(masked)
        pos = pm.start() if pm else len(masked)
        if method == "INLINE_QUOTED_CONTENT" and op.inline_content:
            qp = op.clause_text.find(op.inline_content)
            if qp >= 0:
                pos = qp
        if not _subject_owns_content(op, key, pos):
            return binding.abstain(
                binding.NOT_PROVABLE, "CONTENT_POINTER_SCOPE", key,
                "following content is governed by a different "
                "sub-clause")
    if method == "INLINE_QUOTED_CONTENT":
        kind_, text = "TEXT", op.inline_content
        ns = op.node_index if text else s
        if e > s:
            kind_, span_text = region_text(mdoc, (s, e))
            text = "\n".join(t for t in (text, span_text) if t)
        cand = binding.Candidate(
            instrument_boe_id=mboe, snapshot_id=snap,
            representation_kind=kind_, structural_scope=key,
            node_span=(ns, e),
            locator={"instrument": mboe, "type": "xml_nodes",
                     "node_span": [ns, e]},
            source="operation inline quoted content", text=text)
        return binding.BindingResult(
            binding.BOUND, "INLINE_QUOTED_CONTENT", key, 1,
            (cand,), cand)
    if method == "EXPLICIT_FOLLOWING_CONTENT":
        kind_, text = region_text(mdoc, (s, e))
        if not text.strip():
            return binding.abstain(
                binding.NOT_PROVABLE, "EXPLICIT_FOLLOWING_CONTENT", key,
                "empty content span")
        cand = binding.Candidate(
            instrument_boe_id=mboe, snapshot_id=snap,
            representation_kind=kind_, structural_scope=key,
            node_span=(s, e),
            locator={"instrument": mboe, "type": "xml_nodes",
                     "node_span": [s, e]},
            source="operation following content span", text=text)
        return binding.BindingResult(
            binding.BOUND, "EXPLICIT_FOLLOWING_CONTENT", key, 1,
            (cand,), cand)
    if method == "DECLARED_LITERAL_ONLY":
        return binding.abstain(
            binding.NOT_PROVABLE, "DECLARED_LITERAL_ONLY", key,
            "declared literals; no full replacement representation")
    return binding.abstain(
        binding.NOT_PROVABLE, "NO_PROVEN_CONTENT", key,
        "no operation-owned content link")


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
    ctx.annex_pdf_snap[boe_id] = pdf_art.snapshot_id
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
    _record_parse(ctx, xml_art.snapshot_id, target_res.parse_status,
                  target_res.parse_error)
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
            _anomaly(ctx, ANOMALY_FETCH, None, {"modifier": boe_id})
            parsed_mods.append({"boe_id": boe_id, "kind": kind, "ref": ref,
                                "doc": None, "ops": [], "snapshot": None})
            continue
        mres = boe_diario.parse_diario(art.body)
        _record_parse(ctx, art.snapshot_id, mres.parse_status,
                      mres.parse_error)
        if mres.parse_status != boe_diario.COMPLETE or not mres.doc:
            _anomaly(ctx, ANOMALY_PARSE, art.snapshot_id,
                     {"modifier": boe_id, "parse": mres.parse_error})
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
            _anomaly(ctx, ANOMALY_OUT_OF_TARGET, art.snapshot_id,
                     {"modifier": boe_id,
                      "count": result.out_of_target_ops})
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
    if amap:
        for a in amap.anchors:
            if not a["match"]:
                _anomaly(ctx, ANOMALY_ANCHOR,
                         ctx.annex_pdf_snap.get(target_boe_id), a)

    # --- relations -----------------------------------------------------------
    ordered = sorted(
        (pm for pm in parsed_mods if pm["doc"] is not None),
        key=lambda pm: (pm["pub"], pm["boe_id"]))
    chain: dict[str, SubjectState] = {}
    stats = {"relations": 0, "representations": 0}

    _ABSTENTION_ANOMALY = {
        binding.AMBIGUOUS: ANOMALY_AMBIGUOUS,
        binding.NOT_FOUND: ANOMALY_BIND_NOT_FOUND,
        binding.NOT_PROVABLE: ANOMALY_NOT_PROVABLE,
    }

    def _abstention_anomaly(res: binding.BindingResult, side: str,
                            op_kind: str, mboe: str, snap,
                            clause: str) -> None:
        kind = _ABSTENTION_ANOMALY.get(res.status)
        if kind is None:
            return
        _anomaly(ctx, kind, snap, {
            "subject": res.locator_key, "modifier": mboe, "side": side,
            "operation_kind": op_kind,
            "candidate_count": res.candidate_count,
            "candidates": [c.brief() for c in res.candidates][:5],
            "reason": res.reason, "clause": clause[:200]})

    for pm in ordered:
        mboe = pm["boe_id"]
        mdoc = pm["doc"]
        modifier_map: annexmap.AnnexMap | None = None
        modifier_map_done = False

        def _mmap_getter():
            nonlocal modifier_map, modifier_map_done
            if not modifier_map_done:
                modifier_map_done = True
                modifier_map = _target_annex_map(ctx, mboe, mdoc)
            return modifier_map

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
                scope_provable = _clause_scope_provable(op, key)

                # ----- before binding (G1 §15) -------------------------------
                before_id = None
                before_kind = None
                if op_kind == "ADD":
                    bres = binding.BindingResult(
                        binding.NOT_APPLICABLE, "ADD_NO_BEFORE", key, 0)
                elif not scope_provable:
                    bres = binding.abstain(
                        binding.NOT_PROVABLE, "SUBJECT_SCOPE", key,
                        "clause scopes below the recorded subject "
                        "locator")
                elif key in chain:
                    st = chain[key]
                    if st.status == "PRESENT" \
                            and st.representation_id:
                        row = conn.execute(
                            "SELECT representation_kind, artifact_locator"
                            " FROM representations"
                            " WHERE representation_id=?",
                            (st.representation_id,)).fetchone()
                        cand = binding.Candidate(
                            instrument_boe_id=target_boe_id,
                            snapshot_id=None,
                            representation_kind=row[0] if row else "TEXT",
                            structural_scope="chain_predecessor",
                            node_span=None,
                            locator=json.loads(row[1]) if row else {},
                            source="chain predecessor after",
                            representation_id=st.representation_id)
                        bres = binding.BindingResult(
                            binding.BOUND, "CHAIN_PREDECESSOR", key, 1,
                            (cand,), cand,
                            predecessor_relation_id=st.relation_id,
                            predecessor_representation_id=
                            st.representation_id)
                        before_id = st.representation_id
                        before_kind = row[0] if row else None
                    elif st.status == "DELETED":
                        bres = binding.abstain(
                            binding.NOT_PROVABLE, "CHAIN_STATE", key,
                            "subject state DELETED; non-ADD cannot "
                            "resurrect the old representation")
                        _anomaly(ctx, ANOMALY_CHAIN, pm["snapshot"],
                                 {"subject": key, "modifier": mboe,
                                  "operation_kind": op_kind,
                                  "reason": "deleted_state"})
                    else:
                        bres = binding.abstain(
                            binding.NOT_PROVABLE, "CHAIN_STATE", key,
                            "subject state UNKNOWN; predecessor "
                            "representation not provable")
                        _anomaly(ctx, ANOMALY_CHAIN, pm["snapshot"],
                                 {"subject": key, "modifier": mboe,
                                  "operation_kind": op_kind,
                                  "reason": "unknown_state"})
                else:
                    bres = _bind_first_before(
                        ctx, target, target_boe_id, key, sid, amap,
                        xml_art.snapshot_id)
                    m = _materialize(ctx, sid, bres, key,
                                     xml_art.snapshot_id)
                    if m:
                        before_id, before_kind = m

                # ----- after binding (G1 §17–20) -----------------------------
                after_id = None
                after_kind = None
                if op_kind == "DELETE":
                    ares = binding.BindingResult(
                        binding.NOT_APPLICABLE, "DELETE_NO_AFTER",
                        key, 0)
                elif not scope_provable:
                    ares = binding.abstain(
                        binding.NOT_PROVABLE, "SUBJECT_SCOPE", key,
                        "clause scopes below the recorded subject "
                        "locator")
                elif op.annex_ref:
                    ares = _bind_annex_after(
                        ctx, key, sid, mboe, mdoc, pm["snapshot"],
                        _mmap_getter)
                    m = _materialize(ctx, sid, ares, key, pm["snapshot"])
                    if m:
                        after_id, after_kind = m
                else:
                    ares = _bind_content_after(
                        ctx, key, sid, mboe, mdoc, op, pm["snapshot"])
                    m = _materialize(ctx, sid, ares, key, pm["snapshot"])
                    if m:
                        after_id, after_kind = m

                _abstention_anomaly(bres, "before", op_kind, mboe,
                                    pm["snapshot"], op.clause_text)
                _abstention_anomaly(ares, "after", op_kind, mboe,
                                    pm["snapshot"], op.clause_text)

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

                rid = modification_relation_id(
                    mboe, key, op.clause_text, before_id, after_id)
                resolution, resolution_notes = _resolution(
                    op_kind, bres.status, ares.status, literals)
                if resolution == "UNRESOLVED":
                    _anomaly(ctx, ANOMALY_UNBOUND, pm["snapshot"],
                             {"subject": key, "modifier": mboe,
                              "operation_kind": op_kind,
                              "relation_id": rid,
                              "clause": op.clause_text[:200]})

                proof = {"version": "g1-binding-v1",
                         "before": bres.proof, "after": ares.proof}
                conn.execute(
                    "INSERT OR IGNORE INTO modification_relations"
                    " (relation_id, kind, operation_kind, target_subject_id,"
                    " modifier_instrument_id, locator_raw, relation_raw,"
                    " before_representation_id, after_representation_id,"
                    " publication_date, instrument_effective_date,"
                    " declared_literals,"
                    " diff_levels, resolution, resolution_notes,"
                    " source_snapshot_ids, parser_name, parser_version,"
                    " binding_proof)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, pm["kind"], op_kind, sid,
                     instrument_id(mboe), op.clause_text, pm["ref"].texto,
                     before_id, after_id, pm["pub"],
                     pm["vigencia"] if pm["kind"] == "MODIFICATION" else None,
                     json.dumps(literals, ensure_ascii=False)
                     if literals else None,
                     json.dumps(levels), resolution,
                     resolution_notes,
                     json.dumps(snaps), PARSER_NAME, PARSER_VERSION,
                     _canonical_json(proof)))
                stats["relations"] += 1

                # ----- chain update (G1 §27–28) ------------------------------
                if not scope_provable:
                    # a proven operation on an unrepresentable
                    # sub-element: the subject's representation changed
                    # in a way we cannot show (it is NOT deleted, even
                    # for a sub-element DELETE)
                    chain[key] = SubjectState("UNKNOWN", None, rid)
                else:
                    chain_update(chain, key, op_kind, ares.status,
                                 after_id, rid, literals)

    _persist_anomalies(ctx)
    stats["representations"] = conn.execute(
        "SELECT COUNT(*) FROM representations").fetchone()[0]
    stats["subjects"] = conn.execute(
        "SELECT COUNT(*) FROM subjects").fetchone()[0]
    stats["instruments"] = conn.execute(
        "SELECT COUNT(*) FROM instruments").fetchone()[0]
    stats["instrument_relations"] = conn.execute(
        "SELECT COUNT(*) FROM instrument_relations").fetchone()[0]
    stats["anomaly_count"] = conn.execute(
        "SELECT COUNT(*) FROM anomalies").fetchone()[0]
    return {
        "target": target_boe_id,
        "modifiers": [{"boe_id": b, "kind": k} for b, k, _ in modifiers],
        "target_annex_anchored": bool(amap and amap.anchored),
        "anchors": len(amap.anchors) if amap else 0,
        "fetch_errors": ctx.acquirer.errors,
        "anomalies": _unique_anomalies(ctx.anomalies),
        **stats,
    }
