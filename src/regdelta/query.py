"""G0-E deterministic query surface: read-only product queries over the
persisted ledger.

No network, no writes, no schema changes, no legal interpretation, no
single "effective date" synthesis. ``changes`` answers what was
published in a window (publication_date basis only); ``upcoming``
answers which dated applicability effects fall in a window; ``as-of``
reports legal-time facts published up to a date — it is NOT a synthetic
consolidated version; ``affects`` lists the modification relations
recorded against an instrument or subject.

Temporal semantics here are publication/legal time only. Bitemporal
"what RegDelta knew at instant T" (transaction time) is out of scope.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from . import applicability
from .profile import active_profile

DB_NAME = "regdelta.sqlite"

# effects that carry a real date_value; the rest are qualitative and are
# never forced into the upcoming calendar
DATED_EFFECTS = (
    "INSTRUMENT_EFFECTIVE_FROM", "APPLY_FROM", "FIRST_REFERENCE_DATE",
    "LAST_REFERENCE_DATE", "INITIAL_APPLICATION_DATE",
)

AS_OF_SEMANTICS = "LEGAL_TIME_FACTS_NOT_SYNTHETIC_CONSOLIDATED_VERSION"

WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------


class QueryError(Exception):
    """Expected query/input failure — CLI renders it as JSON, exit 2."""
    code = "QUERY_ERROR"


class DatabaseNotFound(QueryError):
    code = "DATABASE_NOT_FOUND"


class InstrumentNotFound(QueryError):
    code = "INSTRUMENT_NOT_FOUND"


class InstrumentAmbiguous(QueryError):
    code = "INSTRUMENT_AMBIGUOUS"


class SubjectNotFound(QueryError):
    code = "SUBJECT_NOT_FOUND"


class InvalidDateRange(QueryError):
    code = "INVALID_DATE_RANGE"


# ---------------------------------------------------------------------------
# connection + helpers
# ---------------------------------------------------------------------------


def connect_readonly(data_dir: Path) -> sqlite3.Connection:
    """Open the ledger strictly read-only: no creation, no migrations,
    no writes of any kind."""
    path = Path(data_dir) / DB_NAME
    if not path.exists():
        raise DatabaseNotFound(f"ledger not found: {path}")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                           uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def _q(conn, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _one(conn, sql: str, params: tuple = ()) -> dict | None:
    rows = _q(conn, sql, params)
    return rows[0] if rows else None


def _walk(node: dict):
    yield node
    for ch in node["children"]:
        yield from _walk(ch)


def _relative(date_value: str | None, as_of: date) -> str:
    """Factual date comparison only — never 'active'/'inactive'."""
    if not date_value:
        return "UNKNOWN"
    ref = as_of.isoformat()
    if date_value < ref:
        return "BEFORE"
    if date_value > ref:
        return "AFTER"
    return "ON"


def _loads(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


# ---------------------------------------------------------------------------
# instrument resolver — exact matching only, never fuzzy
# ---------------------------------------------------------------------------


def resolve_instrument(conn: sqlite3.Connection, ref: str) -> dict:
    """Resolve 'BOE-A-YYYY-NNNN' or 'Circular N/YYYY' to one instrument.

    Zero matches → InstrumentNotFound; more than one → InstrumentAmbiguous.
    """
    ref = WS_RE.sub(" ", (ref or "").strip())
    ir = active_profile().identity_reference
    if ir.boe_id.match(ref):
        rows = _q(conn, "SELECT * FROM instruments WHERE boe_id=?", (ref,))
    else:
        m = ir.circular_query.match(ref)
        if not m:
            raise InstrumentNotFound(
                f"unresolvable instrument reference: {ref!r}")
        pat = re.compile(rf"circular {m.group(1)}/{m.group(2)}(?!\d)",
                         re.IGNORECASE)
        all_rows = _q(conn, "SELECT * FROM instruments")
        norm = lambda t: WS_RE.sub(" ", (t or "").strip())
        # canonical parsed titles start with "Circular N/YYYY"; referenced
        # instruments carry the relation text, which may only mention it
        rows = ([r for r in all_rows
                 if pat.match(norm(r["titulo"]))]
                or [r for r in all_rows
                    if pat.search(norm(r["titulo"]))])
    if not rows:
        raise InstrumentNotFound(f"instrument not found: {ref!r}")
    if len(rows) > 1:
        raise InstrumentAmbiguous(
            f"ambiguous instrument reference {ref!r}:"
            f" {[r['boe_id'] for r in rows]}")
    return rows[0]


def _resolve_subject(conn, instrument_id: str, locator_key: str) -> dict:
    row = _one(conn,
               "SELECT * FROM subjects WHERE instrument_id=?"
               " AND locator_key=?", (instrument_id, locator_key))
    if row is None:
        raise SubjectNotFound(
            f"subject {locator_key!r} not found in instrument")
    return row


# ---------------------------------------------------------------------------
# relation projection shared by changes / affects / as_of
# ---------------------------------------------------------------------------

_REL_SELECT = """
    SELECT mr.relation_id, mr.kind, mr.operation_kind, mr.publication_date,
           mr.instrument_effective_date, mr.resolution, mr.resolution_notes,
           mr.diff_levels, mr.before_representation_id,
           mr.after_representation_id, mr.modifier_instrument_id,
           s.locator_key, s.subject_kind,
           ti.boe_id  AS target_boe_id,  ti.titulo AS target_title,
           mi.boe_id  AS modifier_boe_id, mi.titulo AS modifier_title,
           mi.fecha_publicacion AS modifier_publication,
           mi.fecha_vigencia    AS modifier_effective,
           br.representation_kind AS before_kind,
           ar.representation_kind AS after_kind
    FROM modification_relations mr
    JOIN subjects s    ON s.subject_id  = mr.target_subject_id
    JOIN instruments ti ON ti.instrument_id = s.instrument_id
    JOIN instruments mi ON mi.instrument_id = mr.modifier_instrument_id
    LEFT JOIN representations br
           ON br.representation_id = mr.before_representation_id
    LEFT JOIN representations ar
           ON ar.representation_id = mr.after_representation_id
"""


def _relation_payload(r: dict) -> dict:
    def rep(rid, kind):
        return {"id": rid, "kind": kind} if rid else None

    return {
        "relation_id": r["relation_id"],
        "kind": r["kind"],
        "operation_kind": r["operation_kind"],
        "target": {"boe_id": r["target_boe_id"],
                   "locator_key": r["locator_key"],
                   "subject_kind": r["subject_kind"]},
        "modifier": {"boe_id": r["modifier_boe_id"],
                     "title": r["modifier_title"]},
        "publication_date": r["publication_date"],
        "instrument_effective_date": r["instrument_effective_date"],
        "resolution": r["resolution"],
        "resolution_notes": _loads(r["resolution_notes"])
        or r["resolution_notes"],
        "diff_levels": _loads(r["diff_levels"]),
        "before_representation": rep(r["before_representation_id"],
                                     r["before_kind"]),
        "after_representation": rep(r["after_representation_id"],
                                    r["after_kind"]),
    }


# ---------------------------------------------------------------------------
# applicability summaries (never flattened to a single date)
# ---------------------------------------------------------------------------


def _modifier_has_clauses(conn, modifier_iid: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM applicability_clauses"
        " WHERE declaring_instrument_id=? LIMIT 1",
        (modifier_iid,)).fetchone())


def _compact_applicability(conn, relation_id: str,
                           modifier_iid: str) -> dict | None:
    """Compact applicability view preserving plurality. None when the
    modifier declares no applicability clauses at all."""
    if not _modifier_has_clauses(conn, modifier_iid):
        return None
    out = applicability.applicability_for_relation(conn, relation_id)
    effects = []
    seen = set()
    conditional = False
    for tree in out["instrument_rules"] + out["specific_clause_trees"]:
        for n in _walk(tree):
            if n["children"] or n["clause"]["condition_raw"] \
                    or n["clause"]["condition_normalized"]:
                conditional = True
            for e in n["effects"]:
                if e["condition_raw"] or e["condition_normalized"]:
                    conditional = True
                sig = (e["temporal_effect"], e["date_value"],
                       n["clause"]["clause_key"])
                if sig not in seen:
                    seen.add(sig)
                    effects.append({
                        "temporal_effect": e["temporal_effect"],
                        "date_value": e["date_value"],
                        "clause_key": n["clause"]["clause_key"]})
    effects.sort(key=lambda e: (e["temporal_effect"],
                                e["date_value"] or "", e["clause_key"]))
    return {"classification": out["classification"],
            "effects": effects,
            "has_conditional_structure": conditional}


def _annotated_applicability(conn, relation_id: str,
                             modifier_iid: str,
                             as_of: date) -> dict | None:
    """Full scoped applicability structure with each effect annotated
    relative_to_as_of (BEFORE/ON/AFTER/UNKNOWN)."""
    if not _modifier_has_clauses(conn, modifier_iid):
        return None
    out = applicability.applicability_for_relation(conn, relation_id)
    for tree in out["instrument_rules"] + out["specific_clause_trees"]:
        for n in _walk(tree):
            for e in n["effects"]:
                e["relative_to_as_of"] = _relative(e["date_value"], as_of)
    return out


# ---------------------------------------------------------------------------
# changes — publication basis only
# ---------------------------------------------------------------------------


def changes(conn: sqlite3.Connection, *, since: date,
            until: date | None = None,
            target: str | None = None) -> dict:
    """Relations whose publication_date falls inside [since, until]
    (inclusive). Publication is not applicability."""
    if until is not None and until < since:
        raise InvalidDateRange(f"since {since} > until {until}")
    inst = resolve_instrument(conn, target) if target else None
    target_iid = inst["instrument_id"] if inst else None
    until_s = until.isoformat() if until else None
    rows = _q(conn,
              _REL_SELECT + """
              WHERE mr.publication_date >= ?
                AND (? IS NULL OR mr.publication_date <= ?)
                AND (? IS NULL OR s.instrument_id = ?)
              ORDER BY mr.publication_date, mi.boe_id,
                       s.locator_key, mr.relation_id""",
              (since.isoformat(), until_s, until_s,
               target_iid, target_iid))
    return {
        "schema": "regdelta.query.changes/v1",
        "query": {"since": since.isoformat(), "until": until_s,
                  "target": target,
                  "target_boe_id": inst["boe_id"] if inst else None},
        "summary": {"result_count": len(rows), "basis": "publication_date"},
        "results": [_relation_payload(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# affects
# ---------------------------------------------------------------------------


def affects(conn: sqlite3.Connection, *, target: str,
            subject: str | None = None,
            modifier: str | None = None) -> dict:
    """Modification relations recorded against an instrument (optionally
    one exact subject locator and/or one exact modifier BOE id)."""
    inst = resolve_instrument(conn, target)
    if subject is not None:
        _resolve_subject(conn, inst["instrument_id"], subject)
    if modifier is not None:
        if not _one(conn, "SELECT instrument_id FROM instruments"
                          " WHERE boe_id=?", (modifier,)):
            raise InstrumentNotFound(f"modifier not found: {modifier!r}")
    rows = _q(conn,
              _REL_SELECT + """
              WHERE s.instrument_id = ?
                AND (? IS NULL OR s.locator_key = ?)
                AND (? IS NULL OR mi.boe_id = ?)
              ORDER BY mi.boe_id, mr.publication_date,
                       s.locator_key, mr.relation_id""",
              (inst["instrument_id"], subject, subject,
               modifier, modifier))
    modifiers: dict[str, dict] = {}
    for r in rows:
        m = modifiers.setdefault(r["modifier_boe_id"], {
            "boe_id": r["modifier_boe_id"],
            "title": r["modifier_title"],
            # instrument-level fecha_* may be NULL on REFERENCED rows —
            # fall back to the relation values, uniform per modifier
            "publication_date": r["modifier_publication"]
            or r["publication_date"],
            "instrument_effective_date": r["modifier_effective"]
            or r["instrument_effective_date"],
            "relations": []})
        rel = _relation_payload(r)
        rel["applicability"] = _compact_applicability(
            conn, r["relation_id"], r["modifier_instrument_id"])
        m["relations"].append(rel)
    results = sorted(modifiers.values(), key=lambda m: m["boe_id"])
    for m in results:
        m["relation_count"] = len(m["relations"])
    return {
        "schema": "regdelta.query.affects/v1",
        "query": {"target": target, "resolved_boe_id": inst["boe_id"],
                  "subject": subject, "modifier": modifier},
        "summary": {"relation_count": len(rows),
                    "modifier_count": len(results)},
        "results": results,
    }


# ---------------------------------------------------------------------------
# upcoming — dated applicability effects
# ---------------------------------------------------------------------------


def _upcoming_end(from_date: date, days: int) -> date:
    if days < 0:
        raise InvalidDateRange(f"days must be >= 0, got {days}")
    try:
        return from_date + timedelta(days=days)
    except OverflowError as exc:
        raise InvalidDateRange(
            f"window overflows date range: {from_date} + {days} days") from exc


def upcoming(conn: sqlite3.Connection, *, from_date: date, days: int,
             target: str | None = None) -> dict:
    """Applicability effects with a concrete date_value inside the
    inclusive window [from_date, from_date+days]. One row per effect;
    effective targets resolved through the frozen scoped trees."""
    end = _upcoming_end(from_date, days)
    inst = resolve_instrument(conn, target) if target else None
    target_iid = inst["instrument_id"] if inst else None

    effects = _q(conn, """
        SELECT e.effect_id, e.temporal_effect, e.date_value, e.clause_id,
               c.clause_key, c.modality, c.declaring_instrument_id,
               i.boe_id AS declaring_boe_id, i.titulo AS declaring_title
        FROM applicability_effects e
        JOIN applicability_clauses c ON c.clause_id = e.clause_id
        JOIN instruments i ON i.instrument_id = c.declaring_instrument_id
        WHERE e.date_value IS NOT NULL
          AND e.temporal_effect IN ({}""".format(
            ",".join("?" * len(DATED_EFFECTS))) + """)
          AND e.date_value >= ? AND e.date_value <= ?
        ORDER BY e.date_value, e.temporal_effect, e.effect_id""",
        (*DATED_EFFECTS, from_date.isoformat(), end.isoformat()))

    # effect -> relations, by inverting the frozen scoped trees
    effects_by_clause: dict[str, list[str]] = defaultdict(list)
    for r in _q(conn, "SELECT effect_id, clause_id"
                      " FROM applicability_effects"):
        effects_by_clause[r["clause_id"]].append(r["effect_id"])
    relations = _q(conn, """
        SELECT mr.relation_id
        FROM modification_relations mr
        JOIN subjects s ON s.subject_id = mr.target_subject_id
        WHERE (? IS NULL OR s.instrument_id = ?)""",
                   (target_iid, target_iid))
    effect_rels: dict[str, set] = defaultdict(set)
    for rel in relations:
        out = applicability.applicability_for_relation(
            conn, rel["relation_id"])
        for tree in out["instrument_rules"] + out["specific_clause_trees"]:
            for n in _walk(tree):
                for eid in effects_by_clause.get(
                        n["clause"]["clause_id"], ()):
                    effect_rels[eid].add(rel["relation_id"])

    # clause -> instrument-level targets
    clause_instruments: dict[str, list[str]] = defaultdict(list)
    for r in _q(conn, """
        SELECT t.clause_id, i.boe_id
        FROM applicability_targets t
        JOIN instruments i ON i.instrument_id = t.target_instrument_id
        WHERE t.target_kind='INSTRUMENT'"""):
        clause_instruments[r["clause_id"]].append(r["boe_id"])

    results = []
    for e in effects:
        rels = sorted(effect_rels.get(e["effect_id"], ()))
        insts = sorted(clause_instruments.get(e["clause_id"], ()))
        if target_iid is not None and not rels \
                and inst["boe_id"] not in insts:
            continue
        results.append({
            "effect_id": e["effect_id"],
            "temporal_effect": e["temporal_effect"],
            "date_value": e["date_value"],
            "clause": {"clause_id": e["clause_id"],
                       "clause_key": e["clause_key"],
                       "modality": e["modality"]},
            "declaring_instrument": {"boe_id": e["declaring_boe_id"],
                                     "title": e["declaring_title"]},
            "effective_targets": {"instruments": insts,
                                  "modification_relations": rels},
            "target_count": len(insts) + len(rels),
        })
    return {
        "schema": "regdelta.query.upcoming/v1",
        "query": {"from": from_date.isoformat(), "days": days,
                  "to": end.isoformat(), "target": target},
        "summary": {"result_count": len(results),
                    "window": {"from": from_date.isoformat(),
                               "to": end.isoformat()}},
        "results": results,
    }


# ---------------------------------------------------------------------------
# as-of — legal-time facts, not a consolidated version
# ---------------------------------------------------------------------------


def as_of(conn: sqlite3.Connection, *, target: str, as_of_date: date,
          subject: str | None = None) -> dict:
    """Relations published up to ``as_of_date`` plus their applicability
    structure with each effect compared factually against the date."""
    inst = resolve_instrument(conn, target)
    if subject is not None:
        _resolve_subject(conn, inst["instrument_id"], subject)
    rows = _q(conn,
              _REL_SELECT + """
              WHERE s.instrument_id = ?
                AND mr.publication_date <= ?
                AND (? IS NULL OR s.locator_key = ?)
              ORDER BY mr.publication_date, mi.boe_id,
                       s.locator_key, mr.relation_id""",
              (inst["instrument_id"], as_of_date.isoformat(),
               subject, subject))
    results = []
    for r in rows:
        rel = _relation_payload(r)
        rel["publication_relative"] = _relative(r["publication_date"],
                                                as_of_date)
        rel["instrument_effective_relative"] = _relative(
            r["instrument_effective_date"], as_of_date)
        rel["applicability"] = _annotated_applicability(
            conn, r["relation_id"], r["modifier_instrument_id"],
            as_of_date)
        results.append(rel)
    return {
        "schema": "regdelta.query.as_of/v1",
        "semantics": AS_OF_SEMANTICS,
        "query": {"target": target, "resolved_boe_id": inst["boe_id"],
                  "date": as_of_date.isoformat(), "subject": subject},
        "summary": {"relation_count": len(results)},
        "results": results,
    }
