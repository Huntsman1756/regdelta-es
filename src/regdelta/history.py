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

from . import annexmap, binding, operations, ownership
from .http import LIVE_FETCH
from .profile import active_profile
from .rawstore import store_blob
from .document import DiarioDoc
from .sources import boe_diario, boe_doc, boe_pdf
from .util import canonical_date, sha256_hex, sha256_hex_text

PARSER_NAME = "history"
PARSER_VERSION = "v5"


def _sd():
    """F8 source descriptors: acquisition endpoints and source ids."""
    return active_profile().source_descriptors

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


def region_text(doc: DiarioDoc,
                span: tuple[int, int]) -> tuple[str, str]:
    """(kind, serialized text) for a node span: TABLE iff it contains a
    table node, else TEXT."""
    texts: list[str] = []
    has_table = False
    tbl = active_profile().document_model.kinds["table"]
    for i in range(*span):
        n = doc.nodes[i]
        if n.kind == tbl:
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
        if a:
            return "RESOLVED", None
        return (("PARTIAL", f"after: {after_status}") if has_lit
                else ("UNRESOLVED", f"after: {after_status}"))
    if op_kind == "DELETE":
        if b:
            return "RESOLVED", None
        return (("PARTIAL", f"before: {before_status}") if has_lit
                else ("UNRESOLVED", f"before: {before_status}"))
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
    annex_pdf_sha: dict = field(default_factory=dict)
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
                       doc: DiarioDoc | None,
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
                                 doc: DiarioDoc,
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
                          "INDICE", "DISPOSICION", "NOTA", "INSTRUMENT",
                          "NUMERO", "LETRA", "NUMERAL", "SECCION",
                          "CAPITULO", "PARRAFO", "GUION")
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
        sd = _sd()
        pname, pver = sd.imagen_parser
        art = ctx.acquirer.get("boe_imagen", sd.base_url + src,
                               sd.media_types["boe_imagen"],
                               pname, pver, ctx.checked_at)
        if art is None:
            return None
        snaps.append(art.snapshot_id)
        entries.append({"boe_page": page, "img_alt": alt,
                        "url": sd.base_url + src,
                        "blob_sha256": art.blob_sha256})
    if not entries:
        return None
    locator = {"instrument": boe_id, "type": "image_pages", "pages": entries}
    evidence = dict(anchor_note)
    evidence["image_snapshots"] = snaps
    # WS-D: the signed diario PDF embeds the annex figures as vector
    # content — byte equality with the served PNGs is impossible
    # (EXP-D1 falsified it). The deterministic association is still
    # provable: record it as evidence, never as identity.
    pdf_idx = {p.boe_page: p.pdf_index for p in amap.pages}
    evidence["pdf_anchor"] = {
        "sha256": ctx.annex_pdf_sha.get(boe_id),
        "page_indexes": [pdf_idx.get(e["boe_page"]) for e in entries],
        "relation": "ASSOCIATION_ONLY",
    }
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


# ---------------------------------------------------------------------------
# CORE-GAP WS-A — redesignation edges
#
# An old_locator -> new_locator continuity edge is emitted only when the
# clause demonstrably declares BOTH endpoints and the pairing is
# unambiguous. Paths locate; the edge carries continuity — never a
# locator mutation, never a positional heuristic. Every refusal is
# journaled as REDESIGNATION_REFUSED; nothing is guessed.
# ---------------------------------------------------------------------------

def _emit_redesignation_edges(ctx: _Ctx, conn, pm, op, entries,
                              chain: dict[str, "SubjectState"],
                              target_boe_id: str,
                              xml_snapshot_id: str) -> None:
    """Emit subject_redesignations rows for one clause's paired
    CODE_REDESIGNATION subjects (per-subject refusal, never guessed).
    ``entries`` is a list of ``(subject, declaration, pair)`` where
    ``pair`` comes from ``operations.redesignation_pairs``."""
    mboe = pm["boe_id"]

    def refuse(reason, sub=None):
        _anomaly(ctx, "REDESIGNATION_REFUSED", pm["snapshot"], {
            "modifier": mboe, "clause": op.clause_text[:200],
            "node_index": op.node_index, "reason": reason,
            "subject": sub.locator_key if sub else None,
            "subjects": [s.locator_key for s, _, _ in entries],
            "destinations": [
                dict(p["dest"]) if isinstance(p["dest"], dict)
                else list(p["dest"]) if p["dest"] is not None else None
                for _, _, p in entries]})

    # pass 1 — validate every pair into an emission plan (per-subject
    # refusal, never guessed)
    plan: list[tuple] = []
    new_keys: set[str] = set()
    for sub, decl, pair in entries:
        old_key = sub.locator_key
        new_key = pair["new_key"]
        if new_key is None:
            refuse("destination_not_anchored", sub)
            continue
        if new_key == old_key:
            refuse("self_redesignation", sub)
            continue
        if new_key in new_keys:
            refuse("new_key_collision", sub)
            continue
        st_new = chain.get(new_key)
        if st_new is not None and st_new.status == "PRESENT":
            # both keys have proven independent existence — merging
            # would fabricate identity; refuse the edge
            refuse("destination_already_exists", sub)
            continue
        plan.append((sub, decl, pair))
        new_keys.add(new_key)

    # chained edges (a->b, b->c) migrate the ORIGINAL old-chain state,
    # so the last link applies first; a cycle (a->b, b->a) has no safe
    # sequential order — fail closed
    pending = list(plan)
    order: list[tuple] = []
    while pending:
        olds = {p[0].locator_key for p in pending}
        nxt = [p for p in pending if p[2]["new_key"] not in olds]
        if not nxt:
            break
        order.extend(nxt)
        pending = [p for p in pending if p not in nxt]
    cyclic = {p[0].locator_key for p in pending}

    edge_ids: dict = {}
    for sub, decl, pair in plan:
        old_key = sub.locator_key
        new_key = pair["new_key"]
        dest = pair["dest"]
        if old_key in cyclic:
            refuse("redesignation_cycle", sub)
            continue
        new_sid = _upsert_subject(
            ctx, target_boe_id, new_key,
            new_key.replace(":", " "),
            new_key.rsplit(":", 1)[0].rsplit(".", 1)[-1].upper())
        edge_id = sha256_hex((
            "redesig|" + target_boe_id + "|" + mboe + "|" + old_key
            + "|" + new_key + "|" + op.clause_text + "|"
            + str(op.node_index)).encode("utf-8"))
        proof = {
            "version": "core-gap-redesig-v1",
            "clause": op.clause_text,
            "node_index": op.node_index,
            "pairing": "ORDERED_N_TO_N" if len(entries) > 1
            else "SINGLE",
            "destination": (
                dict(dest) if isinstance(dest, dict)
                else {"kind": dest[0], "value": dest[1]}),
            "locator_declaration": {
                "status": decl.status,
                "locator_key": decl.locator_key,
                "source_node_index": decl.source_node_index,
                "components": [list(c) for c in decl.components],
                "method": decl.method},
            "old_chain_state": (
                chain[old_key].status if old_key in chain
                else "NO_PRIOR_STATE")}
        old_state = chain.get(old_key)
        conn.execute(
            "INSERT OR IGNORE INTO subject_redesignations"
            " (edge_id, target_instrument_id,"
            " modifier_instrument_id, old_locator_key,"
            " new_locator_key, old_subject_id, new_subject_id,"
            " clause_text, node_index, publication_date,"
            " resolution, edge_proof, source_snapshot_ids,"
            " parser_name, parser_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (edge_id, instrument_id(target_boe_id),
             instrument_id(mboe), old_key, new_key,
             subject_id(target_boe_id, old_key),
             new_sid, op.clause_text, op.node_index, pm["pub"],
             "RESOLVED" if old_state is not None
             and old_state.status == "PRESENT" else "DECLARED",
             _canonical_json(proof),
             json.dumps([pm["snapshot"], xml_snapshot_id]),
             PARSER_NAME, PARSER_VERSION))
        edge_ids[(old_key, new_key)] = edge_id
        pm["inventory"]["redesignation_edges"] += 1
    # migrate in topological order (``order`` holds the plan tuples of
    # every acyclic edge, chain-end first)
    for sub, _decl, pair in order:
        old_key, new_key = sub.locator_key, pair["new_key"]
        edge_id = edge_ids[(old_key, new_key)]
        # continuity: the new address inherits the old state; the old
        # address is tombstoned — a later clause that still addresses
        # it must abstain (CHAIN_DISCONTINUITY)
        chain[new_key] = chain.pop(
            old_key, SubjectState("UNKNOWN", None, edge_id))
        chain[old_key] = SubjectState("DELETED", None, edge_id)


def _xml_candidate(doc: DiarioDoc, boe: str,
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


def _bind_first_before(ctx: _Ctx, target: DiarioDoc,
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


# clause/locator qualifier helpers live in operations (shared with the
# ownership layer); keep the history-local names as aliases
_has_unmodelled_qualifier = operations._has_unmodelled_qualifier
_masked_clause = operations._masked_clause


def _seg_keys(raw: str, masked: str,
              op: operations.Operation) -> list[set[str]]:
    """Composed locator keys per sub-clause, with parser-style context
    threaded across segments ('en la norma 14 ... apartado 1 y a la
    letra b) del apartado 3': the second segment inherits 'norma 14')."""
    ctx = dict(op.context or {})
    out: list[set[str]] = []
    cursor = 0
    for seg in (s for s in active_profile().operative_grammar
                .segment_split.split(masked) if s.strip()):
        start = masked.find(seg, cursor)
        raw_seg = raw[start:start + len(seg)]
        cursor = start + len(seg)
        seg_mentions = operations._extract_mentions(raw_seg)
        out.append({s.locator_key for s in
                    operations._compose_keys(seg_mentions, ctx,
                                             clause_text=raw_seg)})
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
            operations._compose_keys(mentions, op.context,
                                     clause_text=op.clause_text)}
    if key not in keys:
        return False
    masked = _masked_clause(op.clause_text)
    if _has_unmodelled_qualifier(masked, key):
        return False
    key_kinds = {p.split(":", 1)[0] for p in key.split(".")}
    key_kinds |= {"norma", "anejo", "estado", "fichero", "disp",
                  "disposicion", "pagina"}
    segs = [s for s in active_profile().operative_grammar
            .segment_split.split(masked) if s.strip()]
    zone = " ".join(s for s, ks in zip(segs, _seg_keys(
        op.clause_text, masked, op)) if key in ks) or masked
    return not any(
        _scope_word_kind(m.group(0), key_kinds, key) not in key_kinds
        for m in active_profile().operative_grammar.sub_scope
        .finditer(zone))


def _scope_word_kind(word: str, key_kinds: set, key: str) -> str:
    """Map a sub_scope surface word to the locator kind it names —
    accent and plural tolerant so 'sección' suppresses only keys
    without a seccion component and 'párrafos' reads as 'parrafo'.

    Applies the composer's anejo normalization: numbered units inside
    an anejo are 'punto' whatever the clause calls them, so 'número 3
    de la Memoria (Anexo 3)' is represented by key kind 'punto'.
    """
    w = operations._norm(word)
    for cand in (w, w[:-1], w[:-2]):
        if cand in key_kinds:
            return cand
    head = key.split(".", 1)[0].split(":", 1)[0]
    if head in ("anejo", "anexo") and w in (
            "numero", "numeros", "apartado", "apartados") \
            and "punto" in key_kinds:
        return "punto"
    return w


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
                      mdoc: DiarioDoc, snap: str,
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
    segs = [s for s in active_profile().operative_grammar
            .segment_split.split(masked) if s.strip()]
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


def _fichero_norm(text: str) -> str:
    fg = active_profile().annex_state.fichero
    t = fg.dash_collapse.sub("-", operations._norm(text))
    return fg.note_strip.sub("", t)


def _fichero_tokens(text: str) -> tuple[str, ...]:
    fg = active_profile().annex_state.fichero
    return tuple(t for t in re.split(fg.token_split_norm,
                                     _fichero_norm(text))
                 if t and t not in fg.connectors)


def _span_covers_subject(key: str, text: str) -> bool:
    """Frozen-oracle coverage: a TEXT/TABLE binding is provable only
    when the span restates the subject's distinguishing token for
    sub-locator keys and code-kind locators. Whole-subject replacements
    need not restate their heading."""
    head = key.split(":", 1)[0].split(".", 1)[0]
    token = operations._norm(key.split(":")[-1])
    if head == "fichero":
        return _fichero_norm(token) in _fichero_norm(text) or all(
            t in _fichero_tokens(text)
            for t in _fichero_tokens(token))
    has_sub = any(":" in p for p in key.split(".")[1:])
    if not has_sub and head not in \
            active_profile().locator_grammar.coverage_heads:
        return True
    alts = {token, token.replace(".", " ")}
    if head in ("norma", "anejo", "anexo", "disp", "disposicion") \
            and token.isdigit():
        alts |= {operations._norm(w) for w, v in
                 active_profile().locator_grammar.ordinals.items()
                 if v == int(token)}
    tnorm = operations._norm(text)
    return any(a in tnorm for a in alts if a)


def _bind_content_after(ctx: _Ctx, key: str, sid: str, mboe: str,
                        mdoc: DiarioDoc,
                        op: operations.Operation,
                        snap: str) -> binding.BindingResult:
    """after from operation-owned content only (B3). A modifier-global
    lookup for the same locator is never used."""
    method = op.content_link_method
    s, e = op.content_span
    if method in ("INLINE_QUOTED_CONTENT", "EXPLICIT_FOLLOWING_CONTENT"):
        masked = _masked_clause(op.clause_text)
        pm = active_profile().operative_grammar.content_pointer \
            .search(masked)
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
        # the claim covers whole nodes: the recorded text must be the
        # serialization of exactly the claimed span, not only the
        # quoted payload embedded in the clause node
        ns = op.node_index if op.inline_content else s
        kind_, text = region_text(mdoc, (ns, e))
        cand = binding.Candidate(
            instrument_boe_id=mboe, snapshot_id=snap,
            representation_kind=kind_, structural_scope=key,
            node_span=(ns, e),
            locator={"instrument": mboe, "type": "xml_nodes",
                     "node_span": [ns, e]},
            source="operation inline quoted content", text=text)
        if not _span_covers_subject(key, text):
            return binding.abstain(
                binding.NOT_PROVABLE, "COVERAGE_NOT_PROVABLE", key,
                "bound span does not restate the subject locator")
        return binding.BindingResult(
            binding.BOUND, "INLINE_QUOTED_CONTENT", key, 1,
            (cand,), cand)
    if method == "EXPLICIT_FOLLOWING_CONTENT":
        kind_, text = region_text(mdoc, (s, e))
        if not text.strip():
            return binding.abstain(
                binding.NOT_PROVABLE, "EXPLICIT_FOLLOWING_CONTENT", key,
                "empty content span")
        if not _span_covers_subject(key, text):
            return binding.abstain(
                binding.NOT_PROVABLE, "COVERAGE_NOT_PROVABLE", key,
                "bound span does not restate the subject locator")
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
                      doc: DiarioDoc) -> annexmap.AnnexMap | None:
    if boe_id in ctx.annex_maps:
        return ctx.annex_maps[boe_id]
    sd = _sd()
    doc_art = ctx.acquirer.get(
        "boe_doc", sd.url_templates["doc_html"].format(boe=boe_id),
        sd.media_types["boe_doc"], boe_doc.PARSER_NAME,
        boe_doc.PARSER_VERSION, ctx.checked_at)
    pdf_url = doc.metadata.get("url_pdf") or ""
    if pdf_url.startswith("/"):
        pdf_url = sd.base_url + pdf_url
    if not pdf_url:
        pub = canonical_date(doc.metadata.get("fecha_publicacion", "") or "")
        if pub:
            y, m, d = pub.split("-")
            pdf_url = sd.url_templates["dias_pdf"].format(
                y=y, m=m, d=d, boe=boe_id)
    pdf_art = None
    if pdf_url:
        pdf_art = ctx.acquirer.get(
            "boe_pdf", pdf_url,
            sd.media_types["boe_pdf"], boe_pdf.PARSER_NAME,
            boe_pdf.PARSER_VERSION, ctx.checked_at)
    if doc_art is None or pdf_art is None:
        ctx.annex_maps[boe_id] = None
        return None
    images = boe_doc.parse_doc_images(doc_art.body)
    ctx.doc_images[boe_id] = images
    ctx.annex_pdf_snap[boe_id] = pdf_art.snapshot_id
    ctx.annex_pdf_sha[boe_id] = pdf_art.blob_sha256
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

    sd = _sd()
    xml_art = ctx.acquirer.get(
        "boe_diario",
        sd.url_templates["diario_xml"].format(boe=target_boe_id),
        sd.media_types["boe_diario"], boe_diario.PARSER_NAME,
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

    m = active_profile().identity_reference.circular_ref.search(
        target.metadata.get("titulo", ""))
    target_ref = (int(m.group(1)), int(m.group(2))) if m else None

    # --- modifier discovery -------------------------------------------------
    posteriores = target.posteriores
    modifiers = []          # (boe_id, kind, ref)
    corr_pal = active_profile().identity_reference.correction_palabras
    for ref in posteriores:
        kind = ("CORRECTION"
                if any(w in ref.palabra.upper() for w in corr_pal)
                else "MODIFICATION")
        modifiers.append((ref.referencia, kind, ref))

    # --- parse every modifier first: correction anchors feed the target map -
    parsed_mods: list[dict] = []
    anchors: list[tuple[int, str]] = []
    for boe_id, kind, ref in modifiers:
        art = ctx.acquirer.get(
            "boe_diario",
            sd.url_templates["diario_xml"].format(boe=boe_id),
            sd.media_types["boe_diario"], boe_diario.PARSER_NAME,
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
        # G2.1 §10-15: the parser describes every candidate operation
        # target-agnostically; the ownership layer then attributes each
        # operation to an instrument — the reconstructed target never
        # disambiguates a tie
        result = operations.parse_all_operations(mdoc)
        attributed = [(op, ownership.attribute_operation(
            op, mdoc, target_ref, target_boe_id))
            for op in result.operations]
        parsed_mods.append({"boe_id": boe_id, "kind": kind, "ref": ref,
                            "doc": mdoc, "ops": attributed,
                            "snapshot": art.snapshot_id,
                            "pub": canonical_date(
                                mdoc.metadata.get("fecha_publicacion", "")
                                or ""),
                            "vigencia": canonical_date(
                                mdoc.metadata.get("fecha_vigencia") or "")})
        if kind == "CORRECTION":
            # correction anchors only come from operations proven to
            # belong to this target (G2.1 §15.B)
            for op, att in attributed:
                if att.status != ownership.TARGET_PROVEN:
                    continue
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

    def _emit_redesignations(pm, op, entries):
        _emit_redesignation_edges(
            ctx, conn, pm, op, entries, chain, target_boe_id,
            xml_art.snapshot_id)

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

        # §44 operation-inventory accounting: every leaf operation ends
        # in exactly one attribution disposition
        pm["inventory"] = {
            "leaf_operations_parsed": 0, "relations_emitted": 0,
            "redesignation_edges": 0,
            **{s: 0 for s in ownership.ATTRIBUTION_STATUSES}}

        for op, att in pm["ops"]:
            if op.is_container:
                continue
            pm["inventory"]["leaf_operations_parsed"] += 1
            pm["inventory"][att.status] += 1
            # §17 emission gate: only TARGET_PROVEN operations may
            # become target-owned relations — no subject row,
            # representation, relation, lifecycle or chain mutation
            # otherwise (§50). Non-proven dispositions are correct
            # abstentions, journaled in the operation inventory — not
            # anomalies.
            if att.status != ownership.TARGET_PROVEN:
                continue
            # WS-C: anonymous/positional items the key model could not
            # capture are journaled — the op's best anchor stays
            # visible in accounting, never silently absorbed
            for uk in op.unkeyed:
                _anomaly(ctx, "UNKEYED_ANONYMOUS_ITEM",
                         pm["snapshot"], {
                             "modifier": mboe,
                             "clause": op.clause_text[:200],
                             "node_index": op.node_index,
                             "kind": uk})
            # CORE-GAP WS-A: positional subject→destination pairing for
            # structural redesignations. CODE_REDESIGNATION pairs become
            # continuity edges (no ordinary relation); RELABEL pairs and
            # non-structural 'pasa a ser' keep their baseline operation;
            # UNPROVABLE pairs are journaled refusals — a subject whose
            # baseline kind is not REDESIGNATE still emits its ordinary
            # relation, one whose kind is REDESIGNATE (profile-level
            # abstention vocabulary) emits nothing.
            edge_pairs: dict = {}
            paired_keys: set = set()
            for p in operations.redesignation_pairs(
                    op.clause_text, op.subjects):
                skey = p["subject"].locator_key
                paired_keys.add(skey)
                if p["cls"] == "CODE_REDESIGNATION":
                    edge_pairs[skey] = p
                elif p["cls"] == "UNPROVABLE":
                    _anomaly(ctx, "REDESIGNATION_REFUSED",
                             pm["snapshot"], {
                                 "modifier": mboe,
                                 "clause": op.clause_text[:200],
                                 "node_index": op.node_index,
                                 "reason": "destination_unprovable",
                                 "subject": skey,
                                 "verb_pos": p["verb_start"]})
            redesig_pending: list = []
            for sub in op.subjects:
                key = sub.locator_key
                # O2: the operation must demonstrably declare this
                # locator in its governing scope (§20); an unproven
                # locator is likewise a silent abstention
                decl = ownership.prove_locator(op, sub)
                if decl.status != ownership.LOC_PROVEN:
                    continue
                sid = _upsert_subject(ctx, target_boe_id, key, sub.label,
                                      sub.kind)
                op_kind = operations.subject_operation_kind(
                    op.clause_text, key, op.operation_kind)
                pair = edge_pairs.get(key)
                if pair is not None:
                    # WS-A: continuity is an edge, not a relation —
                    # collect the clause's redesignation subjects and
                    # emit them together
                    redesig_pending.append((sub, decl, pair))
                    continue
                if op_kind == "REDESIGNATE":
                    # a profile-level redesignation subject with no
                    # provable pair — abstain (never emit a locator
                    # the clause did not declare as subject)
                    if key not in paired_keys:
                        _anomaly(ctx, "REDESIGNATION_REFUSED",
                                 pm["snapshot"], {
                                     "modifier": mboe,
                                     "clause": op.clause_text[:200],
                                     "node_index": op.node_index,
                                     "reason": "unpaired_redesignation",
                                     "subject": key})
                    continue
                snaps = [pm["snapshot"], xml_art.snapshot_id]
                scope_provable = _clause_scope_provable(op, key)

                # ----- before binding (G1 §15) -------------------------------
                before_id = None
                before_kind = None
                if op_kind == "ADD":
                    bres = binding.BindingResult(
                        binding.NOT_APPLICABLE, "ADD_NO_BEFORE", key, 0)
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
                # G2.1 §28 subject_proof: ownership (O1), locator
                # declaration (O2) and existence-before (O3) — claims
                # for the evaluator to re-derive, not truth it accepts
                sproof = {
                    "version": "g2-subject-v1",
                    "target_attribution": {
                        "status": att.status, "method": att.method,
                        "candidate_instruments":
                            list(att.candidate_instruments),
                        "chosen_instrument": att.chosen_instrument,
                        "corrected_instrument": att.corrected_instrument,
                        "section_evidence": att.section_evidence,
                        "clause_evidence": att.clause_evidence},
                    "locator_declaration": {
                        "status": decl.status,
                        "locator_key": decl.locator_key,
                        "source_node_index": decl.source_node_index,
                        "components": [list(c) for c in decl.components],
                        "method": decl.method},
                    # O3 is derived in the post-emission pass below:
                    # the chain predecessor of a relation is decided by
                    # the authoritative (publication_date, relation_id)
                    # order, which is only complete once all relations
                    # for the target exist
                    "existence_before": None}
                conn.execute(
                    "INSERT OR IGNORE INTO modification_relations"
                    " (relation_id, kind, operation_kind, target_subject_id,"
                    " modifier_instrument_id, locator_raw, relation_raw,"
                    " before_representation_id, after_representation_id,"
                    " publication_date, instrument_effective_date,"
                    " declared_literals,"
                    " diff_levels, resolution, resolution_notes,"
                    " source_snapshot_ids, parser_name, parser_version,"
                    " binding_proof, subject_proof)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, pm["kind"], op_kind, sid,
                     instrument_id(mboe), op.clause_text, pm["ref"].texto,
                     before_id, after_id, pm["pub"],
                     pm["vigencia"] if pm["kind"] == "MODIFICATION" else None,
                     json.dumps(literals, ensure_ascii=False)
                     if literals else None,
                     json.dumps(levels), resolution,
                     resolution_notes,
                     json.dumps(snaps), PARSER_NAME, PARSER_VERSION,
                     _canonical_json(proof), _canonical_json(sproof)))
                stats["relations"] += 1
                pm["inventory"]["relations_emitted"] += 1

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
            if redesig_pending:
                _emit_redesignations(pm, op, redesig_pending)

    # ----- O3 derivation (G2.1 §33) --------------------------------------
    # Subject existence before each emitted relation, derived over the
    # complete emitted chain in its authoritative order — the same
    # derivation the frozen evaluator re-applies independently.
    o3_rows = conn.execute(
        "SELECT m.relation_id, m.operation_kind, m.publication_date,"
        " m.after_representation_id, m.subject_proof, s.locator_key"
        " FROM modification_relations m JOIN subjects s"
        " ON s.subject_id = m.target_subject_id"
        " WHERE s.instrument_id = ?",
        (instrument_id(target_boe_id),)).fetchall()
    by_key: dict[str, list] = {}
    for row in o3_rows:
        by_key.setdefault(row[5], []).append(row)
    for hops in by_key.values():
        hops.sort(key=lambda r: (r[2] or "", r[0]))
    struct_cache: dict[str, bool] = {}
    for key, hops in by_key.items():
        parts = key.split(".")
        ancestors = {".".join(parts[:i])
                     for i in range(1, len(parts))}
        if key not in struct_cache:
            struct_cache[key] = ownership.locator_resolves_in_doc(
                target, key)
        for i, row in enumerate(hops):
            prev = hops[i - 1] if i else None
            born = any(
                h[3] and (h[2] or "") < (row[2] or "")
                for a in ancestors for h in by_key.get(a, ()))
            exist = ownership.expected_existence(
                row[1],
                {"relation_id": prev[0], "operation_kind": prev[1],
                 "after_representation_id": prev[3]} if prev else None,
                born, struct_cache[key])
            sproof = json.loads(row[4]) if row[4] else {}
            sproof["existence_before"] = exist
            conn.execute(
                "UPDATE modification_relations SET subject_proof=?"
                " WHERE relation_id=?",
                (_canonical_json(sproof), row[0]))

    # §18: every parsed leaf operation ends in exactly one attribution
    # disposition — the inventory must account for all of them
    per_modifier = []
    inventory = {"leaf_operations_parsed": 0,
                 "attribution_dispositions":
                     {s: 0 for s in ownership.ATTRIBUTION_STATUSES}}
    for pm in ordered:
        inv = pm.get("inventory")
        if inv is None:
            continue
        dispositions = sum(inv[s] for s in ownership.ATTRIBUTION_STATUSES)
        if dispositions != inv["leaf_operations_parsed"]:
            _anomaly(ctx, "OPERATION_INVENTORY_MISMATCH", None, {
                "modifier": pm["boe_id"],
                "leaf_operations_parsed": inv["leaf_operations_parsed"],
                "dispositions": dispositions})
        inventory["leaf_operations_parsed"] += inv[
            "leaf_operations_parsed"]
        for s in ownership.ATTRIBUTION_STATUSES:
            inventory["attribution_dispositions"][s] += inv[s]
        per_modifier.append({"modifier": pm["boe_id"], **inv})
    inventory["per_modifier"] = per_modifier
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
        "operation_inventory": inventory,
        "target_annex_anchored": bool(amap and amap.anchored),
        "anchors": len(amap.anchors) if amap else 0,
        "fetch_errors": ctx.acquirer.errors,
        "anomalies": _unique_anomalies(ctx.anomalies),
        **stats,
    }

# Frozen-evaluator compatibility (PORT-2R): _CIRCULAR_RE resolves to
# the active profile's identity-reference grammar.
def __getattr__(name: str):
    if name == "_CIRCULAR_RE":
        return active_profile().identity_reference.circular_ref
    raise AttributeError(name)
