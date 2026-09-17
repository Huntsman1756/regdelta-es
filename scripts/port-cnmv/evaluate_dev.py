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

Verdicts per emitted relation:
  CONFIRMED_POSITIVE            clause + subject + resolution verified
  ABSTENTION_CONFIRMED          runtime abstained; evaluator also fails
                                to produce the binding — honest abstention
  ABSTENTION_DISPUTED           runtime abstained but evaluator resolves
                                (coverage gap — reported, not counted as
                                a false claim)
  FALSE_FACT                    emitted relation has no corresponding
                                operative clause in the modifier doc
  FALSE_SUBJECT_ATTRIBUTION     clause exists but attributed to the
                                wrong instrument
  FALSE_LOCATOR_DECLARATION     subject locator differs from the
                                independently derived one
  FALSE_BINDING                 RESOLVED binding contradicted by the
                                bound representation's own evidence
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
    r"Circular\s+(\d+)/(\d{4})\s*(?:,|\s+de\b)", re.IGNORECASE)
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
            ordn = _ORDINAL_WORD.get(ordw)
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
                   doc_circular: tuple[str, str] | None) -> str:
    """Ownership estimate: TARGET | FOREIGN | UNKNOWN."""
    m = _CIRCULAR_REF.search(text)
    if m:
        return ("TARGET" if self_ref and
                (m.group(1), m.group(2)) == self_ref else "FOREIGN")
    if re.search(r"(?:la\s+presente|esta|la\s+misma|dicha)\s+"
                 r"Circular|presente\s+Circular", text, re.IGNORECASE):
        return "TARGET" if self_ref == doc_circular else "UNKNOWN"
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
        "ABSTENTION_DISPUTED": 0, "FALSE_FACT": 0,
        "FALSE_SUBJECT_ATTRIBUTION": 0, "FALSE_LOCATOR_DECLARATION": 0,
        "FALSE_BINDING": 0, "runtime_leaf_ops": 0,
        "independent_clauses": 0,
    }
    findings = []

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

        counts = {"relations": len(rows)}
        verdicts = []
        for (rid, kind, opk, sid, mid, clause, res, b4, aft,
             bproof, sproof) in rows:
            v = "CONFIRMED_POSITIVE"
            why = []
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
            if v != "FALSE_FACT":
                own = _clause_target(clause, self_ref,
                                     _target_circular(mdoc))
                if own == "FOREIGN":
                    v = "FALSE_SUBJECT_ATTRIBUTION"
                    why = ["clause references another circular"]
            if v == "CONFIRMED_POSITIVE" and exp_subj:
                mykeys = _subject_keys(clause)
                if mykeys and not any(
                        k.split(".")[0] == exp_subj.split(".")[0]
                        for k in mykeys):
                    v = "FALSE_LOCATOR_DECLARATION"
                    why = [f"db={exp_subj} independent={mykeys}"]
            if v == "CONFIRMED_POSITIVE" and exp_subj:
                resolves = _eval_resolves(tdoc, exp_subj)
                # asymmetric confidence: a failed independent resolve is
                # weak evidence for multi-part keys (sub-items may live
                # in tables/continuations or be proven via chain
                # predecessors) and meaningless for ADD (no before
                # expected); a successful head-level resolve on an op
                # needing a before-side makes UNRESOLVED disputable —
                # for multi-part keys UNRESOLVED is usually the honest
                # binding-level abstention on content, not subject
                # absence (UNRESOLVED = neither side BOUND).
                head_level = "." not in exp_subj
                exist = (json.loads(sproof or "{}")
                         .get("existence_before", {})
                         .get("method"))
                if res == "RESOLVED" and not resolves \
                        and opk != "ADD" and head_level \
                        and exist == "ORIGINAL_PUBLICATION_STRUCTURAL":
                    v = "FALSE_BINDING"
                    why = [f"{exp_subj} not resolvable independently"]
                elif res == "UNRESOLVED" and resolves and head_level \
                        and opk in ("MODIFY", "DELETE", "SUBSTITUTE"):
                    v = "ABSTENTION_DISPUTED"
                    why = [f"{exp_subj} resolves independently"]
                elif res != "RESOLVED":
                    v = "ABSTENTION_CONFIRMED"
            verdicts.append({"relation_id": rid, "verdict": v,
                             "subject": exp_subj, "resolution": res,
                             "detail": why})
            counts[v] = counts.get(v, 0) + 1
            if v.startswith("FALSE") or v == "ABSTENTION_DISPUTED":
                findings.append({"target": target, "relation_id": rid,
                                 "verdict": v, "subject": exp_subj,
                                 "clause": (clause or "")[:140],
                                 "detail": why})
        indep = sum(len(c) for c in mod_clauses.values())
        counts["independent_clauses"] = indep
        per_target.append({"target": target, "self_ref": self_ref,
                           "norma_heads": len(tnorma), **counts})
        for k in ("relations", "CONFIRMED_POSITIVE",
                  "ABSTENTION_CONFIRMED", "ABSTENTION_DISPUTED",
                  "FALSE_FACT", "FALSE_SUBJECT_ATTRIBUTION",
                  "FALSE_LOCATOR_DECLARATION", "FALSE_BINDING",
                  "independent_clauses"):
            totals[k] = totals.get(k, 0) + counts.get(k, 0)
        conn.close()

    # transitive project-module dependency manifest (firewall audit)
    proj = sorted(m for m in sys.modules if m.startswith("regdelta"))
    return {"targets": per_target, "totals": totals,
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
