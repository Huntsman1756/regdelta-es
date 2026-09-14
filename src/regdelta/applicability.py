"""G0-D applicability ledger: deterministic persistence + query of the
applicability clauses declared by a modifier instrument.

Reads only the existing ledger (instruments → snapshots → blobs → raw
XML); it never fetches. Parsing lives in ``applicability_parser``; this
module owns binding, persistence and the read API.

Entry point:

    applicability.build(conn, data_dir, modifier_boe, target_boe)

Read API:

    applicability.applicability_for_relation(conn, relation_id)
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import applicability_parser as ap
from . import history, operations, rawstore
from .sources import boe_diario
from .util import now_utc_iso, sha256_hex_text

PARSER_NAME = ap.PARSER_NAME
PARSER_VERSION = ap.PARSER_VERSION

ANOMALY_TARGET_UNBOUND = "APPLICABILITY_TARGET_UNBOUND"


# ---------------------------------------------------------------------------
# identities
# ---------------------------------------------------------------------------


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def clause_id(boe_id: str, clause_key: str, locator: dict) -> str:
    return sha256_hex_text(
        f"aclause|{boe_id}|{clause_key}|{_canonical(locator)}")


def effect_id(cid: str, effect: str, value: str, locator: dict) -> str:
    return sha256_hex_text(
        f"aeffect|{cid}|{effect}|{value}|{_canonical(locator)}")


def target_id(cid: str, kind: str, ref: str, method: str) -> str:
    return sha256_hex_text(f"atarget|{cid}|{kind}|{ref}|{method}")


def _q(conn, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _one(conn, sql: str, params: tuple = ()) -> dict | None:
    rows = _q(conn, sql, params)
    return rows[0] if rows else None


def _clause_locator(c: ap.Clause) -> dict:
    return {"section": c.section, "item": c.item, "sub": c.sub,
            "node_span": c.node_span, "char_span": c.char_span}


# ---------------------------------------------------------------------------
# ledger access (no fetch — only already-registered evidence)
# ---------------------------------------------------------------------------


def _instrument_row(conn, boe_id: str) -> dict:
    row = _one(conn,
               "SELECT instrument_id, boe_id, titulo, fecha_publicacion,"
               "       snapshot_id FROM instruments WHERE boe_id=?",
               (boe_id,))
    if row is None:
        raise LookupError(f"instrument {boe_id} not in ledger")
    return row


def _diario_snapshot(conn, instrument_row) -> str:
    """snapshot_id of the instrument's official diario XML.

    PARSED instruments link it directly; REFERENCED instruments (the
    modifiers) resolved their diario XML during reconstruct — recover it
    through the canonical source_url. Fails explicitly if absent: G0-D
    never fetches."""
    if instrument_row["snapshot_id"]:
        return instrument_row["snapshot_id"]
    url = history.XML_URL.format(boe=instrument_row["boe_id"])
    row = conn.execute(
        "SELECT snapshot_id FROM source_snapshots WHERE source_url=?",
        (url,)).fetchone()
    if row is None:
        raise LookupError(
            f"no diario snapshot for {instrument_row['boe_id']}"
            " — acquisition belongs to the observation layer")
    return row[0]


def _doc_from_snapshot(conn, data_dir: Path, snapshot_id: str,
                       boe_id: str) -> boe_diario.DiarioDoc:
    """Parse the diario XML of an instrument from its ledger blob."""
    sha = conn.execute(
        "SELECT blob_sha256 FROM source_snapshots WHERE snapshot_id=?",
        (snapshot_id,)).fetchone()
    if sha is None:
        raise LookupError(f"snapshot {snapshot_id} not in ledger")
    blob = rawstore.blob_path(data_dir, sha[0])
    if not blob.exists():
        raise LookupError(f"blob {sha[0]} not stored under {data_dir}")
    res = boe_diario.parse_diario(blob.read_bytes())
    if res.doc is None:
        raise LookupError(
            f"diario blob for {boe_id} did not parse: {res.error}")
    return res.doc


def _target_num(titulo: str) -> tuple[int, int] | None:
    m = re.search(r"Circular\s+(\d+)\s*/\s*(\d{4})", titulo or "",
                  re.IGNORECASE)
    return (int(m.group(1)), int(m.group(2))) if m else None


# ---------------------------------------------------------------------------
# binding
# ---------------------------------------------------------------------------


@dataclass
class _Binding:
    clause_key: str
    locator_key: str
    relation_id: str
    method: str
    evidence: dict


def _bind(clauses: list[ap.Clause], rel_rows: list[dict],
          op_paths, container_keys, freq_map, freq_node) \
        -> tuple[list[_Binding], list[dict]]:
    """Reproduce the frozen discovery binding:

    * introducer marker paths expand to the ops under them (MARK_PATH);
    * explicitly cited subject locators bind directly (EXPLICIT_LOCATOR);
    * an estado target under a frequency-conditioned clause binds through
      the norma-67 declared periodicity (DECLARED_FREQUENCY);
    * a cited container locator expands silently (its member ops carry
      the relations); a cited non-container locator with no relation is
      an APPLICABILITY_TARGET_UNBOUND gap.

    Returns (bindings, unbound_cited) where unbound_cited is a list of
    {clause_key, locator_key, raw} dicts.
    """
    rel_by_key: dict[str, list[dict]] = {}
    for r in rel_rows:
        rel_by_key.setdefault(r["locator_key"], []).append(r)

    bindings: list[_Binding] = []
    unbound: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def emit(c: ap.Clause, key: str, method: str, ev: dict) -> None:
        for r in rel_by_key.get(key, []):
            sig = (c.clause_key, r["relation_id"], method)
            if sig in seen:
                continue
            seen.add(sig)
            bindings.append(_Binding(c.clause_key, key,
                                     r["relation_id"], method, ev))

    for c in clauses:
        freq_clause = any(
            (e.get("condition_normalized") or {}).get("frequency_in")
            for e in c.temporal_effects)
        path_keys: dict[str, list[str]] = {}
        for path, keys in op_paths:
            if any(path == i or path.startswith(i + "/")
                   for i in c.introducers):
                for k in keys:
                    path_keys.setdefault(k, []).append(path)
        cited = {s["locator_key"]: s for s in c.subjects
                 if not s.get("rule_ref")}
        for key in sorted(set(path_keys) | set(cited)):
            if freq_clause and key.startswith("estado:"):
                estado = key[7:]
                per = freq_map.get(estado)
                via = "exact"
                if per is None:
                    base = estado.split("-")[0]
                    per = freq_map.get(base)
                    via = "base_state"
                    estado = base
                if per is not None:
                    emit(c, key, "DECLARED_FREQUENCY", {
                        "locator_key": key,
                        "paths": path_keys.get(key, []),
                        "estado": estado,
                        "estado_table_key": estado,
                        "resolved_via": via,
                        "periodicity": per,
                        "frequency_table": {"node_index": freq_node,
                                            "source":
                                                "norma 67 table"},
                        "rule": "declared periodicity selects the"
                                " frequency-conditioned effect"})
                    continue
            if key in path_keys:
                emit(c, key, "MARK_PATH", {
                    "locator_key": key, "paths": path_keys[key],
                    "rule": "introduced-by-letter expansion"})
            if key in cited:
                emit(c, key, "EXPLICIT_LOCATOR", {
                    "locator_key": key, "raw": cited[key]["raw"],
                    "rule": "explicit subject citation"})
            if key not in rel_by_key and key not in container_keys:
                unbound.append({"clause_key": c.clause_key,
                                "locator_key": key,
                                "raw": cited.get(key, {}).get("raw", key)})
    return bindings, unbound


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def build(conn: sqlite3.Connection, data_dir: Path,
          modifier_boe: str, target_boe: str) -> dict:
    """Extract, bind and persist the applicability structure declared by
    ``modifier_boe`` over ``target_boe``. Idempotent: a rerun over the
    same ledger inserts nothing."""
    mod = _instrument_row(conn, modifier_boe)
    tgt = _instrument_row(conn, target_boe)
    mod_snap = _diario_snapshot(conn, mod)
    tgt_snap = _diario_snapshot(conn, tgt)
    mod_doc = _doc_from_snapshot(conn, data_dir, mod_snap, modifier_boe)
    tgt_doc = _doc_from_snapshot(conn, data_dir, tgt_snap, target_boe)

    clauses = ap.assign_parents(ap.extract_clauses(mod_doc))
    pub = (mod["fecha_publicacion"]
           or (mod_doc.metadata or {}).get("fecha_publicacion") or "")
    ap.resolve_relative_dates(clauses, pub.replace("-", ""))

    ops = operations.parse_operations(mod_doc, _target_num(tgt["titulo"]))
    _key_to_paths, op_paths, container_keys = ap.build_paths(
        ops.operations)
    freq_map, freq_node = ap.frequency_table(tgt_doc)

    rel_rows = _q(conn,
                  """SELECT mr.relation_id, s.locator_key
                     FROM modification_relations mr
                     JOIN subjects s
                       ON s.subject_id = mr.target_subject_id
                     WHERE mr.modifier_instrument_id=?
                       AND s.instrument_id=?""",
                  (mod["instrument_id"], tgt["instrument_id"]))

    bindings, unbound = _bind(clauses, rel_rows, op_paths,
                              container_keys, freq_map, freq_node)

    # ---- clauses (parents first — self FK) -------------------------------
    key_to_id: dict[str, str] = {}
    pending = list(clauses)
    inserted = 0
    while pending:
        progress = False
        still = []
        for c in pending:
            parent_cid = (key_to_id.get(c.parent_key)
                          if c.parent_key else None)
            if c.parent_key and parent_cid is None:
                still.append(c)
                continue
            loc = _clause_locator(c)
            cid = clause_id(modifier_boe, c.clause_key, loc)
            key_to_id[c.clause_key] = cid
            subject_raw = "; ".join(s["raw"] for s in c.subjects) or None
            cond_norm = [x["normalized"] for x in c.conditions
                         if x.get("normalized")] or None
            cur = conn.execute(
                """INSERT OR IGNORE INTO applicability_clauses
                   (clause_id, declaring_instrument_id, clause_key,
                    parent_clause_id, relation_to_parent, modality,
                    subject_raw, condition_raw, condition_normalized,
                    action_raw, evidence_text, evidence_locator,
                    epistemic, source_snapshot_id, parser_name,
                    parser_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, mod["instrument_id"], c.clause_key, parent_cid,
                 c.relation_to_parent, c.modality, subject_raw,
                 "; ".join(x["raw"] for x in c.conditions) or None,
                 _canonical(cond_norm) if cond_norm else None,
                 c.action_raw or None, c.text, _canonical(loc),
                 c.epistemic, mod_snap, PARSER_NAME,
                 PARSER_VERSION))
            inserted += cur.rowcount
            progress = True
        if not progress:
            raise RuntimeError(
                "applicability clause parent cycle: "
                f"{[c.clause_key for c in still]}")
        pending = still

    # ---- effects ----------------------------------------------------------
    n_effects = 0
    for c in clauses:
        cid = key_to_id[c.clause_key]
        loc = _clause_locator(c)
        for e in c.temporal_effects:
            value = e.get("date_value") or e.get("date_raw") or ""
            eid = effect_id(cid, e["effect"], value, loc)
            n_effects += conn.execute(
                """INSERT OR IGNORE INTO applicability_effects
                   (effect_id, clause_id, temporal_effect, date_value,
                    period_raw, condition_raw, condition_normalized,
                    evidence_locator, epistemic, parser_name,
                    parser_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, cid, e["effect"], e.get("date_value"),
                 e.get("period_raw"), e.get("condition_raw"),
                 _canonical(e["condition_normalized"])
                 if e.get("condition_normalized") else None,
                 _canonical(loc), e["epistemic"], PARSER_NAME,
                 PARSER_VERSION)).rowcount

    # ---- targets ----------------------------------------------------------
    n_targets = 0
    for c in clauses:
        if any(e["effect"] == "INSTRUMENT_EFFECTIVE_FROM"
               for e in c.temporal_effects):
            cid = key_to_id[c.clause_key]
            tid = target_id(cid, "INSTRUMENT", modifier_boe,
                            "INSTRUMENT_SCOPE")
            n_targets += conn.execute(
                """INSERT OR IGNORE INTO applicability_targets
                   (target_id, clause_id, target_kind,
                    target_instrument_id, modification_relation_id,
                    binding_method, binding_evidence,
                    source_snapshot_ids, epistemic)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (tid, cid, "INSTRUMENT", mod["instrument_id"], None,
                 "INSTRUMENT_SCOPE",
                 _canonical({"rule": "instrument-level entry into force",
                             "instrument": modifier_boe}),
                 _canonical([mod_snap]), "DERIVED")).rowcount
    for b in bindings:
        cid = key_to_id[b.clause_key]
        snaps = [mod_snap]
        if b.method == "DECLARED_FREQUENCY":
            snaps.append(tgt_snap)
        tid = target_id(cid, "MODIFICATION_RELATION", b.relation_id,
                        b.method)
        n_targets += conn.execute(
            """INSERT OR IGNORE INTO applicability_targets
               (target_id, clause_id, target_kind,
                target_instrument_id, modification_relation_id,
                binding_method, binding_evidence,
                source_snapshot_ids, epistemic)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (tid, cid, "MODIFICATION_RELATION", None, b.relation_id,
             b.method, _canonical(b.evidence), _canonical(snaps),
             "DERIVED")).rowcount

    # ---- anomalies --------------------------------------------------------
    for u in unbound:
        aid = sha256_hex_text(
            f"anomaly|{ANOMALY_TARGET_UNBOUND}|{modifier_boe}"
            f"|{target_boe}|{u['clause_key']}|{u['locator_key']}")
        conn.execute(
            """INSERT OR IGNORE INTO anomalies
               (anomaly_id, kind, snapshot_id, detail, detected_at)
               VALUES (?,?,?,?,?)""",
            (aid, ANOMALY_TARGET_UNBOUND, mod_snap,
             _canonical({"clause_key": u["clause_key"],
                         "locator_key": u["locator_key"],
                         "modifier": modifier_boe, "target": target_boe,
                         "raw": u["raw"]}),
             now_utc_iso()))

    return {
        "modifier": modifier_boe, "target": target_boe,
        "clauses": len(clauses), "clauses_inserted": inserted,
        "effects": sum(len(c.temporal_effects) for c in clauses),
        "effects_inserted": n_effects,
        "targets_inserted": n_targets,
        "epistemic": _dist(c.epistemic for c in clauses),
        "temporal_effects": _dist(e["effect"] for c in clauses
                                  for e in c.temporal_effects),
        "modalities": _dist(c.modality for c in clauses),
        "classification": classify(conn, mod["instrument_id"],
                                   tgt["instrument_id"]),
        "unbound_targets": unbound,
    }


def _dist(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


# ---------------------------------------------------------------------------
# classification + read API
# ---------------------------------------------------------------------------


def classify(conn: sqlite3.Connection, modifier_iid: str,
             target_iid: str) -> dict:
    """Four-way classification of every relation of (modifier → target)."""
    rows = _q(conn,
              """SELECT mr.relation_id, s.locator_key
                 FROM modification_relations mr
                 JOIN subjects s
                   ON s.subject_id = mr.target_subject_id
                 WHERE mr.modifier_instrument_id=?
                   AND s.instrument_id=?""",
              (modifier_iid, target_iid))
    bound = {r["modification_relation_id"] for r in _q(conn,
        """SELECT DISTINCT modification_relation_id
           FROM applicability_targets
           WHERE modification_relation_id IS NOT NULL""")}
    boes = {r["instrument_id"]: r["boe_id"] for r in _q(conn,
            "SELECT instrument_id, boe_id FROM instruments"
            " WHERE instrument_id IN (?,?)", (modifier_iid, target_iid))}
    cited_unbound = set()
    for r in conn.execute("SELECT detail FROM anomalies WHERE kind=?",
                          (ANOMALY_TARGET_UNBOUND,)):
        d = json.loads(r[0])
        if (d.get("modifier") == boes.get(modifier_iid)
                and d.get("target") == boes.get(target_iid)):
            cited_unbound.add(d.get("locator_key"))
    counts = {"SPECIFIC_BOUND": 0, "SPECIFIC_EXPECTED_BUT_UNBOUND": 0,
              "GENERAL_ONLY": 0, "NOT_APPLICABLE": 0}
    for r in rows:
        if r["relation_id"] in bound:
            counts["SPECIFIC_BOUND"] += 1
        elif r["locator_key"] in cited_unbound:
            counts["SPECIFIC_EXPECTED_BUT_UNBOUND"] += 1
        else:
            counts["GENERAL_ONLY"] += 1
    return counts


def _clause_payload(conn, cid: str) -> dict:
    return {
        "clause": _one(conn,
                       "SELECT clause_id, clause_key, relation_to_parent,"
                       "       modality, condition_raw,"
                       "       condition_normalized, action_raw,"
                       "       evidence_text, evidence_locator, epistemic"
                       " FROM applicability_clauses WHERE clause_id=?",
                       (cid,)),
        "effects": _q(conn,
                      """SELECT temporal_effect, date_value, period_raw,
                                condition_raw, condition_normalized,
                                evidence_locator, epistemic
                         FROM applicability_effects WHERE clause_id=?""",
                      (cid,)),
        "direct_targets": _q(conn,
                             """SELECT target_id, target_kind,
                                       target_instrument_id,
                                       modification_relation_id,
                                       binding_method, binding_evidence,
                                       source_snapshot_ids, epistemic
                                FROM applicability_targets
                                WHERE clause_id=?""",
                             (cid,)),
    }


def applicability_for_relation(conn: sqlite3.Connection,
                               relation_id: str) -> dict:
    """Applicability structure for one modification_relation.

    Never a single scalar date: returns the instrument-level rules plus
    the clause trees that target this relation, preserving parent/child
    structure and DIRECT vs INHERITED target origin. Sibling branches
    that target other relations are not inherited scope and are pruned;
    targetless children of an applicable clause inherit it."""
    rel = _one(conn,
               """SELECT mr.relation_id, mr.modifier_instrument_id,
                         s.locator_key, s.instrument_id AS target_iid,
                         im.boe_id AS modifier_boe,
                         it.boe_id AS target_boe
                  FROM modification_relations mr
                  JOIN subjects s
                    ON s.subject_id = mr.target_subject_id
                  JOIN instruments im
                    ON im.instrument_id = mr.modifier_instrument_id
                  JOIN instruments it
                    ON it.instrument_id = s.instrument_id
                  WHERE mr.relation_id=?""", (relation_id,))
    if rel is None:
        raise LookupError(f"relation {relation_id} not found")

    # direct modification targets per clause; INSTRUMENT-scope targets do
    # not bind a clause to a relation
    mod_targets: dict[str, set] = {}
    for r in _q(conn,
                """SELECT clause_id, modification_relation_id
                   FROM applicability_targets
                   WHERE modification_relation_id IS NOT NULL"""):
        mod_targets.setdefault(r["clause_id"], set()).add(
            r["modification_relation_id"])
    direct_ids = {cid for cid, rs in mod_targets.items()
                  if relation_id in rs}

    # scope check: does the modifier declare any applicability clauses?
    n_clauses = conn.execute(
        """SELECT COUNT(*) FROM applicability_clauses
           WHERE declaring_instrument_id=?""",
        (rel["modifier_instrument_id"],)).fetchone()[0]

    if direct_ids:
        classification = "SPECIFIC_BOUND"
    elif n_clauses == 0:
        classification = "NOT_APPLICABLE"
    else:
        unbound = _q(conn,
                     "SELECT detail FROM anomalies WHERE kind=?",
                     (ANOMALY_TARGET_UNBOUND,))
        if any((d := json.loads(x["detail"])).get("locator_key")
               == rel["locator_key"]
               and d.get("modifier") == rel["modifier_boe"]
               and d.get("target") == rel["target_boe"]
               for x in unbound):
            classification = "SPECIFIC_EXPECTED_BUT_UNBOUND"
        else:
            classification = "GENERAL_ONLY"

    rows = _q(conn, "SELECT clause_id, clause_key, parent_clause_id"
                    " FROM applicability_clauses")
    parent_of = {r["clause_id"]: r["parent_clause_id"] for r in rows}
    key_of = {r["clause_id"]: r["clause_key"] for r in rows}
    children_of: dict[str, list] = {}
    for r in rows:
        if r["parent_clause_id"]:
            children_of.setdefault(r["parent_clause_id"], []).append(
                r["clause_id"])
    for kids in children_of.values():
        kids.sort(key=lambda c: key_of[c])

    def emit(cid: str, bound: str | None) -> dict:
        """Serialize the applicable subgraph. A child with its own
        modification targets is included iff it targets ``bound`` (or
        ``bound`` is None → never, i.e. instrument rules carry no
        relation-specific branches); a targetless child inherits the
        scope of its included parent. Pruned subtrees are not recursed
        into."""
        node = _clause_payload(conn, cid)
        node["target_origin"] = (
            "DIRECT" if bound is not None
            and bound in mod_targets.get(cid, ()) else "INHERITED")
        node["children"] = [
            emit(ch, bound) for ch in children_of.get(cid, ())
            if not mod_targets.get(ch)
            or (bound is not None and bound in mod_targets[ch])]
        return node

    # instrument-scope rules: the instrument-level clause itself plus any
    # targetless refinements; specific (relation-bound) branches pruned
    inst = _q(conn,
              """SELECT DISTINCT t.clause_id FROM applicability_targets t
                 WHERE t.target_kind='INSTRUMENT'
                   AND t.target_instrument_id=?""",
              (rel["modifier_instrument_id"],))
    instrument_rules = [emit(r["clause_id"], None) for r in
                        sorted(inst, key=lambda r: key_of[r["clause_id"]])]

    # specific trees: rooted at the topmost ancestor of every clause
    # directly bound to this relation; ancestors are context
    roots: set[str] = set()
    for cid in direct_ids:
        cur = cid
        while parent_of.get(cur):
            cur = parent_of[cur]
        roots.add(cur)
    trees = [emit(r, relation_id)
             for r in sorted(roots, key=lambda c: key_of[c])]

    # safety net: a bound clause under an ancestor targeted elsewhere is
    # unreachable through the pruned tree — re-root it at its highest
    # targetless ancestor so no DIRECT binding is silently dropped
    reached = set()

    def collect(n):
        reached.add(n["clause"]["clause_id"])
        for ch in n["children"]:
            collect(ch)
    for t in trees:
        collect(t)
    extra_roots = set()
    for cid in sorted(direct_ids - reached, key=lambda c: key_of[c]):
        cur = cid
        while parent_of.get(cur) and not mod_targets.get(
                parent_of[cur]):
            cur = parent_of[cur]
        extra_roots.add(cur)
    trees.extend(emit(r, relation_id) for r in
                 sorted(extra_roots, key=lambda c: key_of[c]))

    return {
        "relation_id": relation_id,
        "locator_key": rel["locator_key"],
        "classification": classification,
        "instrument_rules": instrument_rules,
        "specific_clause_trees": trees,
    }
