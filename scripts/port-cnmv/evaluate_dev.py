"""PORT-CNMV-1 — independent DEV evaluator (import firewall, prereg §8).

Independently re-derives the claims the runtime emitted and checks them
against the persisted per-target SQLite produced by run_dev_probe.py
--persist-dir. Runtime output is NEVER treated as truth — only as
claims to falsify.

IMPORT FIREWALL (prereg §8 EVALUATOR IMPORT FIREWALL)
---------------------------------------------------
Allowed and used:
  * Python stdlib
  * regdelta.document            — canonical Node/DiarioDoc data types
  * regdelta.sources.boe_diario  — raw XML -> canonical node stream
  * regdelta.sources.boe_pdf     — PDF text layer (zlib + re only)
  * regdelta.sources.boe_doc     — doc HTML image list (re only)
All four are profile-free (verified: no imports of profile/registry/
runtime semantic modules; package __init__ files are empty).

Forbidden and NOT used: regdelta.profiles.*, active_profile/use_profile,
operations/binding/ownership/history helpers, any profile regex or
vocabulary, and the probe's boundary adapter (cnmv_boundary) — the
evaluator keeps its OWN class-normalization map, derived independently
from the XML class attributes.

Every regex/vocabulary below is written independently from DEV evidence;
none is imported from the profile under evaluation.

Every relation starts at EVALUATOR_NOT_PROVABLE and is promoted to
CONFIRMED_POSITIVE only after ALL of these independently succeed:
  O1      clause attribution = TARGET (FOREIGN -> FALSE_SUBJECT_,
          UNKNOWN -> NOT_PROVABLE)
  O2      the emitted locator_key equals the evaluator's independently
          derived key EXACTLY — root-only agreement is not confirmation
          (different full key -> FALSE_LOCATOR_DECLARATION,
          underivable  -> NOT_PROVABLE)
  BINDING every required bound side verifies: the persisted
          representation's text_content sha matches and equals the raw
          document nodes at artifact_locator.node_span, and the
          before-side locator independently resolves in the target
          (uncheckable side -> NOT_PROVABLE, contradiction ->
          FALSE_BINDING)

Verdicts per emitted relation:
  CONFIRMED_POSITIVE            clause + O1 + O2 + all required sides
                                independently verified
  ABSTENTION_CONFIRMED          runtime abstained; evaluator also fails
                                to produce the binding — honest abstention
  ABSTENTION_DISPUTED           runtime abstained but evaluator resolves
                                (coverage gap — reported, not counted as
                                a false claim)
  EVALUATOR_NOT_PROVABLE        a required independent check cannot be
                                performed (deep/table/continuation/image
                                binding, undetermined attribution,
                                underivable locator). Inability to
                                falsify is NOT confirmation. Written to
                                failures.jsonl with
                                CNMV_EVALUATOR_MODEL_ERROR.
  FALSE_FACT                    emitted relation has no corresponding
                                operative clause in the modifier doc
  FALSE_SUBJECT_ATTRIBUTION     clause exists but attributed to the
                                wrong instrument
  FALSE_LOCATOR_DECLARATION     subject locator differs from the
                                independently derived one
  FALSE_BINDING                 RESOLVED binding contradicted by the
                                bound representation's own evidence, or
                                a required bound side is absent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# --- allowed imports only (see header) --------------------------------------
from regdelta.document import DiarioDoc  # noqa: E402,F401  (types)
from regdelta.sources import boe_diario, boe_doc, boe_pdf  # noqa: E402

DEV_ROOT = ROOT / "evidence" / "port-cnmv" / "split-v2" / "dev"
SELECTION = ROOT / "evidence" / "port-cnmv" / "split-v2" / "selection.json"

# ---------------------------------------------------------------------------
# evaluator-owned vocabulary (independently derived from DEV evidence)
# ---------------------------------------------------------------------------

# legacy BOE stylesheet -> canonical class; derived from the XML class
# attributes themselves (style names encode the role literally)
_CLASS_NORM = {
    "RBF_SFRANySIG_ARTICULO": "articulo", "RBF_SFRAN_SOLA": "articulo",
    "LINEA_ANEXO": "anexo", "RVC_CAPITULO": "capitulo_num",
    "RHC_SEC_VERSALITAS": "centro", "RBC_RED_CENTRO": "centro",
    "NBC_SUBCAPITULO": "centro",
    "ATEXTO_NORMAL": "parrafo", "ATEXTO_BLANCO_4": "parrafo",
    "ATEXTO_BLANCO_6": "parrafo", "ATEXTOySIGUIENTE": "parrafo",
    "ACITAS": "parrafo", "[No paragraph style]": "parrafo",
}

_OP_VERB = re.compile(
    r"\b(?:queda[n]?\s+(?:redactad|sustituid|derogad)|"
    r"se\s+(?:modifica|añade|adiciona|suprime|elimina|sustituye|deroga|"
    r"introduce|da\s+nueva\s+redacci[oó]n|incorpora|incluye)|"
    r"pas[ae]n?\s+a\s+ser|se\s+da\s+nueva\s+redacci[oó]n|"
    r"añad[ae]n?|suprim[ei]n?|sustituy[ae]n?|modifi[qc]a)\w*",
    re.IGNORECASE)

_ORDINAL_WORD = {
    "uno": 1, "una": 1, "primero": 1, "primera": 1, "primer": 1,
    "dos": 2, "segundo": 2, "segunda": 2, "tres": 3, "tercero": 3,
    "tercera": 3, "tercer": 3, "cuatro": 4, "cuarto": 4, "cuarta": 4,
    "cinco": 5, "quinto": 5, "quinta": 5, "seis": 6, "sexto": 6,
    "sexta": 6, "siete": 7, "séptimo": 7, "septimo": 7, "séptima": 7,
    "septima": 7, "ocho": 8, "octavo": 8, "octava": 8, "nueve": 9,
    "noveno": 9, "novena": 9, "diez": 10, "décimo": 10, "decimo": 10,
    "décima": 10, "decima": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15,
}
_ORD_HEAD = re.compile(
    r"^(?:\d{1,2}|[a-z]|[ivxl]+|" +
    "|".join(sorted(_ORDINAL_WORD, key=len, reverse=True)) +
    r")\s*[.)]\s", re.IGNORECASE)

_OP_TAIL = re.compile(
    r"del\s+siguiente\s+modo|siguientes?\s+\w+:|como\s+sigue|"
    r"siguiente\s+redacci[oó]n|siguientes\s+t[eé]rminos|en\s+los?\s+"
    r"siguientes\s+t[eé]rminos", re.IGNORECASE)

_STATE_FAM = ("SEAFI", "BCFT", "SEAF", "SGE", "PC", "CS", "CA", "GA",
              "CR", "RM", "LI", "G", "R", "M", "T", "A", "P")
_STATE_ALT = "|".join(_STATE_FAM)

_CIRCULAR_REF = re.compile(
    r"Circular\s+(\d+)/(\d{4})", re.IGNORECASE)
_ISSUER = re.compile(
    r"Comisi[oó]n\s+Nacional\s+del\s+Mercado\s+de\s+Valores|\bCNMV\b",
    re.IGNORECASE)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip())


def _parse(path: Path) -> DiarioDoc:
    res = boe_diario.parse_diario(path.read_bytes())
    doc = res.doc
    if doc is not None:
        for i, n in enumerate(doc.nodes):
            new = _CLASS_NORM.get(n.cls)
            if new is not None:
                from dataclasses import replace
                doc.nodes[i] = replace(n, cls=new)
    return doc


# ---------------------------------------------------------------------------
# independent operative-clause + subject extraction
# ---------------------------------------------------------------------------

def _operative_clauses(doc: DiarioDoc) -> list[tuple[int, str]]:
    """(node index, text) for every node that opens an operative item:
    marked item (1./a)/iv)/Uno.) or unmarked clause, each carrying an
    operative verb or an operative colon tail."""
    out = []
    for n in doc.nodes:
        if n.kind != "p" or not n.text:
            continue
        t = _norm(n.text)
        if len(t) < 12:
            continue
        marked = bool(_ORD_HEAD.match(t))
        if _OP_VERB.search(t) or (marked and _OP_TAIL.search(t)):
            out.append((n.index, t))
    return out


def _subject_keys(text: str) -> list[str]:
    """Independent subject-locator extraction -> canonical key strings."""
    keys: list[str] = []
    # norma N(.ª)? (+ optional número/apartado/punto/letra chains)
    for m in re.finditer(
            r"\bnorma\s+(\d+)\s*[.ªº°]*\s*\.?"
            r"((?:[^.]{0,60}?)?)(?=\.|$|–|—)", text, re.IGNORECASE):
        base = f"norma:{m.group(1)}"
        tail = m.group(2) or ""
        sub = re.search(
            r"(?:n[uú]mero|apartado|punto)\s+(\d+|[A-Za-z])\b", tail,
            re.IGNORECASE)
        if sub:
            base += f".apartado:{sub.group(1)}"
            let = re.search(r"letra\s+\(?([a-z])\)?", tail, re.IGNORECASE)
            if let:
                base += f".letra:{let.group(1).lower()}"
        keys.append(base)
    # inverted CNMV order: "la letra l) del apartado 2 de la Norma 50ª",
    # "el número 3 de la norma 6ª", "el punto 2 de la norma 61.ª"
    for m in re.finditer(
            r"(?:letra\s+\(?([a-z])\)?\s+(?:del|de\s+la|de)\s+)?"
            r"(n[uú]mero|apartado|punto)\s+(\d+|[A-Za-z])\b"
            r"[^.]{0,60}?\bde\s+(?:la|el)\s+norma\s+(\d+)",
            text, re.IGNORECASE):
        kind = "punto" if m.group(2).lower() == "punto" else "apartado"
        base = f"norma:{m.group(4)}.{kind}:{m.group(3)}"
        if m.group(1):
            base += f".letra:{m.group(1).lower()}"
        keys.append(base)
    # plural enum: "las normas 43.ª, 44.ª, 45.ª, 46.ª, 47.ª y 48.ª";
    # a token may carry a sub-number ("Norma 11.ª 2" -> norma:11.2)
    for m in re.finditer(
            r"\bnormas\s+((?:\d+\s*\.?\s*[ªº°]?\s*(?:\d+)?\s*"
            r"(?:[,;]|y\b|e\b)?\s*)+)", text, re.IGNORECASE):
        for tok in re.finditer(r"(\d+)\s*\.?\s*[ªº°]?\s*(\d+)?",
                               m.group(1)):
            k = f"norma:{tok.group(1)}"
            if tok.group(2):
                k += f".apartado:{tok.group(2)}"
            keys.append(k)
    for m in re.finditer(
            r"\b(?:norma|disposici[oó]n)\s+"
            r"(adicional|transitoria|final|derogatoria|única|unica)"
            r"(?:\s+(\w+))?", text, re.IGNORECASE):
        tipo = m.group(1).lower()
        ordw = (m.group(2) or "").rstrip(".").lower()
        if tipo in ("única", "unica"):
            keys.append("disp:final.1" if "final" in text.lower()
                        else "disp:unica")
        else:
            ordn = _ORDINAL_WORD.get(ordw) or (
                ordw if ordw in ("bis", "ter", "quáter", "quater")
                else None)
            keys.append(f"disp:{tipo}.{ordn}" if ordn
                        else f"disp:{tipo}")
    for m in re.finditer(
            r"\banexos?\s+([0-9]+|[ivxl]+|bis|ter|qu[aá]ter)\b",
            text, re.IGNORECASE):
        keys.append(f"anejo:{m.group(1)}")
    # estado codes appear bare ("T2", "modelo SEAFI1", list after ':')
    # as often as behind the word "estado" — scan FAM+digits anywhere
    for m in re.finditer(
            r"\b(" + _STATE_ALT + r")\s*\.?\s*(\d[\d.\-]*)", text):
        tail = re.sub(r"[^0-9\-]", "", m.group(2))
        keys.append(f"estado:{m.group(1)} {tail}")
    return keys


def _target_circular(doc: DiarioDoc) -> tuple[str, str] | None:
    """The instrument's own Circular N/YYYY from its title/metadata."""
    tit = _norm(doc.metadata.get("titulo", ""))
    m = _CIRCULAR_REF.search(tit)
    if m and _ISSUER.search(tit):
        return (m.group(1), m.group(2))
    return None


def _clause_target(text: str, self_ref: tuple[str, str] | None,
                   doc_circular: tuple[str, str] | None) -> str | None:
    """Clause-level ownership: TARGET | FOREIGN | None (no signal — the
    caller falls back to the containing section's declared target).
    Only numbered 'Circular N/YYYY' refs count: 'la presente Circular'
    is a mention of the modifier itself (e.g. the source of replacement
    content), not a target declaration."""
    refs = _CIRCULAR_REF.findall(text)
    if refs:
        return ("TARGET" if self_ref and self_ref in refs
                else "FOREIGN")
    return None


def _clause_pos(doc: DiarioDoc, clause: str,
                node_index: int | None) -> int | None:
    """Locate the clause in the modifier doc. Prefer the claimed
    node_index from the relation's clause_evidence (identical clause
    texts can appear under different sections); fall back to a text
    prefix search."""
    cn = _norm(clause)[:60]
    if node_index is not None:
        for i, n in enumerate(doc.nodes):
            if (i == node_index or n.index == node_index) \
                    and n.text and cn in _norm(n.text):
                return i
    for i, n in enumerate(doc.nodes):
        if n.text and cn in _norm(n.text):
            return i
    return None


def _section_target(doc: DiarioDoc, pos: int,
                    self_ref: tuple[str, str] | None) -> str:
    """Section-level ownership: use the Circular refs declared by the
    clause's containing head ('Norma final segunda. Modificación de la
    Circular 4/2008…'); fall back to a doc-wide unique head-level ref.
    Returns TARGET | FOREIGN | UNKNOWN."""
    head_refs = []
    for n in reversed(doc.nodes[:pos]):
        if n.cls in ("articulo", "centro") and n.text:
            head_refs = _CIRCULAR_REF.findall(_head_text(n.text))
            break
    if head_refs:
        return ("TARGET" if self_ref and self_ref in head_refs
                else "FOREIGN")
    # doc-level target declared in the title
    # ("Circular 2/2008 … por la que se modifica … la Circular 4/1994")
    tit_refs = _CIRCULAR_REF.findall(
        _norm(doc.metadata.get("titulo", "")))
    if self_ref and self_ref in tit_refs:
        return "TARGET"
    # unique head-level circular ref across the whole document
    doc_refs = {_CIRCULAR_REF.findall(_head_text(n.text))[0]
                for n in doc.nodes
                if n.cls in ("articulo", "centro") and n.text
                and _CIRCULAR_REF.findall(_head_text(n.text))}
    if len(doc_refs) == 1:
        only = next(iter(doc_refs))
        return "TARGET" if self_ref and only == self_ref else "FOREIGN"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# independent resolution checks over the target document
# ---------------------------------------------------------------------------

def _head_text(t: str) -> str:
    """Normalized head text minus structural bracket tags
    ('[precepto]Norma 11. ...')."""
    return re.sub(r"^(?:\[[^\]]*\]\s*)+", "", _norm(t))


def _norma_spans(doc: DiarioDoc) -> dict[int, tuple[int, int]]:
    heads = [(n.index, n.text) for n in doc.nodes if n.cls == "articulo"]
    out = {}
    for pos, (idx, t) in enumerate(heads):
        m = re.match(r"norma\s+(\d+)", _head_text(t), re.IGNORECASE)
        if m:
            end = heads[pos + 1][0] if pos + 1 < len(heads) \
                else len(doc.nodes)
            out[int(m.group(1))] = (idx, end)
    return out


def _heads_iter(doc):
    for n in doc.nodes:
        if n.cls in ("articulo", "centro") and n.text:
            yield n.index, n.text


def _eval_resolves(doc: DiarioDoc, key: str) -> bool:
    """Independent locator resolution: head span + literal sub-items."""
    parts = key.split(".")
    kind, _, body = parts[0].partition(":")
    if kind == "norma" and body.isdigit():
        sp = _norma_spans(doc).get(int(body))
        if sp is None:
            return False
        texts = [_norm(n.text) for n in doc.nodes[sp[0]:sp[1]]]
        # each sub-part must show as a numbered/lettered item start
        for part in parts[1:]:
            _k, _, v = part.partition(":")
            if not any(re.match(rf"^{re.escape(v)}\s*[.)]", t,
                                re.IGNORECASE) for t in texts):
                return False
        return True
    if kind == "disp":
        tipo = body
        for _i, t in _heads_iter(doc):
            if re.match(rf"(?:norma|disposici[oó]n)\s+{tipo}\b",
                        _head_text(t), re.IGNORECASE):
                return True
        return False
    if kind == "anejo":
        return any(
            re.match(rf"anexos?\s+{re.escape(body)}\b",
                     _norm(n.text), re.IGNORECASE)
            for n in doc.nodes if n.text)
    if kind == "estado":
        return any(
            re.match(rf"(?:estado\s+)?{re.escape(body)}\b",
                     _norm(n.text))
            for n in doc.nodes if n.text)
    return False


_ITEM_HEAD = re.compile(
    r"^(?:Uno|Dos|Tres|Cuatro|Cinco|Seis|Siete|Ocho|Nueve|Diez|Once|"
    r"Doce|Trece|Catorce|Quince)\.\s|^\d+\.\s|^[a-z]\)\s",
    re.IGNORECASE)


def _has_after_content(doc, pos, clause):
    """Can the evaluator see after-content the runtime could have bound?
    True  = content independently present (literal or declared-following
            nodes that are not the next operative item)
    False = clause is self-contained; nothing follows
    None  = clause node not found / ambiguous
    """
    cn = _norm(clause)
    if re.search(r"[«\"].{10,}[»\"]", cn):
        return True
    if pos is None:
        return None
    if not (cn.rstrip().endswith(":") or "siguiente" in cn.lower()):
        return False
    j = pos + 1
    while j < len(doc.nodes) and not doc.nodes[j].text:
        j += 1
    if j >= len(doc.nodes):
        return False
    return not _ITEM_HEAD.match(_norm(doc.nodes[j].text))


# ---------------------------------------------------------------------------
# main evaluation
# ---------------------------------------------------------------------------

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def evaluate(db_dir: Path) -> dict:
    man = json.loads((DEV_ROOT / "manifest.json").read_text("utf-8"))
    entries = {e["name"]: e for e in man["entries"].values()}
    sel = json.loads(SELECTION.read_text("utf-8"))

    def raw(boe: str) -> Path:
        name = f"boe_diario_xml__{boe}.xml"
        e = entries.get(name)
        if e is None:
            raise SystemExit(f"evaluator: no dev artifact for {boe}")
        p = ROOT / e["path"]
        if _sha(p) != e["sha256"]:
            raise SystemExit(f"evaluator: sha mismatch on {name}")
        return p

    per_target = []
    totals = {
        "relations": 0, "CONFIRMED_POSITIVE": 0, "ABSTENTION_CONFIRMED": 0,
        "ABSTENTION_DISPUTED": 0, "EVALUATOR_NOT_PROVABLE": 0,
        "FALSE_FACT": 0, "FALSE_SUBJECT_ATTRIBUTION": 0,
        "FALSE_LOCATOR_DECLARATION": 0, "FALSE_BINDING": 0,
        "independent_clauses": 0,
    }
    findings = []
    all_verdicts = []

    for target in sel["dev"]:
        db_path = db_dir / target / "regdelta.sqlite"
        if not db_path.exists():
            raise SystemExit(f"missing persisted db for {target}: "
                             f"run probe with --persist-dir")
        conn = sqlite3.connect(db_path)
        tdoc = _parse(raw(target))
        tnorma = _norma_spans(tdoc)
        self_ref = _target_circular(tdoc)

        mods = {r[0]: r[1] for r in conn.execute(
            "SELECT instrument_id, boe_id FROM instruments")}
        mod_docs: dict[str, DiarioDoc] = {}
        mod_clauses: dict[str, list[tuple[int, str]]] = {}
        for iid, boe in mods.items():
            if boe == target:
                continue
            try:
                d = _parse(raw(boe))
            except SystemExit:
                continue
            mod_docs[iid] = d
            mod_clauses[iid] = _operative_clauses(d)

        rows = conn.execute(
            "SELECT relation_id, kind, operation_kind,"
            " target_subject_id, modifier_instrument_id, locator_raw,"
            " resolution, before_representation_id,"
            " after_representation_id, binding_proof, subject_proof"
            " FROM modification_relations").fetchall()
        subj_of = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT subject_id, locator_key, label FROM subjects")}
        reps = {r[0]: r[1:] for r in conn.execute(
            "SELECT representation_id, representation_kind,"
            " text_content, content_sha256, artifact_locator"
            " FROM representations")}

        doc_by_boe = {target: tdoc}
        doc_by_boe.update(
            {boe: mod_docs[iid] for iid, boe in mods.items()
             if iid in mod_docs})

        def rep_check(rid):
            """Verify a bound representation against raw evidence.
            True = verified, False = contradicted, None = not checkable.
            """
            row = reps.get(rid)
            if row is None:
                return None, "bound representation id not in table"
            kind, text, sha, loc_s = row
            loc = json.loads(loc_s or "{}")
            if loc.get("type") == "image_pages":
                pages = loc.get("pages") or []
                if not pages:
                    return None, "image_pages rep lists no pages"
                for pg in pages:
                    url = str(pg.get("url") or "")
                    name = (f"boe_imagen__{loc.get('instrument')}__"
                            f"{url.rsplit('/', 1)[-1]}")
                    e = entries.get(name)
                    if e is None:
                        return None, (f"image blob {name} not in dev "
                                      "manifest")
                    if _sha(ROOT / e["path"]) != pg.get("blob_sha256"):
                        return False, ("image blob sha256 mismatch on "
                                       f"{name}")
                return True, "image blob sha256 verified"
            if not text or not str(text).strip():
                return False, "bound representation text_content empty"
            if hashlib.sha256(str(text).encode("utf-8")).hexdigest() \
                    != sha:
                return False, "content_sha256 mismatch"
            if loc.get("type") == "xml_nodes" and loc.get("node_span"):
                d = doc_by_boe.get(loc.get("instrument"))
                if d is None:
                    return None, ("rep instrument "
                                  f"{loc.get('instrument')} unavailable")
                a, b = loc["node_span"]
                span = d.nodes[a:b]
                if kind == "TABLE":
                    # runtime serializes table cells with ' | ' and rows
                    # with '\n'; raw node text is a flat cell join that
                    # may repeat cells — verify ordered containment of
                    # every rep line, plus completeness of p nodes
                    raw_all = " " + " ".join(
                        _norm(n.text) for n in span) + " "
                    pos = 0
                    for line in str(text).split("\n"):
                        ln = _norm(line.replace("|", " "))
                        if not ln:
                            continue
                        i = raw_all.find(ln, pos)
                        if i < 0:
                            return False, ("rep line absent from span: "
                                           f"{ln[:60]}")
                        pos = i + len(ln)
                    rep_flat = _norm(str(text).replace("|", " "))
                    for n in span:
                        if n.kind == "p" and n.text and \
                                _norm(n.text) not in rep_flat:
                            return False, ("span node absent from rep: "
                                           f"{_norm(n.text)[:60]}")
                    return True, "table line containment verified"
                joined = "\n".join((n.text or "") for n in span)
                if joined.strip() == str(text).strip():
                    return True, "node_span text fidelity verified"
                return False, "text_content does not equal doc nodes"
            return None, (f"rep kind {kind}/{loc.get('type')} not "
                          "independently checkable")

        counts = {"relations": len(rows)}
        verdicts = []
        for (rid, kind, opk, sid, mid, clause, res, b4, aft,
             bproof, sproof) in rows:
            # default: NOT PROVEN — a claim is confirmed only by evidence
            v = "EVALUATOR_NOT_PROVABLE"
            why = []
            unverifiable = []

            # --- FALSE_FACT: the clause must exist in the modifier ----
            mdoc = mod_docs.get(mid)
            if mdoc is None:
                v, why = "FALSE_FACT", ["modifier doc unavailable"]
            else:
                cn = _norm(clause)
                alltext = "\n".join(
                    _norm(n.text) for n in mdoc.nodes if n.text)
                if cn[:60] not in alltext and \
                        not any(cn[:80] in t or t[:80] in cn
                                for _, t in mod_clauses.get(mid, [])):
                    v, why = "FALSE_FACT", ["clause not found"]
            exp_subj = subj_of.get(sid, (None,))[0]

            o1_ok = o2_ok = False
            cpos = None
            if v != "FALSE_FACT":
                cpos = _clause_pos(
                    mdoc, clause,
                    ((json.loads(sproof or "{}")
                      .get("target_attribution") or {})
                     .get("clause_evidence") or {})
                    .get("node_index"))
                # --- O1 attribution ------------------------------------
                own = _clause_target(clause, self_ref,
                                     _target_circular(mdoc))
                if own is None:
                    own = _section_target(mdoc, cpos, self_ref) \
                        if cpos is not None else "UNKNOWN"
                if own == "FOREIGN":
                    v = "FALSE_SUBJECT_ATTRIBUTION"
                    why = ["clause references another circular"]
                elif own == "TARGET":
                    o1_ok = True
                else:
                    why.append("O1 attribution undetermined")

                # --- O2 locator declaration ----------------------------
                if v != "FALSE_SUBJECT_ATTRIBUTION" and exp_subj:
                    mykeys = _subject_keys(clause)
                    if exp_subj in mykeys:
                        o2_ok = True
                    elif not mykeys:
                        why.append("locator not independently derivable")
                    else:
                        same_root = [
                            k for k in mykeys
                            if k.split(".")[0] == exp_subj.split(".")[0]]
                        if not same_root:
                            v = "FALSE_LOCATOR_DECLARATION"
                            why = [f"db={exp_subj} "
                                   f"independent={mykeys}"]
                        elif any(
                                len(k.split("."))
                                >= len(exp_subj.split("."))
                                for k in same_root):
                            # I derived a different key at the same or
                            # deeper level — a real disagreement
                            v = "FALSE_LOCATOR_DECLARATION"
                            why = [f"db={exp_subj} "
                                   f"independent={same_root}"]
                        else:
                            why.append(
                                "only locator root independently "
                                "derivable")

            # --- BINDING: verify every side that is checkable ---------
            bound_bad = []
            if not v.startswith("FALSE"):
                for side, rep_id in (("before", b4), ("after", aft)):
                    if rep_id is None:
                        continue
                    ok, note = rep_check(rep_id)
                    if ok is False:
                        bound_bad.append(f"{side}: {note}")
                    elif ok is None:
                        unverifiable.append(f"{side}: {note}")
                if bound_bad:
                    v = "FALSE_BINDING"
                    why = bound_bad

            resolves = (exp_subj is not None
                        and _eval_resolves(tdoc, exp_subj))
            before_needed = opk != "ADD"
            after_needed = opk != "DELETE"
            if not v.startswith("FALSE"):
                if res == "RESOLVED":
                    missing = [
                        s for s, rep_id in (("before", b4),
                                            ("after", aft))
                        if rep_id is None and
                        (s == "before" and before_needed
                         or s == "after" and after_needed)]
                    if missing:
                        v = "FALSE_BINDING"
                        why = [f"RESOLVED but no bound rep on "
                               f"{missing}"]
                    elif o1_ok and o2_ok and not unverifiable \
                            and (resolves or not before_needed):
                        v = "CONFIRMED_POSITIVE"
                        why = []
                    else:
                        if not resolves and before_needed:
                            why.append(
                                "subject not independently resolvable")
                elif res in ("PARTIAL", "UNRESOLVED"):
                    # each absent required side gets its own assessment:
                    # confirmed = abstention independently justified,
                    # disputed = evaluator sees what runtime missed,
                    # unprovable = cannot determine either way
                    outcome = "confirmed"
                    if before_needed and b4 is None:
                        if resolves:
                            why.append(f"{exp_subj} resolves "
                                       "independently")
                            outcome = "disputed"
                    if after_needed and aft is None:
                        hc = _has_after_content(mdoc, cpos, clause)
                        if hc is True:
                            why.append("after content independently "
                                       "present")
                            if outcome != "disputed":
                                outcome = "disputed"
                        elif hc is None:
                            why.append("after-side content presence "
                                       "not independently checkable")
                            if outcome == "confirmed":
                                outcome = "unprovable"
                    # the abstention's subject claim must itself verify
                    if outcome == "confirmed" and (
                            not o1_ok or (exp_subj and not o2_ok)):
                        outcome = "unprovable"
                    if unverifiable and outcome == "confirmed":
                        outcome = "unprovable"
                    v = {"confirmed": "ABSTENTION_CONFIRMED",
                         "disputed": "ABSTENTION_DISPUTED",
                         "unprovable": "EVALUATOR_NOT_PROVABLE"
                         }[outcome]
                    if v == "ABSTENTION_CONFIRMED":
                        why = []
            detail = why + unverifiable
            verdicts.append({"relation_id": rid, "verdict": v,
                             "subject": exp_subj, "resolution": res,
                             "detail": detail})
            counts[v] = counts.get(v, 0) + 1
            if v.startswith("FALSE") or v == "ABSTENTION_DISPUTED" \
                    or v == "EVALUATOR_NOT_PROVABLE":
                findings.append({
                    "target": target, "relation_id": rid,
                    "verdict": v, "subject": exp_subj,
                    "clause": (clause or "")[:140],
                    "detail": detail,
                    "reason_class": (
                        "CNMV_EVALUATOR_MODEL_ERROR"
                        if v == "EVALUATOR_NOT_PROVABLE" else None)})
        indep = sum(len(c) for c in mod_clauses.values())
        counts["independent_clauses"] = indep
        per_target.append({"target": target, "self_ref": self_ref,
                           "norma_heads": len(tnorma), **counts})
        all_verdicts.extend({"target": target, **v} for v in verdicts)
        for k in ("relations", "CONFIRMED_POSITIVE",
                  "ABSTENTION_CONFIRMED", "ABSTENTION_DISPUTED",
                  "EVALUATOR_NOT_PROVABLE",
                  "FALSE_FACT", "FALSE_SUBJECT_ATTRIBUTION",
                  "FALSE_LOCATOR_DECLARATION", "FALSE_BINDING",
                  "independent_clauses"):
            totals[k] = totals.get(k, 0) + counts.get(k, 0)
        conn.close()

    # transitive project-module dependency manifest (firewall audit)
    proj = sorted(m for m in sys.modules if m.startswith("regdelta"))
    return {"targets": per_target, "totals": totals,
            "relation_verdicts": all_verdicts,
            "findings": findings,
            "evaluator_import_manifest": proj}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = evaluate(args.db_dir)
    args.output.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(out["totals"], indent=1))
    print("import_manifest:", out["evaluator_import_manifest"])
    print(f"findings: {len(out['findings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
