"""G0-G.1 DEV evaluator — runs the frozen pipeline over the eight
GENERALIZATION_DEV targets and produces the preregistered run
artifacts. Zero network: all bytes come from evidence/g0g/dev/manifest
entries served as EVIDENCE_IMPORT FetchResults.

Contract: evidence/g0g/dev/EVALUATOR.md (frozen at baseline).

Usage:
    .venv/Scripts/python.exe -X utf8 scripts/g0g/evaluate_dev.py \
        --run-id 000-baseline --slug baseline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from regdelta import applicability, db as dbm, diffing, history, query  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
DEV = G0G / "dev"
DEV_MANIFEST = DEV / "manifest.json"
SELECTION = G0G / "selection.json"
GOLD = G0G / "gold" / "declared_modifiers.json"

VALID_OPS = {"SUBSTITUTE", "MODIFY", "ADD", "DELETE", "CORRECT"}

# ---------------------------------------------------------------------------
# allowlist / evidence plumbing
# ---------------------------------------------------------------------------


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).lower().strip()


def load_selection() -> dict:
    return json.loads(SELECTION.read_text(encoding="utf-8"))


def dev_allowlist(sel: dict) -> dict[str, str]:
    """boe_id -> cell, DEV only."""
    return {b: cell for cell, c in sel["cells"].items()
            for b in c["GENERALIZATION_DEV"]}


def holdout_set(sel: dict) -> set[str]:
    return {b for c in sel["cells"].values()
            for b in c["SEALED_HOLDOUT"]}


def load_dev_manifest() -> dict[str, dict]:
    m = json.loads(DEV_MANIFEST.read_text(encoding="utf-8"))
    return {e["url"]: e for e in m["entries"].values()}


def evidence_fetch(by_url: dict[str, dict]):
    def fetch(url: str, accept: str) -> FetchResult:
        e = by_url.get(url)
        if e is None or "path" not in e:
            return FetchResult(url, None, None, None, "MISSING",
                               "url not in dev evidence",
                               via=EVIDENCE_IMPORT)
        return FetchResult(url, 200, "application/octet-stream",
                           (ROOT / e["path"]).read_bytes(), None, None,
                           via=EVIDENCE_IMPORT)
    return fetch


def dev_xml(by_url: dict[str, dict], boe_id: str) -> bytes | None:
    e = by_url.get(f"https://www.boe.es/diario_boe/xml.php?id={boe_id}")
    if e is None or "path" not in e:
        return None
    return (ROOT / e["path"]).read_bytes()


# ---------------------------------------------------------------------------
# independent helpers (evaluator-side; no runtime parsing of claims)
# ---------------------------------------------------------------------------

_DISP_RE = re.compile(
    r"disposici[oó]n\s+(final|transitoria)", re.IGNORECASE)

_VERB_RULES = [
    ("SUBSTITUTE", re.compile(
        r"sustituy|debe\w*\s+sustituirse", re.I)),
    ("ADD", re.compile(
        r"a[ñn]ad|adicion|crea\w*\b|introduc|incorpor|inclu|"
        r"debe\w*\s+(?:añadir|insertar|incluir|agregar|crear)se", re.I)),
    ("DELETE", re.compile(
        r"suprim|derog|elimin|debe\w*\s+(?:suprimir|eliminar)se", re.I)),
    ("MODIFY", re.compile(
        r"modific|redact|queda|pasa\s+a\s+ser|sombrea|realiza|"
        r"desglos|inserta|donde\s+dice|debe\s+decir|"
        r"debe\w*\s+modificarse", re.I)),
    ("CORRECT", re.compile(r"correg|correcci", re.I)),
]


_QUOTED_RE = re.compile(r"«[^»]*»")


def _expected_op(verb_text: str) -> str | None:
    """The governing amendment verb is the earliest positional match —
    a trailing 'la descripción ... sustituye a la del fichero ...'
    boilerplate is descriptive, not the operative verb. Quoted «...»
    spans are stripped first: they cite titles/rubrics and literals,
    never the operative verb ('sobre «Modificaciones en las normas de
    la Circular 4/2004»')."""
    t = _norm(_QUOTED_RE.sub("", verb_text))
    best: tuple[int, str] | None = None
    for op, pat in _VERB_RULES:
        m = pat.search(t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), op)
    return best[1] if best else None


def modifier_declares_applicability(xml: bytes) -> bool:
    """Independent detector: any <p>/heading node whose text starts a
    disposicion final/transitoria. Raw-regex over official bytes; never
    applicability_parser."""
    text = xml.decode("utf-8", errors="replace")
    for m in re.finditer(r'<p class="[^"]*"[^>]*>(.*?)</p>', text, re.S):
        t = _norm(re.sub(r"<[^>]+>", " ", m.group(1)))
        if _DISP_RE.match(t):
            return True
    return False



def _locator_token(key: str) -> str:
    """Distinguishing suffix: estado:FI 100-14 -> 'fi 100-14';
    norma:33 -> '33'; anejo:9.punto:46 -> '46' with parents."""
    return key.split(":")[-1]


def _fichero_norm(text: str) -> str:
    """Independent fichero-name compare: _norm + hyphen spacing +
    footnote marks ('(*)')."""
    t = re.sub(r"\s*-\s*", "-", _norm(text))
    return re.sub(r"\s*\(\s*\*+\s*\)\s*$", "", t)


_FICHERO_CONNECTORS = frozenset(
    {"a", "ante", "con", "de", "del", "e", "el", "en", "la", "las",
     "los", "para", "por", "sobre", "y"})


def _fichero_tokens(text: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"[^\w]+", _fichero_norm(text))
                 if t and t not in _FICHERO_CONNECTORS)


def _fichero_eq(a: str, b: str) -> bool:
    """Exact normalized name, or equal content tokens — annex titles and
    clause citations can differ in connectors ('de' vs 'del')."""
    return _fichero_norm(a) == _fichero_norm(b) \
        or _fichero_tokens(a) == _fichero_tokens(b)


_ORDINAL_WORDS = {
    "1": "primera", "2": "segunda", "3": "tercera", "4": "cuarta",
    "5": "quinta", "6": "sexta", "7": "septima", "8": "octava",
    "9": "novena", "10": "decima", "11": "undecima", "12": "duodecima",
    "13": "decima tercera", "14": "decima cuarta", "15": "decima quinta",
    "16": "decima sexta", "17": "decima septima", "18": "decima octava",
    "19": "decima novena", "20": "vigesima",
}


def _head_span(doc: boe_diario.DiarioDoc, pat: re.Pattern,
               articulo_only: bool) -> tuple[int, int] | None:
    start = None
    for n in doc.nodes:
        if start is None:
            ok = (n.cls == "articulo" if articulo_only else n.kind == "p")
            if ok and pat.search(_norm(n.text)):
                start = n.index
        elif n.cls == "articulo":
            return (start, n.index)
    return (start, len(doc.nodes)) if start is not None else None


def _sub_present(doc: boe_diario.DiarioDoc, span: tuple[int, int],
                 kind: str, val: str) -> bool:
    """A 'kind:val' sub-locator resolves iff a node inside the parent
    span carries the value token with the kind prefix consistent."""
    v = _norm(val)
    if kind == "apartado":
        pats = (re.compile(rf"^{re.escape(v)}\s*\.\s"),
                re.compile(rf"\bapartados?\s+{re.escape(v)}\b"))
    elif kind == "punto":
        pats = (re.compile(rf"^{re.escape(v)}\s*\.\s"),
                re.compile(rf"\bpuntos?\s+{re.escape(v)}\b"))
    elif kind in ("letra", "nota"):
        pats = (re.compile(rf"^\(?{re.escape(v)}\)"),
                re.compile(rf"\b{kind}s?\s+\(?{re.escape(v)}\)?"))
    elif kind == "numeral":
        pats = (re.compile(rf"^{re.escape(v)}\s*[.)]"),)
    else:
        pats = (re.compile(rf"\b{re.escape(v)}\b"),)
    for i in range(*span):
        n = doc.nodes[i]
        if n.text and any(p.search(_norm(n.text)) for p in pats):
            return True
    return False


def locator_resolves(doc: boe_diario.DiarioDoc, key: str) -> bool:
    """Independent locator check over the official target document.

    norma:N -> a node whose text starts 'norma N'; anejo:N -> 'anejo N';
    disp:tipo.ordinal -> 'disposición <tipo> <ordinal>' heading;
    fichero:<name> -> a 'fichero: <name>' heading or a centered title
    node equal to the name; estado/others -> the raw token appears in
    any node text. Composed keys resolve hierarchically: head span must
    exist and each 'kind:val' part must occur inside it.
    """
    parts = key.split(".")
    kind, _, body = parts[0].partition(":")
    if kind == "disp":
        tipo = body
        ordinal = parts[1] if len(parts) > 1 and ":" not in parts[1] \
            else None
        pat = re.compile(
            rf"^(?:\[[^\]]*\]\s*)?disposici[oó]n\s+"
            rf"{re.escape(_norm(tipo))}"
            rf"\s+{re.escape(_norm(ordinal or ''))}\b")
        span = _head_span(doc, pat, articulo_only=True)
        if span is None:
            return False
        rest = parts[2:] if ordinal is not None else parts[1:]
        return all(":" in p and _sub_present(
            doc, span, p.split(":")[0], p.split(":")[1]) for p in rest)
    if kind == "fichero":
        fhead = re.compile(r"^fichero\s*:\s*(.*)$")
        for n in doc.nodes:
            t = _fichero_norm(n.text)
            m = fhead.match(t)
            if m and _fichero_eq(m.group(1), body):
                return True
            if (n.cls.startswith("centro")
                    or n.cls in ("capitulo_tit", "anexo_tit")) \
                    and _fichero_eq(t, body):
                return True
        return False
    if kind == "norma":
        num = _norm(body)
        word = _ORDINAL_WORDS.get(num)
        head_alt = rf"(?:{re.escape(num)}|{re.escape(word)})" \
            if word else re.escape(num)
        span = _head_span(
            doc, re.compile(
                rf"^(?:\[[^\]]*\]\s*)?norma\s+{head_alt}\b"),
            articulo_only=True)
        if span is None:
            return False
        return all(":" in p and _sub_present(
            doc, span, p.split(":")[0], p.split(":")[1])
            for p in parts[1:])
    token = _norm(body.split(".")[0] if "." in body else body)
    if kind in ("anejo", "disposicion", "titulo", "capitulo",
                "seccion", "apartado", "nota"):
        pat = re.compile(rf"^{re.escape(kind)}\s+{re.escape(token)}\b")
    else:
        pat = re.compile(rf"\b{re.escape(token)}\b")
    for n in doc.nodes:
        if n.text and pat.search(_norm(n.text)):
            return True
    return False


def _span_text(doc: boe_diario.DiarioDoc, span: list[int]) -> str:
    texts = []
    for i in range(span[0], span[1]):
        n = doc.nodes[i]
        if n.kind == "table":
            texts.extend(" | ".join(row) for row in n.rows)
        elif n.text:
            texts.append(n.text)
    return "\n".join(texts)


def _required_sides(op: str, literals) -> tuple[bool, bool]:
    """Mirrors history._resolution exactly."""
    if op == "ADD":
        return (False, True)
    if op == "DELETE":
        return (True, False)
    if op == "SUBSTITUTE":
        return (True, True)
    # MODIFY / CORRECT / other: before required; after required only
    # when no declared literal pair substitutes for it
    return (True, not literals)


def _expected_resolution(op, before_id, after_id, literals):
    need_b, need_a = _required_sides(op, literals)
    missing = []
    if need_b and not before_id:
        missing.append("before")
    if need_a and not after_id:
        missing.append("after")
    if not missing:
        return "RESOLVED"
    if before_id or after_id or literals:
        return "PARTIAL"
    return "UNRESOLVED"


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


def audit_relation(r: dict, docs: dict[str, boe_diario.DiarioDoc],
                   by_url: dict[str, dict], gold_ids: set[str],
                   gold_palabra: dict[str, str],
                   target_boe: str) -> dict:
    claims: dict[str, str] = {}
    ev: dict = {}

    # modifier identity + kind
    mboe = r["modifier_boe"]
    if mboe in gold_ids:
        claims["modifier_declared"] = "VERIFIED"
        expected_kind = ("CORRECTION"
                         if re.search(r"CORR", gold_palabra.get(mboe, ""),
                                      re.I) else "MODIFICATION")
        claims["kind_matches_palabra"] = (
            "VERIFIED" if r["kind"] == expected_kind else "CONTRADICTED")
        ev["gold_palabra"] = gold_palabra.get(mboe)
    else:
        claims["modifier_declared"] = "CONTRADICTED"

    # operation verb (vocabulary-limited: unmatched is not a fact error)
    exp_op = _expected_op(r["locator_raw"] or "")
    claims["operation_verb_consistent"] = (
        "NOT_CHECKABLE" if exp_op is None else
        "VERIFIED" if exp_op == r["operation_kind"] else "CONTRADICTED")

    # target locator
    tdoc = docs.get(target_boe)
    if tdoc is None:
        claims["target_locator_resolves"] = "NOT_CHECKABLE"
    elif locator_resolves(tdoc, r["locator_key"]):
        claims["target_locator_resolves"] = "VERIFIED"
    elif r["operation_kind"] == "ADD":
        # an ADD asserts the subject comes to exist; its absence from
        # the pre-change target is expected, not a contradiction
        claims["target_locator_resolves"] = "NOT_CHECKABLE"
    elif r["locator_key"].startswith(("estado:", "pagina:")) \
            and any(n.img_src for n in tdoc.nodes):
        # the code/page may live inside annex images, which are not
        # mechanically readable (no OCR) — the image evidence chain is
        # checked separately under before_binding
        claims["target_locator_resolves"] = "NOT_CHECKABLE"
    else:
        claims["target_locator_resolves"] = "CONTRADICTED"

    claims["subject_in_target"] = (
        "VERIFIED" if r["subject_instrument_boe"] == target_boe
        else "CONTRADICTED")

    # bindings
    for side in ("before", "after"):
        rep = r[f"{side}_representation_id"]
        claim = f"{side}_binding"
        if rep is None:
            continue
        inst = r[f"{side}_instrument"]
        doc = docs.get(inst)
        loc = r[f"{side}_locator"]
        kind = r[f"{side}_kind"]
        if kind in ("TEXT", "TABLE"):
            if doc is None or not isinstance(loc, dict) \
                    or "node_span" not in loc:
                claims[claim] = "NOT_CHECKABLE"
                continue
            try:
                text = _span_text(doc, loc["node_span"])
            except Exception:
                claims[claim] = "CONTRADICTED"
                continue
            ok = _norm(text) == _norm(r[f"{side}_text"] or "")
            # the claimed span must also cover the locator's region
            token = _locator_token(r["locator_key"])
            if r["locator_key"].startswith("fichero:"):
                covers = _fichero_norm(token) in _fichero_norm(text) \
                    or all(t in _fichero_tokens(text)
                           for t in _fichero_tokens(token))
            else:
                covers = _norm(token) in _norm(text)
            claims[claim] = "VERIFIED" if (ok and covers) \
                else "CONTRADICTED"
            ev[f"{side}_span"] = loc["node_span"]
        elif kind in ("IMAGE", "PDF_PAGE"):
            if doc is None or not isinstance(loc, dict):
                claims[claim] = "NOT_CHECKABLE"
                continue
            xml_srcs = {n.img_src for n in doc.nodes if n.img_src}
            pages = loc.get("pages") or []
            ok_srcs = all(p.get("url", "").replace(
                "https://www.boe.es", "") in xml_srcs for p in pages)
            ok_hash = True
            for p in pages:
                e = by_url.get(p.get("url", ""))
                if e is None or "path" not in e:
                    ok_hash = False
                    continue
                if _sha256((ROOT / e["path"]).read_bytes()) \
                        != p.get("blob_sha256"):
                    ok_hash = False
            ev[f"{side}_pages"] = [p.get("url") for p in pages]
            claims[claim] = ("VERIFIED" if (ok_srcs and ok_hash)
                             else "CONTRADICTED")
            claims[f"{side}_image_content"] = "NOT_CHECKABLE"
        else:
            claims[claim] = "NOT_CHECKABLE"

    # resolution recomputation
    lits = json.loads(r["declared_literals"]) \
        if r["declared_literals"] else None
    exp_res = _expected_resolution(
        r["operation_kind"], r["before_representation_id"],
        r["after_representation_id"], lits)
    claims["resolution_consistent"] = (
        "VERIFIED" if exp_res == r["resolution"] else "CONTRADICTED")

    # publication date vs modifier XML metadata
    mdoc = docs.get(mboe)
    if mdoc is not None:
        raw = (mdoc.metadata or {}).get("fecha_publicacion", "")
        pub = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else raw
        claims["publication_date_matches"] = (
            "VERIFIED" if pub == r["publication_date"]
            else "CONTRADICTED")

    if lits:
        claims["declared_literals_sane"] = (
            "VERIFIED" if all(len(p) == 2 and p[0] and p[1]
                              for p in lits) else "CONTRADICTED")

    verdict = ("FALSE_FACT" if "CONTRADICTED" in claims.values()
               else "PASS")
    return {"claims_checked": claims, "verdict": verdict,
            "evidence_locator": ev}


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

_RELQ = """
SELECT mr.relation_id, mr.kind, mr.operation_kind, mr.locator_raw,
       mr.relation_raw, mr.before_representation_id,
       mr.after_representation_id, mr.publication_date,
       mr.instrument_effective_date, mr.declared_literals,
       mr.diff_levels, mr.resolution, mr.resolution_notes,
       mr.source_snapshot_ids,
       s.locator_key, si.boe_id AS subject_instrument_boe,
       i.boe_id AS modifier_boe,
       rb.representation_kind AS before_kind,
       rb.text_content AS before_text,
       rb.artifact_locator AS before_locator,
       rb.binding AS before_binding,
       ra.representation_kind AS after_kind,
       ra.text_content AS after_text,
       ra.artifact_locator AS after_locator,
       ra.binding AS after_binding
FROM modification_relations mr
JOIN subjects s ON s.subject_id = mr.target_subject_id
JOIN instruments si ON si.instrument_id = s.instrument_id
JOIN instruments i ON i.instrument_id = mr.modifier_instrument_id
LEFT JOIN representations rb ON rb.representation_id =
       mr.before_representation_id
LEFT JOIN representations ra ON ra.representation_id =
       mr.after_representation_id
ORDER BY mr.publication_date, mr.relation_id
"""


def _side_instrument(locator: str | None) -> str | None:
    try:
        loc = json.loads(locator) if locator else None
    except json.JSONDecodeError:
        return None
    return loc.get("instrument") if isinstance(loc, dict) else None


def relation_rows(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(_RELQ).fetchall()]
    for r in rows:
        for side in ("before", "after"):
            loc = r[f"{side}_locator"]
            r[f"{side}_instrument"] = _side_instrument(loc)
            try:
                r[f"{side}_locator"] = json.loads(loc) if loc else None
            except json.JSONDecodeError:
                r[f"{side}_locator"] = {"_raw": loc}
    return rows


def chain_metrics(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """SELECT s.locator_key, mr.publication_date, mr.relation_id,
                  mr.before_representation_id, mr.after_representation_id
           FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           ORDER BY s.locator_key, mr.publication_date, mr.relation_id"""
    ).fetchall()
    per_sub: dict[str, list] = {}
    for r in rows:
        per_sub.setdefault(r[0], []).append(r)
    multi = {k: v for k, v in per_sub.items() if len(v) > 1}
    verdicts = {"CHAIN_PROVEN": 0, "CHAIN_NOT_PROVABLE": 0,
                "CHAIN_BROKEN": 0}
    broken = []
    for key, hops in multi.items():
        broken_hop = any(
            hops[i][4] and hops[i + 1][3]
            and hops[i][4] != hops[i + 1][3]
            for i in range(len(hops) - 1))
        all_proven = all(
            hops[i][4] and hops[i + 1][3]
            and hops[i][4] == hops[i + 1][3]
            for i in range(len(hops) - 1))
        if broken_hop:
            verdicts["CHAIN_BROKEN"] += 1
            broken.append(key)
        elif all_proven:
            verdicts["CHAIN_PROVEN"] += 1
        else:
            verdicts["CHAIN_NOT_PROVABLE"] += 1
    return {"multi_hop_subjects": len(multi), **verdicts,
            "broken_locator_keys": broken}


def required_bound(r: dict) -> bool:
    lits = json.loads(r["declared_literals"]) \
        if r["declared_literals"] else None
    nb, na = _required_sides(r["operation_kind"], lits)
    return (not nb or r["before_representation_id"]) and \
        (not na or r["after_representation_id"])


def run_queries(conn, target: str, rows: list[dict]) -> dict:
    pubs = sorted(r["publication_date"] for r in rows
                  if r["publication_date"])
    first = date.fromisoformat(pubs[0]) if pubs else date(1990, 1, 1)
    last = date.fromisoformat(pubs[-1]) if pubs else date.today()
    out = {}
    calls = {
        "changes": lambda: query.changes(
            conn, since=first - timedelta(days=1),
            until=last + timedelta(days=1), target=target),
        "affects": lambda: query.affects(conn, target=target),
        "upcoming": lambda: query.upcoming(
            conn, from_date=first, days=365, target=target),
        "as_of": lambda: query.as_of(
            conn, target=target, as_of_date=last),
        "diff": lambda: diffing.diff(
            conn, target=target, from_date=first - timedelta(days=1),
            to_date=last),
    }
    for name, fn in calls.items():
        try:
            res = fn()
            out[name] = {"status": "OK",
                         "result_count": len(res.get("results", []))}
        except Exception as exc:  # noqa: BLE001 - recorded, not hidden
            out[name] = {"status": "EXCEPTION",
                         "error": f"{type(exc).__name__}: {exc}"}
    return out


# ---------------------------------------------------------------------------
# per-target evaluation
# ---------------------------------------------------------------------------


def evaluate_target(target: str, cell: str, by_url: dict[str, dict],
                    gold: dict, run_id: str, tmp_root: Path) -> dict:
    data_dir = tmp_root / target
    data_dir.mkdir(parents=True)
    conn = dbm.connect(data_dir / "regdelta.sqlite")
    failures = []
    report = {}
    try:
        report = history.reconstruct(conn, data_dir, target,
                                     evidence_fetch(by_url))
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        failures.append({"target": target, "stage": "reconstruct",
                         "failure_class": "EVALUATION_FAILURE",
                         "symptom": f"{type(exc).__name__}: {exc}",
                         "expected": "reconstruct completes",
                         "observed": "exception", "status": "OPEN"})
        conn.close()
        return {"target": target, "cell": cell, "error": str(exc),
                "failures": failures}

    rows = relation_rows(conn)

    # -- declared modifier recall ----------------------------------------
    gdecl = gold.get(target, {}).get("declared", [])
    gold_ids = {d["modifier_boe_id"] for d in gdecl}
    gold_palabra = {d["modifier_boe_id"]: d["palabra"] for d in gdecl}
    discovered = {m["boe_id"] for m in report.get("modifiers", [])}
    rev = {r[0] for r in conn.execute(
        """SELECT i.boe_id FROM instrument_relations ir
           JOIN instruments i
             ON i.instrument_id = ir.declaring_instrument_id
           WHERE ir.direction='ANTERIOR' AND ir.other_boe_id=?""",
        (target,))}
    rec = [m for m in gold_ids
           if m in discovered and m in rev]
    missing = sorted(gold_ids - discovered)
    not_rev = sorted(gold_ids & discovered - rev)
    unexpected = sorted(discovered - gold_ids)
    for m in missing:
        failures.append({
            "target": target, "modifier": m, "stage": "discovery",
            "failure_class": "PARSER_FAILURE",
            "symptom": "gold modifier not discovered",
            "expected": f"{m} in posteriores-derived modifiers",
            "observed": "absent from report.modifiers",
            "evidence_locator": {"gold": m}, "status": "OPEN"})
    for m in not_rev:
        failures.append({
            "target": target, "modifier": m, "stage": "discovery",
            "failure_class": "PARSER_FAILURE",
            "symptom": "modifier discovered but no reverse ANTERIOR link",
            "expected": f"{m} anteriores references {target}",
            "observed": "no instrument_relations ANTERIOR row",
            "evidence_locator": {"gold": m}, "status": "OPEN"})
    for fe in report.get("fetch_errors", []):
        failures.append({
            "target": target, "stage": "acquire",
            "failure_class": "ACQUISITION_FAILURE",
            "symptom": str(fe), "expected": "artifact captured",
            "observed": "fetch error", "evidence_locator": fe,
            "status": "OPEN"})

    # -- applicability ----------------------------------------------------
    app_eligible, app_ok, app_detail = [], [], {}
    for m in report.get("modifiers", []):
        mb = m["boe_id"]
        xml = dev_xml(by_url, mb)
        if xml is None:
            failures.append({
                "target": target, "modifier": mb, "stage": "acquire",
                "failure_class": "ACQUISITION_FAILURE",
                "symptom": "modifier diario XML not in dev evidence",
                "expected": "captured", "observed": "MISSING",
                "evidence_locator": {"modifier": mb}, "status": "OPEN"})
            continue
        if not modifier_declares_applicability(xml):
            continue
        app_eligible.append(mb)
        try:
            arep = applicability.build(conn, data_dir, mb, target)
            conn.commit()
            n = conn.execute(
                """SELECT COUNT(*) FROM applicability_clauses c
                   JOIN instruments i
                     ON i.instrument_id = c.declaring_instrument_id
                   WHERE i.boe_id=?""", (mb,)).fetchone()[0]
            app_detail[mb] = {"clauses": n}
            if n > 0:
                app_ok.append(mb)
            else:
                failures.append({
                    "target": target, "modifier": mb,
                    "stage": "applicability",
                    "failure_class": "PARSER_FAILURE",
                    "symptom": "disposicion sections present but 0 clauses",
                    "expected": ">=1 clause", "observed": "0",
                    "evidence_locator": {"modifier": mb},
                    "status": "OPEN"})
        except Exception as exc:  # noqa: BLE001
            app_detail[mb] = {"exception": f"{type(exc).__name__}: {exc}"}
            failures.append({
                "target": target, "modifier": mb,
                "stage": "applicability",
                "failure_class": "EVALUATION_FAILURE",
                "symptom": f"{type(exc).__name__}: {exc}",
                "expected": "build completes", "observed": "exception",
                "evidence_locator": {"modifier": mb}, "status": "OPEN"})

    # -- audit ------------------------------------------------------------
    docs: dict[str, boe_diario.DiarioDoc] = {}
    for bid in {target} | {r["modifier_boe"] for r in rows} | \
            {r["before_instrument"] for r in rows if r["before_instrument"]} | \
            {r["after_instrument"] for r in rows if r["after_instrument"]}:
        xml = dev_xml(by_url, bid)
        if xml is not None:
            try:
                res = boe_diario.parse_diario(xml)
                if res.doc:
                    docs[bid] = res.doc
            except Exception:  # noqa: BLE001
                pass
    audit_rows = []
    for r in rows:
        a = audit_relation(r, docs, by_url, gold_ids, gold_palabra,
                           target)
        a.update(run_id=run_id, target=target,
                 relation_id=r["relation_id"], evidence_quote=None)
        audit_rows.append(a)
        if a["verdict"] == "FALSE_FACT":
            failures.append({
                "target": target, "relation_id": r["relation_id"],
                "stage": "audit", "failure_class": "EVALUATION_FAILURE",
                "symptom": "FALSE_FACT: " + ", ".join(
                    k for k, v in a["claims_checked"].items()
                    if v == "CONTRADICTED"),
                "expected": "claims consistent with official source",
                "observed": "contradicted",
                "evidence_locator": a["evidence_locator"],
                "status": "OPEN"})

    # -- anomalies as failures --------------------------------------------
    for an in report.get("anomalies", []):
        failures.append({
            "target": target, "stage": "reconstruct",
            "failure_class": "PARSER_FAILURE",
            "symptom": json.dumps(an, ensure_ascii=False)[:300],
            "expected": "no anomaly", "observed": an.get("kind", "?"),
            "evidence_locator": an, "status": "OPEN"})

    qres = run_queries(conn, target, rows)
    for name, res in qres.items():
        if res["status"] != "OK":
            failures.append({
                "target": target, "stage": "query",
                "failure_class": "EVALUATION_FAILURE",
                "symptom": f"{name}: {res['error']}",
                "expected": "query executes", "observed": "exception",
                "evidence_locator": {"query": name}, "status": "OPEN"})

    chains = chain_metrics(conn)
    n_rel = len(rows)
    metrics = {
        "declared_modifier_recall": {
            "num": len(rec), "den": len(gold_ids),
            "value": len(rec) / len(gold_ids) if gold_ids else None},
        "operation_parsing_rate": {
            "num": sum(1 for r in rows
                       if r["operation_kind"] in VALID_OPS),
            "den": n_rel,
            "value": (sum(1 for r in rows
                          if r["operation_kind"] in VALID_OPS) / n_rel)
            if n_rel else None},
        "subject_locator_resolution": {
            "num": sum(1 for a in audit_rows
                       if a["claims_checked"].get(
                           "target_locator_resolves") == "VERIFIED"),
            "den": n_rel,
            "value": (sum(1 for a in audit_rows
                          if a["claims_checked"].get(
                              "target_locator_resolves") == "VERIFIED")
                      / n_rel) if n_rel else None},
        "representation_binding": {
            "num": sum(1 for r in rows if required_bound(r)),
            "den": n_rel,
            "value": (sum(1 for r in rows if required_bound(r)) / n_rel)
            if n_rel else None},
        "chain_reconstruction": {
            "num": chains["CHAIN_PROVEN"], "den": chains["multi_hop_subjects"],
            "value": (chains["CHAIN_PROVEN"] / chains["multi_hop_subjects"])
            if chains["multi_hop_subjects"] else None,
            **{k: chains[k] for k in
               ("CHAIN_PROVEN", "CHAIN_NOT_PROVABLE", "CHAIN_BROKEN")}},
        "applicability_extraction": {
            "num": len(app_ok), "den": len(app_eligible),
            "value": (len(app_ok) / len(app_eligible))
            if app_eligible else None},
        "query_execution": {
            "num": sum(1 for v in qres.values() if v["status"] == "OK"),
            "den": 5,
            "value": sum(1 for v in qres.values()
                         if v["status"] == "OK") / 5},
        "false_positive_facts":
            sum(1 for a in audit_rows if a["verdict"] == "FALSE_FACT"),
        "source_limitations":
            sum(1 for f in failures
                if f["failure_class"] == "SOURCE_LIMITATION"),
    }

    inv = {
        "subjects": conn.execute("SELECT COUNT(*) FROM subjects")
        .fetchone()[0],
        "representations":
            conn.execute("SELECT COUNT(*) FROM representations")
            .fetchone()[0],
        "relations": n_rel,
        "resolution": dict(conn.execute(
            "SELECT resolution, COUNT(*) FROM modification_relations"
            " GROUP BY 1").fetchall()),
        "kind": dict(conn.execute(
            "SELECT kind, COUNT(*) FROM modification_relations"
            " GROUP BY 1").fetchall()),
        "operations": dict(conn.execute(
            "SELECT operation_kind, COUNT(*) FROM modification_relations"
            " GROUP BY 1").fetchall()),
        "transitions": dict(conn.execute(
            """SELECT COALESCE(rb.representation_kind,'NULL') || '->' ||
                      COALESCE(ra.representation_kind,'NULL'), COUNT(*)
               FROM modification_relations mr
               LEFT JOIN representations rb
                 ON rb.representation_id = mr.before_representation_id
               LEFT JOIN representations ra
                 ON ra.representation_id = mr.after_representation_id
               GROUP BY 1""").fetchall()),
        "anomalies": report.get("anomaly_count", 0),
        "app_clauses": conn.execute(
            "SELECT COUNT(*) FROM applicability_clauses").fetchone()[0],
    }
    conn.close()
    return {"target": target, "cell": cell, "report": {
                "modifiers": report.get("modifiers", []),
                "target_annex_anchored":
                    report.get("target_annex_anchored"),
                "anchors": report.get("anchors", 0)},
            "metrics": metrics, "inventory": inv,
            "query_execution": qres,
            "app_eligible": app_eligible, "app_detail": app_detail,
            "NON_GATE_DIAGNOSTIC": {
                "gold_count": len(gold_ids),
                "discovered_count": len(discovered),
                "reverse_cross_checked_count": len(rec),
                "missing_gold_modifiers": missing,
                "not_reverse_checked": not_rev,
                "unexpected_declared_modifier_candidates": unexpected,
                "chains": chains},
            "audit": audit_rows, "failures": failures,
            "relations": rows}


# ---------------------------------------------------------------------------
# combined smoke
# ---------------------------------------------------------------------------


def combined_smoke(allow: dict[str, str], by_url: dict[str, dict],
                   gold: dict, tmp_root: Path) -> dict:
    data_dir = tmp_root / "_combined"
    data_dir.mkdir(parents=True)
    conn = dbm.connect(data_dir / "regdelta.sqlite")
    problems = []
    for t in sorted(allow):
        try:
            rep = history.reconstruct(conn, data_dir, t,
                                      evidence_fetch(by_url))
            for m in rep.get("modifiers", []):
                xml = dev_xml(by_url, m["boe_id"])
                if xml is not None \
                        and modifier_declares_applicability(xml):
                    applicability.build(conn, data_dir, m["boe_id"], t)
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            problems.append({"target": t, "stage": "reconstruct",
                             "error": f"{type(exc).__name__}: {exc}"})
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        problems.append({"fk_violations": len(fk)})
    # relation leakage: relation's subject instrument must be a target
    bad = conn.execute(
        """SELECT COUNT(*) FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           JOIN instruments i ON i.instrument_id = s.instrument_id
           WHERE i.boe_id NOT IN (%s)"""
        % ",".join("?" * len(allow)), tuple(sorted(allow))).fetchone()[0]
    if bad:
        problems.append({"cross_target_subject_rows": bad})
    # no relation_id collision between distinct targets
    dup = conn.execute(
        """SELECT relation_id, COUNT(DISTINCT s.instrument_id)
           FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           GROUP BY relation_id HAVING COUNT(DISTINCT s.instrument_id)>1"""
    ).fetchall()
    if dup:
        problems.append({"relation_id_collisions": len(dup)})
    per_target = {}
    for t in sorted(allow):
        rows = relation_rows(conn)
        rows = [r for r in rows if r["subject_instrument_boe"] == t]
        per_target[t] = run_queries(conn, t, rows)
    conn.close()
    return {"problems": problems, "per_target_queries": per_target,
            "ok": not problems}


# ---------------------------------------------------------------------------
# run orchestration
# ---------------------------------------------------------------------------


def main() -> int:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--run-id", required=True)
    ap_.add_argument("--slug", required=True)
    ap_.add_argument("--targets", nargs="*", default=None)
    args = ap_.parse_args()

    sel = load_selection()
    allow = dev_allowlist(sel)
    hold = holdout_set(sel)
    targets = args.targets or sorted(allow)
    for t in targets:
        if t in hold:
            print(f"FAIL CLOSED: {t} is SEALED_HOLDOUT")
            return 2
        if t not in allow:
            print(f"FAIL CLOSED: {t} not in GENERALIZATION_DEV")
            return 2

    by_url = load_dev_manifest()
    gold_all = json.loads(GOLD.read_text(encoding="utf-8"))
    gold = {k: v for k, v in gold_all.items() if k in allow}  # dev only

    run_dir = DEV / "runs" / f"{args.run_id}-{args.slug}"
    run_dir.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()

    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True, cwd=ROOT
                          ).stdout.strip()
    src_tree = subprocess.run(
        ["git", "rev-parse", "HEAD:src/regdelta"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip()

    audit_path = G0G / "audit.jsonl"
    per_target = {}
    all_audit = []
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        for t in targets:
            print(f"evaluating {t} ({allow[t]})")
            res = evaluate_target(t, allow[t], by_url, gold,
                                  args.run_id, tmp_root)
            per_target[t] = res
            all_audit.extend(res.get("audit", []))
        print("combined DEV smoke")
        combined = combined_smoke(allow, by_url, gold, tmp_root)

    finished = datetime.now(timezone.utc).isoformat()

    # pooled metrics
    def pool(key):
        nums = sum(v["metrics"][key]["num"] for v in per_target.values()
                   if "metrics" in v and isinstance(
                       v["metrics"][key], dict))
        dens = sum(v["metrics"][key]["den"] for v in per_target.values()
                   if "metrics" in v and isinstance(
                       v["metrics"][key], dict))
        return {"num": nums, "den": dens,
                "value": nums / dens if dens else None}

    metrics = {k: pool(k) for k in
               ("declared_modifier_recall", "operation_parsing_rate",
                "subject_locator_resolution", "representation_binding",
                "chain_reconstruction", "applicability_extraction",
                "query_execution")}
    metrics["false_positive_facts"] = sum(
        v["metrics"]["false_positive_facts"]
        for v in per_target.values() if "metrics" in v)
    metrics["source_limitations"] = sum(
        v["metrics"]["source_limitations"]
        for v in per_target.values() if "metrics" in v)
    by_cell: dict[str, dict] = {}
    for t, v in per_target.items():
        c = by_cell.setdefault(v["cell"], {"targets": []})
        c["targets"].append(t)
        c.setdefault("metrics", v.get("metrics"))

    self_sha = _sha256(Path(__file__).read_bytes())
    run = {
        "run_id": args.run_id, "slug": args.slug,
        "runtime_head": head, "src_tree_sha": src_tree,
        "evaluator_sha256": self_sha,
        "dev_manifest_sha256": _sha256(DEV_MANIFEST.read_bytes()),
        "selection_sha256": _sha256(SELECTION.read_bytes()),
        "gold_sha256": _sha256(GOLD.read_bytes()),
        "started_at": started, "finished_at": finished,
    }

    with audit_path.open("a", encoding="utf-8") as fh:
        for a in all_audit:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")

    (run_dir / "run.json").write_text(json.dumps(
        run, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(
        {"aggregate": metrics, "by_cell": by_cell,
         "per_target": {t: v.get("metrics")
                        for t, v in per_target.items()}},
        indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    (run_dir / "targets.json").write_text(json.dumps(
        {t: {k: v[k] for k in ("cell", "report", "inventory",
                               "query_execution", "app_eligible",
                               "NON_GATE_DIAGNOSTIC")
             if k in v}
         for t, v in per_target.items()},
        indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    with (run_dir / "failures.jsonl").open("w", encoding="utf-8") as fh:
        for v in per_target.values():
            for f in v.get("failures", []):
                fh.write(json.dumps(
                    {"failure_id": _sha256(json.dumps(
                        f, sort_keys=True,
                        ensure_ascii=False).encode())[:16],
                     **f}, ensure_ascii=False) + "\n")
    with (run_dir / "relations.jsonl").open("w", encoding="utf-8") as fh:
        for t, v in per_target.items():
            for r in v.get("relations", []):
                slim = {k: r[k] for k in (
                    "relation_id", "kind", "operation_kind",
                    "locator_key", "modifier_boe", "publication_date",
                    "resolution", "before_kind", "after_kind")}
                slim["target"] = t
                fh.write(json.dumps(slim, ensure_ascii=False) + "\n")
    (run_dir / "combined-dev.json").write_text(json.dumps(
        combined, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    # report.md
    lines = [f"# G0-G DEV run {args.run_id}-{args.slug}", "",
             f"runtime_head: `{head}`", "",
             "## Aggregate", "",
             "| metric | num/den | value |", "|---|---|---|"]
    for k, v in metrics.items():
        if isinstance(v, dict):
            lines.append(f"| {k} | {v['num']}/{v['den']} | "
                         f"{v['value'] if v['value'] is None else round(v['value'],4)} |")
        else:
            lines.append(f"| {k} | — | {v} |")
    lines += ["", "## Per target", "",
              "| target | cell | rels | res(P/U) | recall | FF |",
              "|---|---|---|---|---|---|"]
    for t, v in sorted(per_target.items()):
        if "metrics" not in v:
            lines.append(f"| {t} | {v['cell']} | ERROR | — | — | — |")
            continue
        r = v["inventory"]["resolution"]
        lines.append(
            f"| {t} | {v['cell']} | {v['inventory']['relations']} | "
            f"{r.get('RESOLVED',0)}/{r.get('PARTIAL',0)}/"
            f"{r.get('UNRESOLVED',0)} | "
            f"{v['metrics']['declared_modifier_recall']['num']}/"
            f"{v['metrics']['declared_modifier_recall']['den']} | "
            f"{v['metrics']['false_positive_facts']} |")
    n_fail = sum(len(v.get("failures", [])) for v in per_target.values())
    lines += ["", f"failures: {n_fail} | audit rows: {len(all_audit)} | "
              f"combined smoke ok: {combined['ok']}", ""]
    (run_dir / "report.md").write_text("\n".join(lines),
                                     encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "aggregate": metrics,
                      "failures": n_fail, "audit_rows": len(all_audit),
                      "combined_ok": combined["ok"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
