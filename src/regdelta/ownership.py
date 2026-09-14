"""G2.1 ownership & lifecycle layer.

Attribution answers "whose legal structure is this operation
changing?" — decided per parsed operation, before any target relation
is persisted (G2.1 §12-19). LocatorDeclaration answers "did this
operation declare this locator?" (§20-26). Subject existence (O3) is
derived over the emitted chain independently of the G1 representation
chain (§31-35).

The policy is::

    PARSE → ATTRIBUTE TARGET → PROVE LOCATOR → DETERMINE LIFECYCLE
    → BIND REPRESENTATIONS → EMIT RELATION

never "parse target-specific, assume ownership, repair later".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from . import operations
from .sources import boe_diario

PARSER_NAME = "ownership"
PARSER_VERSION = "g2-v1"

# --- target attribution statuses (G2.1 §13) ---------------------------------
TARGET_PROVEN = "TARGET_PROVEN"
FOREIGN_TARGET = "FOREIGN_TARGET"
MODIFIER_LOCAL = "MODIFIER_LOCAL"
ATTR_AMBIGUOUS = "AMBIGUOUS"
ATTR_NOT_PROVABLE = "NOT_PROVABLE"

ATTRIBUTION_STATUSES = (TARGET_PROVEN, FOREIGN_TARGET, MODIFIER_LOCAL,
                        ATTR_AMBIGUOUS, ATTR_NOT_PROVABLE)

# --- locator declaration statuses (§20) -------------------------------------
LOC_PROVEN = "PROVEN"
LOC_AMBIGUOUS = "AMBIGUOUS"
LOC_NOT_PROVABLE = "NOT_PROVABLE"

# --- lifecycle statuses (§6/§31) ---------------------------------------------
L_PRESENT = "PRESENT"
L_ABSENT = "ABSENT"
L_DELETED = "DELETED"
L_UNKNOWN = "UNKNOWN"
L_NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class TargetAttribution:
    """O1 proof record for one parsed operation (G2.1 §13)."""
    status: str
    method: str | None
    candidate_instruments: tuple[str, ...]
    chosen_instrument: str | None
    section_evidence: dict | None
    clause_evidence: dict | None
    corrected_instrument: str | None
    reason: str | None


@dataclass(frozen=True)
class LocatorDeclaration:
    """O2 proof record for one subject of one operation (§20)."""
    status: str                    # PROVEN | NOT_PROVABLE | AMBIGUOUS
    locator_key: str | None
    components: tuple              # SubjectRef.proof_components
    source_node_index: int
    method: str | None
    reason: str | None


# ---------------------------------------------------------------------------
# corrigendum corrected-instrument resolution (§16)
# ---------------------------------------------------------------------------

_ELI_CIR_RE = re.compile(r"/cir/(\d{4})/(\d{2})/(\d{2})/(\d+)")


def _unique_refs(text: str) -> list[tuple[int, int]]:
    refs = operations._target_refs(
        operations._QUOTED_SPAN_RE.sub("", text))
    return list(dict.fromkeys(refs))


def _corr_kind(ref) -> str | None:
    """'CORRECCIÓN de errores' = the corrected instrument (primary);
    'CORRIGE errores en <X>' = a downstream secondary relation."""
    p = (ref.palabra or "").upper().replace("Ó", "O")
    if p.startswith("CORRECCION DE ERRORES"):
        return "PRIMARY"
    if p.startswith("CORRIGE ERRORES") or "CORRECCION" in p:
        return "SECONDARY"
    return None


def resolve_corrected_instrument(mdoc: boe_diario.DiarioDoc) -> dict:
    """Resolve the corrected instrument C of a corrigendum M.

    Priority (§16): ELI /corrigendum/ path -> anterior 'CORRECCIÓN de
    errores' -> unique correction relation. Incompatible official
    evidence -> AMBIGUOUS; none -> NONE.
    """
    eli = mdoc.metadata.get("url_eli", "") or ""
    eli_ref = None
    m = _ELI_CIR_RE.search(eli)
    if m and "/corrigendum/" in eli:
        eli_ref = (int(m.group(4)), int(m.group(1)))  # (num, year)

    primaries = [(r.referencia, r.texto) for r in mdoc.anteriores
                 if _corr_kind(r) == "PRIMARY"]
    secondary = [(r.referencia, r.texto) for r in mdoc.anteriores
                 if _corr_kind(r) == "SECONDARY"]

    chosen = None
    method = None
    evidence = {"eli": eli or None, "eli_ref": eli_ref,
                "primary_anteriores": primaries,
                "secondary_anteriores": secondary}
    if eli_ref is not None:
        for ref, texto in primaries + secondary:
            if eli_ref in _unique_refs(texto):
                chosen, method = ref, "ELI_CORRECTS"
                break
        if chosen is None and len(primaries) == 1:
            chosen, method = primaries[0][0], "ELI_CORRECTS"
    if chosen is None and len(primaries) == 1:
        chosen, method = primaries[0][0], "CORRECCION_ANTERIOR"
    if chosen is None and not primaries:
        corr = primaries + secondary
        if len(corr) == 1:
            chosen, method = corr[0][0], "UNIQUE_CORRECTION_RELATION"
    if chosen is None:
        return {"status": "AMBIGUOUS" if (primaries or eli_ref)
                else "NONE", "corrected_boe": None,
                "corrected_ref": eli_ref, "method": method,
                "evidence": evidence}
    cref = None
    for ref, texto in primaries + secondary:
        if ref == chosen:
            cr = _unique_refs(texto)
            cref = cr[0] if len(cr) == 1 else eli_ref
            break
    return {"status": "RESOLVED", "corrected_boe": chosen,
            "corrected_ref": cref or eli_ref, "method": method,
            "evidence": evidence}


def is_corrigendum(mdoc: boe_diario.DiarioDoc) -> bool:
    rango = mdoc.metadata.get("rango", "") or ""
    eli = mdoc.metadata.get("url_eli", "") or ""
    titulo = (mdoc.metadata.get("titulo", "") or "").upper()
    return ("/corrigendum/" in eli
            or "CORRECCI" in rango.upper()
            or titulo.startswith("CORRECCI"))


# ---------------------------------------------------------------------------
# O1 — target attribution (§14-16)
# ---------------------------------------------------------------------------


def _fmt_ref(ref: tuple[int, int] | None) -> str | None:
    return f"{ref[0]}/{ref[1]}" if ref else None


def attribute_operation(op: operations.Operation,
                        mdoc: boe_diario.DiarioDoc,
                        target_ref: tuple[int, int] | None,
                        target_boe: str) -> TargetAttribution:
    """Attribute one parsed operation to an instrument (O1).

    Deterministic precedence (§15):
      A. explicit clause ownership — an owner construction or a unique
         clause ref wins over section-level inheritance;
      B. corrigendum rule — the corrected instrument C resolves from
         official metadata; a downstream target requires explicit
         clause-level naming;
      C. section/preamble target;
      D. 0 candidates -> NOT_PROVABLE; >1 -> AMBIGUOUS.

    The reconstructed target never disambiguates a tie.
    """
    corrigendum = is_corrigendum(mdoc)
    corr = resolve_corrected_instrument(mdoc) if corrigendum else None
    clause_refs = _unique_refs(op.clause_text)
    prefix_refs = _unique_refs(op.prefix or "")
    owners = [(int(m.group(1)), int(m.group(2))) for m in
              operations._FICHERO_OWNER_RE.finditer(op.clause_text)]
    # attributive clause refs: owner construction wins; otherwise a
    # unique ref attributes the clause
    clause_attr = owners or (clause_refs if len(clause_refs) == 1 else [])
    sec_targets = list(op.section_targets or [])

    cands: list[str] = []
    for r in clause_attr + clause_refs + prefix_refs + sec_targets:
        s = _fmt_ref(r)
        if s and s not in cands:
            cands.append(s)
    section_ev = {"targets": [_fmt_ref(t) for t in sec_targets],
                  "heading": op.section_heading,
                  "heading_names": bool(
                      operations._target_refs(op.section_heading))}
    clause_ev = {"clause_refs": [_fmt_ref(r) for r in clause_refs],
                 "prefix_refs": [_fmt_ref(r) for r in prefix_refs],
                 "owners": [_fmt_ref(r) for r in owners],
                 "node_index": op.node_index}
    corrected_boe = (corr or {}).get("corrected_boe") if corr else None

    def out(status, method, chosen, reason=None):
        return TargetAttribution(
            status=status, method=method,
            candidate_instruments=tuple(cands),
            chosen_instrument=chosen,
            section_evidence=section_ev, clause_evidence=clause_ev,
            corrected_instrument=corrected_boe, reason=reason)

    # A — explicit clause ownership
    if len(clause_attr) == 1:
        ref = clause_attr[0]
        if ref == target_ref:
            return out(
                TARGET_PROVEN,
                "CORRIGENDUM_EXPLICIT_DOWNSTREAM_TARGET"
                if corrigendum else "EXPLICIT_CLAUSE_TARGET",
                _fmt_ref(ref))
        return out(FOREIGN_TARGET, "EXPLICIT_CLAUSE_TARGET",
                   _fmt_ref(ref),
                   "clause explicitly names another instrument")
    if len(clause_attr) > 1:
        if target_ref in clause_attr:
            return out(ATTR_AMBIGUOUS, "EXPLICIT_CLAUSE_TARGET", None,
                       "clause names multiple instruments including "
                       "target; target cannot disambiguate")
        return out(FOREIGN_TARGET, "EXPLICIT_CLAUSE_TARGET",
                   _fmt_ref(clause_attr[0]),
                   "clause names multiple instruments, none the target")

    # B — corrigendum rule
    if corrigendum:
        if corr["status"] == "AMBIGUOUS":
            return out(ATTR_AMBIGUOUS, "CORRIGENDUM_AMBIGUOUS_OWNER",
                       None,
                       "incompatible official corrected-instrument "
                       "evidence")
        c_boe = corr.get("corrected_boe")
        c_ref = corr.get("corrected_ref")
        target_is_c = (target_boe == c_boe) or (
            c_ref is not None and target_ref == c_ref)
        if target_is_c:
            return out(TARGET_PROVEN, "CORRIGENDUM_CORRECTED_INSTRUMENT",
                       _fmt_ref(target_ref) if target_ref else target_boe)
        return out(FOREIGN_TARGET, "CORRIGENDUM_CORRECTED_INSTRUMENT",
                   c_boe or _fmt_ref(c_ref),
                   "operation belongs to the corrected instrument; a "
                   "secondary 'CORRIGE errores' relation is not "
                   "ownership proof")

    # C — section / preamble
    if len(sec_targets) == 1:
        ref = sec_targets[0]
        if ref == target_ref:
            return out(TARGET_PROVEN,
                       "EXPLICIT_SECTION_TARGET"
                       if section_ev["heading_names"]
                       else "UNIQUE_SECTION_INHERITANCE",
                       _fmt_ref(ref))
        return out(FOREIGN_TARGET, "EXPLICIT_SECTION_TARGET",
                   _fmt_ref(ref),
                   "section declares another instrument")
    if len(sec_targets) > 1:
        if target_ref in sec_targets:
            return out(ATTR_AMBIGUOUS, "SECTION_MULTI_TARGET", None,
                       "section names multiple instruments including "
                       "target; target cannot disambiguate")
        return out(FOREIGN_TARGET, "EXPLICIT_SECTION_TARGET",
                   _fmt_ref(sec_targets[0]),
                   "section declares other instruments only")

    # unmarked-op prefix refs act like clause refs
    if len(prefix_refs) == 1:
        ref = prefix_refs[0]
        if ref == target_ref:
            return out(TARGET_PROVEN, "EXPLICIT_CLAUSE_TARGET",
                       _fmt_ref(ref))
        return out(FOREIGN_TARGET, "EXPLICIT_CLAUSE_TARGET",
                   _fmt_ref(ref),
                   "prefix names another instrument")
    if len(prefix_refs) > 1:
        return out(ATTR_AMBIGUOUS, "EXPLICIT_CLAUSE_TARGET", None,
                   "prefix names multiple instruments")

    # D — nothing
    return out(ATTR_NOT_PROVABLE, None, None,
               "no clause, section, or preamble target evidence")


# ---------------------------------------------------------------------------
# O2 — locator declaration (§20-26)
# ---------------------------------------------------------------------------


def prove_locator(op: operations.Operation,
                  sub: operations.SubjectRef) -> LocatorDeclaration:
    """Prove that the operation declared ``sub.locator_key`` in its
    governing lexical scope.

    Every key component carries declaration provenance from
    composition (explicit clause mention vs. inherited scoped frame).
    A locator carrying a qualifier the model cannot express
    ('norma 64 bis', 'apartado 2.e)') is NOT_PROVABLE — never degraded
    to its parent (§26).
    """
    key = sub.locator_key
    comps = sub.proof_components or ()
    masked = operations._masked_clause(op.clause_text)
    if operations._has_unmodelled_qualifier(masked, key):
        return LocatorDeclaration(
            LOC_NOT_PROVABLE, key, comps, op.node_index,
            "UNMODELLED_QUALIFIER",
            "clause qualifier the locator model cannot express")
    if not comps:
        return LocatorDeclaration(
            LOC_NOT_PROVABLE, key, (), op.node_index,
            "NO_COMPONENT_PROOF",
            "no declaration provenance recorded for locator")
    return LocatorDeclaration(
        LOC_PROVEN, key, comps, op.node_index,
        "COMPOSED_CLAUSE_SCOPE", None)


# ---------------------------------------------------------------------------
# O3 — subject existence / lifecycle (§31-34)
# ---------------------------------------------------------------------------

_KINDED_TAIL_RE = re.compile(
    r"\.(?:punto|apartado|letra|numeral|nota|indice|estado|fichero|"
    r"norma|anejo|disp|disposicion|seccion|pagina):")


def ancestor_keys(key: str) -> list[str]:
    """Ancestor locator keys, nearest first — a dotted value never
    starts a new component; only '.kind:' boundaries do."""
    out: list[str] = []
    k = key
    while True:
        last = None
        for m in _KINDED_TAIL_RE.finditer(k):
            last = m.start()
        if last is None:
            return out
        k = k[:last]
        out.append(k)


def expected_existence(op_kind: str, prev_hop: dict | None,
                       chain_born: bool,
                       structurally_present: bool) -> dict:
    """O3 derivation for one emitted relation (§33).

    ``prev_hop`` is the immediately-preceding emitted relation on the
    same subject in the chain's authoritative order — a bound
    after-representation proves PRESENT before a prior proven DELETE
    is consulted, since a bound new text supersedes the deletion. A
    first occurrence is PRESENT only via an ancestor born by the chain
    or structural proof in the original publication; otherwise the
    derivation abstains with UNKNOWN — never inferred ABSENT.
    """
    if op_kind == "ADD":
        return {"status": L_NOT_APPLICABLE, "method": "ADD_OPERATION",
                "predecessor_relation_id": None}
    if prev_hop and prev_hop.get("after_representation_id"):
        return {"status": L_PRESENT, "method": "CHAIN_PREDECESSOR",
                "predecessor_relation_id": prev_hop["relation_id"]}
    if prev_hop and prev_hop.get("operation_kind") == "DELETE":
        return {"status": L_DELETED, "method": "CHAIN_PREDECESSOR",
                "predecessor_relation_id": prev_hop["relation_id"]}
    if chain_born:
        return {"status": L_PRESENT, "method": "ANCESTOR_BORN_BY_CHAIN",
                "predecessor_relation_id": None}
    if structurally_present:
        return {"status": L_PRESENT,
                "method": "ORIGINAL_PUBLICATION_STRUCTURAL",
                "predecessor_relation_id": None}
    return {"status": L_UNKNOWN, "method": "NO_STRUCTURAL_PROOF",
            "predecessor_relation_id": None}


# ---------------------------------------------------------------------------
# structural presence in the original publication (§33 O3 primitive)
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).lower().strip()


_ORDINAL_WORDS = {
    "1": "primera", "2": "segunda", "3": "tercera", "4": "cuarta",
    "5": "quinta", "6": "sexta", "7": "septima", "8": "octava",
    "9": "novena", "10": "decima", "11": "undecima", "12": "duodecima",
    "13": "decima tercera", "14": "decima cuarta", "15": "decima quinta",
    "16": "decima sexta", "17": "decima septima", "18": "decima octava",
    "19": "decima novena", "20": "vigesima",
}


def _fichero_norm(text: str) -> str:
    t = re.sub(r"\s*-\s*", "-", _norm(text))
    return re.sub(r"\s*\(\s*\*+\s*\)\s*$", "", t)


_FICHERO_CONNECTORS = frozenset(
    {"a", "ante", "con", "de", "del", "e", "el", "en", "la", "las",
     "los", "para", "por", "sobre", "y"})


def _fichero_tokens(text: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"[^\w]+", _fichero_norm(text))
                 if t and t not in _FICHERO_CONNECTORS)


def _fichero_eq(a: str, b: str) -> bool:
    return _fichero_norm(a) == _fichero_norm(b) \
        or _fichero_tokens(a) == _fichero_tokens(b)


def _head_span(doc: boe_diario.DiarioDoc, pat: re.Pattern,
               articulo_only: bool) -> tuple[int, int] | None:
    start = None
    for n in doc.nodes:
        if start is None:
            ok = (n.cls == "articulo" if articulo_only else n.kind == "p")
            if ok and n.text and pat.search(_norm(n.text)):
                start = n.index
        elif n.cls == "articulo":
            return (start, n.index)
    return (start, len(doc.nodes)) if start is not None else None


def _sub_present(doc: boe_diario.DiarioDoc, span: tuple[int, int],
                 kind: str, val: str) -> bool:
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


def locator_resolves_in_doc(doc: boe_diario.DiarioDoc, key: str) -> bool:
    """Independent structural check over the official target document —
    the same derivation the frozen evaluator applies for O3.

    A headed root resolves via its heading span and each kinded
    component must occur inside it; unheaded kinds resolve by token
    presence in any node text; named fichero subjects compare on
    normalized names.
    """
    parts = key.split(".")
    kind, _, body = parts[0].partition(":")
    if kind == "norma" and body.isdigit():
        num = int(body)
        alts = {body} | {_norm(w) for w, v in
                         operations._ORDINALS.items() if v == num}
        head_alt = "|".join(re.escape(a) for a in sorted(alts))
        span = _head_span(
            doc, re.compile(
                rf"^(?:\[[^\]]*\]\s*)?norma\s+(?:{head_alt})\b"),
            articulo_only=True)
        if span is None:
            return False
        return all(":" in p and _sub_present(
            doc, span, p.split(":")[0], p.split(":")[1])
            for p in parts[1:])
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
            if not n.text:
                continue
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
