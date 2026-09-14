"""G2.1 DEV evaluator — Subject Ownership & Lifecycle.

Frozen before any ``src/regdelta`` change (G2.1 §5). Re-derives three
independent claims per emitted ``modification_relation``:

  O1 OPERATION_TARGETS_INSTRUMENT  — attribution re-derived from the
      modifier document (section/preamble/clause refs + corrigendum
      corrected-instrument resolution), never from runtime output.
  O2 OPERATION_DECLARES_LOCATOR    — the recorded locator_key must be
      composed from mentions in the clause's own lexical scope, with
      root-family exclusivity and sibling-context death.
  O3 SUBJECT_EXISTENCE_BEFORE      — lifecycle immediately before the
      operation, derived from the target document and the prior chain.

The G1 binding audit (before/after binding, chain predecessor,
resolution, verb/discovery/date claims) is preserved verbatim via the
G1 evaluator; the retired ``target_locator_resolves`` claim is
replaced by the O1/O2 pair.

Outputs (G2.1 §7): run.json, metrics.json, relations.jsonl,
operations.jsonl, attribution.jsonl, lifecycle.jsonl, bindings.jsonl,
audit.jsonl, failures.jsonl, report.md.

Usage:
    uv run python -X utf8 scripts/g2/evaluate_g2.py \
        --dev-manifest evidence/g2/dev/manifest.json \
        --targets evidence/g2/dev/targets.json \
        --gold evidence/g2/dev/declared_modifiers.json \
        --corpus evidence/g1/dev/g0-false-binding-corpus.json \
        --four-cases evidence/g2/root-cause/g1-four-cases.json \
        --output evidence/g2/dev/runs/000-baseline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                    / "scripts" / "g0g"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                    / "scripts" / "g1"))

from regdelta import applicability, db as dbm, history, \
    operations  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402
import evaluate_dev as ev  # noqa: E402
import evaluate_g1 as eg1  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
G2 = ROOT / "evidence" / "g2"

EVALUATOR_NAME = "evaluate_g2"
EVALUATOR_VERSION = "g2-v1"

# G2 root-cause classes (frozen; G0/G1 classes still apply to binding)
G2_RCC = {"RUNTIME_WRONG_TARGET_ATTRIBUTION", "RUNTIME_WRONG_LOCATOR",
          "VALID_CHAIN_BORN_LOCATOR", "G1_EVALUATOR_MODEL_ERROR",
          "OTHER"}

ATTR_STATUSES = ("TARGET_PROVEN", "FOREIGN_TARGET", "MODIFIER_LOCAL",
                 "AMBIGUOUS", "NOT_PROVABLE")

# ---------------------------------------------------------------------------
# evaluator-side structural helpers (independent derivation; shared lexical
# primitives only — same contract as the G1 audit reusing _OP_KINDS)
# ---------------------------------------------------------------------------

_TARGET_RE = re.compile(
    r"Circular\s+(?:del\s+Banco\s+de\s+Espa[ñn]a\s+)?(\d+)\s*/\s*(\d{4})",
    re.IGNORECASE)
_QUOTED = re.compile(r"«[^»]*»")

# unmarked ordinal-word items: "Cuatro. En la norma undécima ..." —
# siblings of each other; the previous item's context dies when the
# next item opens
_ORDINAL_WORD_ITEM_RE = re.compile(
    r"^(primer[oa]?|segund[oa]|tercer[oa]?|tercer|cuart[oa]|quint[oa]|"
    r"sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]|d[eé]cim[oa]|"
    r"und[eé]cim[oa]?|duod[eé]cim[oa]|uno|una|dos|tres|cuatro|cinco|"
    r"seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince)\."
    r"\s", re.IGNORECASE)

_ROOT_FAMILIES = ("norma", "anejo", "disp")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _wtext(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))


def _refs(text: str) -> list[tuple[int, int]]:
    return [(int(a), int(b))
            for a, b in _TARGET_RE.findall(_QUOTED.sub("", text))]


def _unique_refs(text: str) -> list[tuple[int, int]]:
    return list(dict.fromkeys(_refs(text)))


# evaluator-side subject mention extraction: dotted apartado values are
# single identifiers ("1.3.2"), letter enumerations expand
_LET_LIST_RE = re.compile(
    r"\bletras?\s+((?:\(?[a-z]\)?\s*(?:,|\sy\s|\se\s|\sa\s))*"
    r"\(?[a-z]\)?)", re.IGNORECASE)
_NUM_SEQ = r"\d+(?:\s*\.\s*\d+)*"
_ROMAN_SEQ = r"[IVX]+(?:\.[A-Z0-9]+)*"
_ORD_SEQ = "|".join(operations._ORDINALS)
_APART_RE = re.compile(
    r"\bapartados?\s+((?:" + _NUM_SEQ + r"|" + _ROMAN_SEQ + r")"
    r"(?:\s*(?:a|al|,|y|e)\s+(?:" + _NUM_SEQ + r"|" + _ROMAN_SEQ
    + r"))*)"
    r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|donde|y\s+el)\b|$)",
    re.IGNORECASE)
_NORMA_RE = re.compile(
    r"\bnormas?\s+((?:\d+|" + _ORD_SEQ + r")"
    r"(?:\s*(?:a|al|,|y|e)\s+(?:\d+|" + _ORD_SEQ + r"))*)"
    r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|donde|y\s+la"
    r"|y\s+el|y\s+los|y\s+las)\b|$)",
    re.IGNORECASE)
_ANEJO_RE = re.compile(
    r"\banejos?\s+(" + _NUM_SEQ +
    r"(?:\s*(?:a|al|,|y|e)\s+" + _NUM_SEQ + r")*)"
    r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|sobre|donde"
    r"|y\s+el)\b|$)",
    re.IGNORECASE)
_DISP_RE = re.compile(
    r"\bdisposici[oó]n\s+(adicional|transitoria|final|derogatoria)\s+"
    r"(\w+)", re.IGNORECASE)
_PUNTO_RE = re.compile(
    r"\bpuntos?\s+(" + _NUM_SEQ +
    r"(?:\s*(?:a|al|,|y|e)\s+" + _NUM_SEQ + r")*)"
    r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|donde|y\s+el"
    r"|sin\s+que)\b|$)",
    re.IGNORECASE)
_NUMERAL_RE = re.compile(
    r"\bnumerales?\s+([ivxlcdm]+)\s*\)?", re.IGNORECASE)
_NOTA_RE = re.compile(r"\bnotas?\s+\(?([a-z])\)?", re.IGNORECASE)
_PAGINA_RE = re.compile(r"\bp[aá]gina\s+(\d{3,6})", re.IGNORECASE)
_INDICE_RE = re.compile(r"\b[íi]ndice\b", re.IGNORECASE)
_ESTADO_RE = re.compile(
    r"\b(FI|FC|PI|PC|PA|UEM|AVE)\s*(\d[\d.]*(?:-\s*[\d.]+)?)")
_FICHERO_RE = re.compile(r"\bficheros?\s+«([^»]+)»", re.IGNORECASE)


def _letters(raw: str) -> list[str]:
    return [m.group(0).lstrip("(").rstrip(")").lower()
            for m in re.finditer(r"\(?[a-z]\)?", raw)]


def _numlist(raw: str) -> list[tuple[str, ...]]:
    """Tokenize a numeric enumeration preserving ranges and
    hierarchical values: '12 a 17' -> ('12','17'); '12, 14 y 15' ->
    singletons; '1.3.2' -> ('1.3.2',)."""
    out: list[tuple[str, ...]] = []
    for tok in re.split(r"\s*(?:,|y|e)\s+", raw):
        tok = re.sub(r"\s*\.\s*", ".", tok.strip())
        m = re.fullmatch(r"(\d+)\s+(?:a|al)\s+(\d+)", tok)
        if m:
            out.append((m.group(1), m.group(2)))
        elif re.fullmatch(r"\d+(?:\.\d+)*|[IVX]+(?:\.[A-Z0-9]+)*|" +
                          _ORD_SEQ, tok, re.IGNORECASE):
            out.append((tok,))
    return out


def _eval_mentions(text: str) -> dict[str, list]:
    """Evaluator-side subject mentions of a clause/scope fragment."""
    stripped = _QUOTED.sub("«»", text)
    out: dict[str, list] = {}
    for key, rx in (("norma", _NORMA_RE), ("anejo", _ANEJO_RE),
                    ("punto", _PUNTO_RE), ("apartado", _APART_RE)):
        vals: list[tuple[str, ...]] = []
        for m in rx.finditer(stripped):
            vals.extend(_numlist(m.group(1)))
        if vals:
            out[key] = vals
    for key, rx in (("disp", _DISP_RE), ("numeral", _NUMERAL_RE),
                    ("nota", _NOTA_RE), ("pagina", _PAGINA_RE)):
        vals = [m.groups() for m in rx.finditer(stripped)]
        if vals:
            out[key] = vals
    letras: list[str] = []
    for m in _LET_LIST_RE.finditer(stripped):
        for lt in _letters(m.group(1)):
            if lt not in letras:
                letras.append(lt)
    if letras:
        out["letra"] = letras
    # estado codes are self-identifying ('«FI 151-1 ...»'); quoted
    # content is where they are declared — match on the full text
    estados = [operations._norm_state_code(m.group(1), m.group(2))
               for m in _ESTADO_RE.finditer(text)]
    if estados:
        out["estado"] = list(dict.fromkeys(estados))
    ficheros = [re.sub(r"\s+", " ", m.group(1)).strip()
                for m in _FICHERO_RE.finditer(text)]
    if ficheros:
        out["fichero"] = ficheros
    if _INDICE_RE.search(stripped):
        out["indice"] = ["1"]
    return out


def _section_preamble_refs(doc: boe_diario.DiarioDoc,
                           node_start: int,
                           node_end: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for n in doc.nodes[node_start + 1:node_end]:
        if n.kind != "p" or n.cls not in ("parrafo", "parrafo_2") \
                or operations._marker_parts(n.text) is not None:
            break
        text = n.text.rstrip()
        if not (text.endswith(":") or "siguientes" in text.lower()):
            break
        for r in _refs(n.text):
            if r not in out:
                out.append(r)
    return out


def _sections(doc: boe_diario.DiarioDoc) -> list[dict]:
    """Evaluator-side section split: articulo headings + their targets
    (heading + leading preamble)."""
    arts = [n for n in doc.nodes if n.cls == "articulo"]
    if not arts:
        return [{"heading": "", "start": 0, "end": len(doc.nodes),
                 "targets": []}]
    bounds = [a.index for a in arts] + [len(doc.nodes)]
    secs = []
    for i, a in enumerate(arts):
        tg = _refs(a.text)
        for r in _section_preamble_refs(doc, a.index, bounds[i + 1]):
            if r not in tg:
                tg.append(r)
        secs.append({"heading": a.text, "start": a.index,
                     "end": bounds[i + 1], "targets": tg})
    return secs


def _is_setter(n: boe_diario.Node) -> bool:
    """Unmarked context-setting paragraph."""
    return n.kind == "p" and n.cls in ("parrafo", "parrafo_2") and (
        n.text.rstrip().endswith(":")
        or "siguientes" in n.text.lower())


def _is_leaf_clause(n: boe_diario.Node) -> bool:
    return operations._is_locator(n) or \
        operations._unmarked_op(n) is not None


def _leaf_clauses(doc: boe_diario.DiarioDoc,
                  sec: dict) -> list[dict]:
    """Enumerate leaf operative clauses evaluator-side with the scope
    context of each (section preamble + current ordinal-item setter +
    marker ancestors).

    Scope model (G2.1 §21–23):
      * section_ctx — preamble setters before the first marked or
        ordinal-word item;
      * item_ctx — the most recent unmarked ordinal-word setter
        ("Cinco.", "Seis."); a new ordinal item replaces it (sibling
        death); non-ordinal setters after the first item merge into
        item_ctx;
      * marker ancestors — the runtime-compatible level stack; a new
        sibling at depth d drops deeper levels.
    Root-family exclusivity is applied at composition, not here.
    """
    out: list[dict] = []
    section_ctx: dict[str, list] = {}
    item_ctx: dict[str, list] = {}
    item_active = False
    levels: list[tuple[str, int, dict]] = []   # (style, node_index, ctx)
    top_alpha = 0
    prev_container = False

    def merged() -> dict[str, list]:
        c: dict[str, list] = {k: list(v) for k, v in section_ctx.items()}
        for k, v in item_ctx.items():
            c[k] = list(v)
        for _, _, lctx in levels:
            for k, v in lctx.items():
                c[k] = list(v)
        return c

    for i in range(sec["start"] + 1, sec["end"]):
        n = doc.nodes[i]
        if n.kind not in ("p", "blockquote"):
            continue
        parts = operations._marker_parts(n.text)
        if parts is None:
            unmarked = operations._unmarked_op(n)
            if unmarked is not None:
                prefix, clause = unmarked
                if prefix:
                    tgt = item_ctx if item_active else section_ctx
                    for k, v in _eval_mentions(prefix).items():
                        tgt[k] = v
                out.append({"node_index": i, "marker": "",
                            "clause": clause,
                            "prefix": prefix,
                            "ctx": merged(),
                            "is_container": False})
                continue
            if _is_setter(n):
                if _ORDINAL_WORD_ITEM_RE.match(n.text):
                    item_ctx = _eval_mentions(n.text)
                    item_active = True
                else:
                    tgt = item_ctx if item_active else section_ctx
                    for k, v in _eval_mentions(n.text).items():
                        tgt[k] = v
            continue
        if not operations._is_locator(n):
            continue
        style, val = parts
        text = n.text.split("«", 1)[0] if n.kind == "blockquote" \
            else n.text
        container = operations._is_container(text)
        if prev_container:
            cs = "roman" if style == "amb" else style
            levels.append((cs, i, {}))
        else:
            aval = operations._alpha_value(val)
            force_top = (style == "amb" and levels
                         and levels[0][0] == "alpha"
                         and aval == top_alpha + 1)
            if force_top:
                del levels[1:]
                levels[0] = ("alpha", i, {})
                top_alpha = aval
            else:
                depth = None
                for d in range(len(levels) - 1, -1, -1):
                    if operations._compatible(style, levels[d][0]):
                        depth = d
                        break
                if depth is None:
                    levels.append((style, i, {}))
                    if len(levels) == 1 and style == "alpha":
                        top_alpha = aval
                else:
                    adopted = levels[depth][0]
                    del levels[depth:]
                    levels.append((adopted if style == "amb" else style,
                                   i, {}))
                    if depth == 0 and style in ("alpha", "amb"):
                        top_alpha = aval
        mentions = _eval_mentions(text)
        ctx = merged()
        for k, v in mentions.items():
            ctx[k] = v
        out.append({"node_index": i, "marker":
                    operations._MARKER_RE.match(n.text).group("m"),
                    "clause": text, "prefix": "",
                    "ctx": ctx, "is_container": container,
                    "own_mentions": mentions})
        levels[-1] = (levels[-1][0], i, ctx)
        prev_container = container
    return out


# ---------------------------------------------------------------------------
# corrigendum corrected-instrument resolution (G2.1 §16)
# ---------------------------------------------------------------------------

_ELI_CORR_RE = re.compile(
    r"/corrigendum/\d{8}$|/corrigendum/\d+$", re.IGNORECASE)
_ELI_CIR_RE = re.compile(r"/cir/(\d{4})/(\d{2})/(\d{2})/(\d+)")


def resolve_corrected(mdoc: boe_diario.DiarioDoc) -> dict:
    """Resolve the corrected instrument C of a corrigendum M.

    Priority: ELI /corrigendum/ path → anterior 'CORRECCIÓN de errores'
    → unique correction relation. 0 -> status NONE; incompatible
    evidence -> AMBIGUOUS.
    """
    eli = mdoc.metadata.get("url_eli", "") or ""
    eli_ref = None
    m = _ELI_CIR_RE.search(eli)
    if m and "/corrigendum/" in eli:
        eli_ref = (int(m.group(4)), int(m.group(1)))  # (num, year)

    def _corr_kind(ref) -> str | None:
        p = (ref.palabra or "").upper()
        p = p.replace("Ó", "O")
        if p.startswith("CORRECCION DE ERRORES"):
            return "PRIMARY"          # 'correction OF <anterior>'
        if p.startswith("CORRIGE ERRORES") or "CORRECCION" in p:
            return "SECONDARY"        # 'corrects errors IN <anterior>'
        return None

    primaries = [(r.referencia, r.texto) for r in mdoc.anteriores
                 if _corr_kind(r) == "PRIMARY"]
    secondary = [(r.referencia, r.texto) for r in mdoc.anteriores
                 if _corr_kind(r) == "SECONDARY"]

    chosen = None
    method = None
    ev_ = {"eli": eli or None, "eli_ref": eli_ref,
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
                "evidence": ev_}
    cref = None
    for ref, texto in primaries + secondary:
        if ref == chosen:
            cr = _unique_refs(texto)
            cref = cr[0] if len(cr) == 1 else eli_ref
            break
    return {"status": "RESOLVED", "corrected_boe": chosen,
            "corrected_ref": cref or eli_ref, "method": method,
            "evidence": ev_}


def _is_corrigendum(mdoc: boe_diario.DiarioDoc) -> bool:
    rango = mdoc.metadata.get("rango", "") or ""
    eli = mdoc.metadata.get("url_eli", "") or ""
    titulo = (mdoc.metadata.get("titulo", "") or "").upper()
    return ("/corrigendum/" in eli
            or "CORRECCI" in rango.upper()
            or titulo.startswith("CORRECCI"))


# ---------------------------------------------------------------------------
# O1 — evaluator-side target attribution
# ---------------------------------------------------------------------------


def attribute_operation(target_ref: tuple[int, int] | None,
                        target_boe: str,
                        mdoc: boe_diario.DiarioDoc,
                        clause: dict,
                        sec: dict) -> dict:
    """Expected TargetAttribution for one leaf clause.

    Order (G2.1 §15):
      A. explicit clause target wins (owner construction or unique ref);
      B. corrigendum corrected-instrument rule;
      C. section/preamble target;
      D. 0 candidates -> NOT_PROVABLE; >1 -> AMBIGUOUS.
    """
    corrigendum = _is_corrigendum(mdoc)
    corr = resolve_corrected(mdoc) if corrigendum else None
    clause_refs = _unique_refs(clause["clause"])
    prefix_refs = _unique_refs(clause.get("prefix") or "")
    owners = [(int(m.group(1)), int(m.group(2))) for m in
              operations._FICHERO_OWNER_RE.finditer(clause["clause"])]
    # attributive clause refs: owner construction wins; otherwise a
    # unique ref attributes the clause
    clause_attr = owners or (clause_refs if len(clause_refs) == 1 else [])
    sec_targets = sec["targets"]
    base = {
        "corrigendum": corrigendum,
        "corrected_instrument":
            (corr or {}).get("corrected_boe") if corr else None,
        "clause_refs": [f"{a}/{b}" for a, b in clause_refs],
        "clause_attributive_refs":
            [f"{a}/{b}" for a, b in clause_attr],
        "section_targets": [f"{a}/{b}" for a, b in sec_targets],
        "preamble_refs": [f"{a}/{b}" for a, b in prefix_refs],
    }

    def out(status, method, chosen):
        return {"status": status, "method": method,
                "chosen": chosen, **base}

    # A — explicit clause ownership
    if len(clause_attr) == 1:
        ref = clause_attr[0]
        if ref == target_ref:
            return out("TARGET_PROVEN",
                       "CORRIGENDUM_EXPLICIT_DOWNSTREAM_TARGET"
                       if corrigendum else "EXPLICIT_CLAUSE_TARGET",
                       f"{ref[0]}/{ref[1]}")
        return out("FOREIGN_TARGET", "EXPLICIT_CLAUSE_TARGET",
                   f"{ref[0]}/{ref[1]}")
    if len(clause_attr) > 1:
        if target_ref in clause_attr:
            return out("AMBIGUOUS", "EXPLICIT_CLAUSE_TARGET", None)
        return out("FOREIGN_TARGET", "EXPLICIT_CLAUSE_TARGET",
                   clause_attr[0] and
                   f"{clause_attr[0][0]}/{clause_attr[0][1]}")

    # B — corrigendum rule
    if corrigendum:
        if corr["status"] == "AMBIGUOUS":
            return out("AMBIGUOUS", "CORRIGENDUM_AMBIGUOUS_OWNER",
                       None)
        c_boe = corr.get("corrected_boe")
        c_ref = corr.get("corrected_ref")
        target_is_c = (target_boe == c_boe) or (
            c_ref is not None and target_ref == c_ref)
        if target_is_c:
            return out("TARGET_PROVEN",
                       "CORRIGENDUM_CORRECTED_INSTRUMENT",
                       f"{target_ref[0]}/{target_ref[1]}"
                       if target_ref else target_boe)
        return out("FOREIGN_TARGET",
                   "CORRIGENDUM_CORRECTED_INSTRUMENT",
                   c_boe or (f"{c_ref[0]}/{c_ref[1]}"
                             if c_ref else None))

    # C — section / preamble
    if len(sec_targets) == 1:
        ref = sec_targets[0]
        if ref == target_ref:
            head_names = bool(_refs(sec["heading"]))
            return out("TARGET_PROVEN",
                       "EXPLICIT_SECTION_TARGET" if head_names
                       else "UNIQUE_SECTION_INHERITANCE",
                       f"{ref[0]}/{ref[1]}")
        return out("FOREIGN_TARGET", "EXPLICIT_SECTION_TARGET",
                   f"{ref[0]}/{ref[1]}")
    if len(sec_targets) > 1:
        if target_ref in sec_targets:
            return out("AMBIGUOUS", "SECTION_MULTI_TARGET", None)
        return out("FOREIGN_TARGET", "EXPLICIT_SECTION_TARGET",
                   f"{sec_targets[0][0]}/{sec_targets[0][1]}")

    # unmarked-op prefix refs act like clause refs
    if len(prefix_refs) == 1:
        ref = prefix_refs[0]
        if ref == target_ref:
            return out("TARGET_PROVEN", "EXPLICIT_CLAUSE_TARGET",
                       f"{ref[0]}/{ref[1]}")
        return out("FOREIGN_TARGET", "EXPLICIT_CLAUSE_TARGET",
                   f"{ref[0]}/{ref[1]}")
    if len(prefix_refs) > 1:
        return out("AMBIGUOUS", "EXPLICIT_CLAUSE_TARGET", None)

    # D — nothing
    return out("NOT_PROVABLE", None, None)


# ---------------------------------------------------------------------------
# O2 — evaluator-side locator declaration
# ---------------------------------------------------------------------------


def _norm_val(v: str) -> str:
    return re.sub(r"\s+", "", v.lower())


def _kind_mentions(mentions: dict[str, list], kind: str) -> list[str]:
    """Normalized values mentioned for a key kind."""
    vals = mentions.get(kind) or []
    out = []
    for v in vals:
        if isinstance(v, tuple):
            out.append(_norm_val(" ".join(g or "" for g in v)))
        else:
            out.append(_norm_val(str(v)))
    return out


def _merged_mentions(clause_mentions: dict[str, list],
                     scope_mentions: dict[str, list]) -> dict[str, list]:
    """Union without mutating/aliasing — scope lists may be the same
    objects as the clause's own mentions."""
    all_m: dict[str, list] = {k: list(v)
                              for k, v in clause_mentions.items()}
    for k, v in scope_mentions.items():
        all_m[k] = all_m.get(k, []) + list(v)
    return all_m


def _declared_in(kind: str, val: str,
                 all_m: dict[str, list]) -> bool:
    """Is `kind:val` declared among the merged mentions? Range tuples
    ('12','17') count as membership; ordinals resolve for norma."""
    val = _norm_val(val)
    if kind == "disp":
        tipo, _, ordinal = val.partition(".")
        for m in all_m.get("disp") or []:
            t, o = m[0], (m[1] if len(m) > 1 else "")
            if _norm_val(t) == tipo and _norm_val(str(o)) == ordinal:
                return True
        return False
    if kind == "estado":
        return val in set(_kind_mentions(all_m, "estado"))
    if kind == "fichero":
        toks = set(re.findall(r"\w+", val))
        for f in all_m.get("fichero") or []:
            ftoks = set(re.findall(r"\w+", _norm_val(str(f))))
            if toks & ftoks or val in _norm_val(str(f)):
                return True
        return False
    kinds = (kind,) if kind not in ("punto", "apartado") \
        else ("punto", "apartado")
    for k in kinds:
        for m in all_m.get(k) or []:
            if isinstance(m, tuple):
                if len(m) >= 2 and m[0].isdigit() \
                        and m[1].isdigit() and val.isdigit():
                    if int(m[0]) <= int(val) <= int(m[1]):
                        return True
                v = str(m[0])
            else:
                v = str(m)
            if _norm_val(v) == val:
                return True
            if kind == "norma" and val.isdigit():
                n = operations._ordinal_num(v)
                if n is not None and n == int(val):
                    return True
    return False


def _bare_declared(val: str, all_m: dict[str, list]) -> bool:
    """A kindless key component ('.2', '.3') is declared if witnessed
    as a value of any sub-locator kind in scope."""
    return any(_declared_in(k, val, all_m)
               for k in ("punto", "apartado", "numeral", "letra",
                         "nota", "pagina"))


def _consume_component(parts: list[str], i: int,
                       all_m: dict[str, list]) -> tuple[bool, int]:
    """Check parts[i]; a kinded component may absorb following bare
    parts into one hierarchical value ('apartado:II' + 'B' + '2' ->
    'II.B.2'; 'estado:FI 131-2' + '2' -> 'FI 131-2.2'). Returns
    (declared, next_index)."""
    kind, sep, val = parts[i].partition(":")
    if not sep:
        return _bare_declared(val, all_m) or \
            bool(all_m.get(kind)), i + 1
    j = i
    while j + 1 < len(parts) and ":" not in parts[j + 1]:
        j += 1
    # longest merge first: 'FI 131-2.2' is more specific than
    # 'FI 131-2' when both are declared
    for k in range(j, i, -1):
        mv = val + "." + ".".join(parts[i + 1:k + 1])
        if _declared_in(kind, mv, all_m):
            return True, k + 1
    return _declared_in(kind, val, all_m), i + 1


def _root_family(kind: str) -> str | None:
    return {"norma": "norma", "anejo": "anejo", "disp": "disp",
            "estado": "estado", "fichero": "fichero"}.get(kind)


def o2_locator_check(locator_key: str, clause: dict) -> dict:
    """Verify the recorded locator_key is declared by the clause's own
    lexical scope.

    Fails when:
      * any key component has no mention in clause or governing scope;
      * the clause (or its governing setter) declares an explicit root
        of family F while the key's head belongs to a different root
        family G (root exclusivity);
      * the recorded deep value differs from the declared one
        ('apartado 1.3.2' recorded as 'apartado:1').
    """
    clause_mentions = clause.get("own_mentions") or \
        _eval_mentions(clause["clause"])
    scope = clause.get("ctx") or {}
    parts = locator_key.split(".")
    # 'disp:transitoria.tercera' — the head spans two segments
    if parts[0].startswith("disp:") and len(parts) > 1 \
            and ":" not in parts[1]:
        parts = [".".join(parts[:2])] + parts[2:]
    head = parts[0]
    head_kind = head.split(":", 1)[0]
    declared_roots = {f for f in _ROOT_FAMILIES
                      if clause_mentions.get(f)}
    scope_roots = {f for f in _ROOT_FAMILIES if scope.get(f)}
    key_root = _root_family(head_kind)
    if key_root in ("norma", "anejo", "disp"):
        # an explicit root of a different family anywhere in scope or
        # clause displaces an inherited head of family key_root only
        # when key_root itself is NOT explicitly declared
        if key_root not in declared_roots and key_root not in scope_roots:
            return {"verdict": "CONTRADICTED",
                    "reason": f"locator head '{head}' has no root "
                              f"declaration in clause scope"}
        if declared_roots and key_root not in declared_roots:
            return {"verdict": "CONTRADICTED",
                    "reason": f"explicit {sorted(declared_roots)} root "
                              f"displaces inherited '{head_kind}'"}
        if scope_roots and key_root not in scope_roots \
                and key_root not in declared_roots:
            return {"verdict": "CONTRADICTED",
                    "reason": f"scope root {sorted(scope_roots)} "
                              f"displaces '{head_kind}'"}
    all_m = _merged_mentions(clause_mentions, scope)
    i = 0
    while i < len(parts):
        ok, i = _consume_component(parts, i, all_m)
        if not ok:
            return {"verdict": "CONTRADICTED",
                    "reason": f"component '{parts[i - 1]}' not "
                              f"declared in clause scope"}
    return {"verdict": "VERIFIED", "reason": None}


# ---------------------------------------------------------------------------
# O3 — evaluator-side existence-before
# ---------------------------------------------------------------------------


def o3_expected(r: dict, tdoc: boe_diario.DiarioDoc | None,
                prev_hop: dict | None,
                chain_born: bool) -> dict:
    """Expected SUBJECT_EXISTENCE_BEFORE (abstention-capable)."""
    if r["operation_kind"] == "ADD":
        return {"status": "NOT_APPLICABLE", "method": "ADD_OPERATION"}
    if prev_hop and prev_hop.get("after_representation_id"):
        return {"status": "PRESENT", "method": "CHAIN_PREDECESSOR",
                "predecessor_relation_id": prev_hop["relation_id"]}
    if prev_hop and prev_hop.get("operation_kind") == "DELETE":
        return {"status": "DELETED", "method": "CHAIN_PREDECESSOR",
                "predecessor_relation_id": prev_hop["relation_id"]}
    if chain_born:
        return {"status": "PRESENT", "method": "ANCESTOR_BORN_BY_CHAIN"}
    if tdoc is not None and eg1._locator_resolves_g1(
            tdoc, r["locator_key"]):
        return {"status": "PRESENT",
                "method": "ORIGINAL_PUBLICATION_STRUCTURAL"}
    return {"status": "UNKNOWN", "method": "NO_STRUCTURAL_PROOF"}


# ---------------------------------------------------------------------------
# clause-node location for emitted relations
# ---------------------------------------------------------------------------


def _find_clause_node(mdoc: boe_diario.DiarioDoc, locator_raw: str,
                      key: str, lix: dict | None = None
                      ) -> tuple[int | None, str]:
    """Locate the operative clause node: exact text containment first,
    locator-mention search as fallback.  When several nodes carry the
    same clause text (e.g. 'i) Se sustituye el índice…' under anejo 4
    and anejo 5), prefer the one whose scope declares the key's head."""
    want = ev._norm(locator_raw)
    if want:
        head, _, _ = key.partition(".")
        hk, _, hv = head.partition(":")
        cands = []
        for n in mdoc.nodes:
            if not n.text:
                continue
            tn = ev._norm(n.text)
            # locator_raw is the clause text: either contained in the
            # node (unmarked fused / blockquote prefix) or the node is
            # its own continuation
            if want in tn or (len(tn) >= 40
                              and tn.startswith(want[:40])):
                cands.append(n.index)
        if len(cands) > 1 and lix is not None and hv:
            scoped = []
            for ni in cands:
                c = lix.get(ni)
                if c is None:
                    continue
                am = _merged_mentions(
                    c.get("own_mentions") or {}, c.get("ctx") or {})
                if _declared_in(hk, hv, am):
                    scoped.append(ni)
            if scoped:
                return scoped[0], "locator_raw"
        if cands:
            return cands[0], "locator_raw"
    clause = eg1.find_op_clause(mdoc, key)
    if clause is not None:
        cnorm = ev._norm(clause)
        for n in mdoc.nodes:
            if n.text and ev._norm(n.text) == cnorm:
                return n.index, "doc_search"
    return None, "not_found"


# ---------------------------------------------------------------------------
# per-target evaluation
# ---------------------------------------------------------------------------


def _leaf_index(doc: boe_diario.DiarioDoc) -> dict[int, dict]:
    """node_index -> leaf-clause record (with scope ctx), all sections."""
    idx: dict[int, dict] = {}
    for sec in _sections(doc):
        for c in _leaf_clauses(doc, sec):
            c["section"] = sec
            idx[c["node_index"]] = c
    return idx


def evaluate_target(target: str, cell: str, by_url: dict[str, dict],
                    gold: dict, run_id: str, tmp_root: Path) -> dict:
    data_dir = tmp_root / target
    data_dir.mkdir(parents=True)
    conn = dbm.connect(data_dir / "regdelta.sqlite")
    try:
        return _evaluate_target(target, cell, by_url, gold, run_id,
                                data_dir, conn)
    finally:
        conn.close()


def _evaluate_target(target: str, cell: str,
                     by_url: dict[str, dict], gold: dict, run_id: str,
                     data_dir: Path, conn) -> dict:
    failures = []
    try:
        report = history.reconstruct(
            conn, data_dir, target, ev.evidence_fetch(by_url))
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        failures.append({"target": target, "stage": "reconstruct",
                         "failure_class": "QUERY_EVALUATION_FAILURE",
                         "symptom": f"{type(exc).__name__}: {exc}",
                         "status": "OPEN"})
        return {"target": target, "cell": cell, "error": str(exc),
                "failures": failures}

    rows = ev.relation_rows(conn)
    proof_by_rid = {r[0]: json.loads(r[1]) for r in conn.execute(
        "SELECT relation_id, binding_proof"
        " FROM modification_relations")}
    subj_by_rid = {}
    try:
        subj_by_rid = {r[0]: json.loads(r[1]) for r in conn.execute(
            "SELECT relation_id, subject_proof"
            " FROM modification_relations")}
    except Exception:
        pass  # pre-G2 schema has no subject_proof
    for r in rows:
        r["binding_proof"] = proof_by_rid.get(r["relation_id"], {})
        r["subject_proof"] = subj_by_rid.get(r["relation_id"], {})
    rows_by_id = {r["relation_id"]: r for r in rows}

    gdecl = gold.get(target, {}).get("declared", [])
    gold_ids = {d["modifier_boe_id"] for d in gdecl}
    gold_palabra = {d["modifier_boe_id"]: d["palabra"] for d in gdecl}
    meta_texts = {d.get("texto", "").strip() for d in gdecl}
    discovered = {m["boe_id"] for m in report.get("modifiers", [])}
    rev = {r[0] for r in conn.execute(
        """SELECT i.boe_id FROM instrument_relations ir
           JOIN instruments i
             ON i.instrument_id = ir.declaring_instrument_id
           WHERE ir.direction='ANTERIOR' AND ir.other_boe_id=?""",
        (target,))}
    rec = [m for m in gold_ids if m in discovered and m in rev]
    for m in sorted(gold_ids - discovered):
        failures.append({"target": target, "modifier": m,
                         "stage": "discovery",
                         "failure_class": "OPERATION_PARSER_FAILURE",
                         "symptom": "gold modifier not discovered",
                         "status": "OPEN"})
    for m in sorted(gold_ids & discovered - rev):
        failures.append({"target": target, "modifier": m,
                         "stage": "discovery",
                         "failure_class": "OPERATION_PARSER_FAILURE",
                         "symptom": "no reverse ANTERIOR link",
                         "status": "OPEN"})
    for fe in report.get("fetch_errors", []):
        failures.append({"target": target, "stage": "acquire",
                         "failure_class": "ACQUISITION_FAILURE",
                         "symptom": str(fe), "status": "OPEN"})

    # -- target circular ref -------------------------------------------
    tdoc = None
    txml = ev.dev_xml(by_url, target)
    if txml is not None:
        tres = boe_diario.parse_diario(txml)
        tdoc = tres.doc
    target_ref = None
    if tdoc is not None:
        m = re.search(r"Circular\s+(\d+)\s*/\s*(\d{4})",
                      tdoc.metadata.get("titulo", ""), re.IGNORECASE)
        if m:
            target_ref = (int(m.group(1)), int(m.group(2)))

    # -- evaluator-side operation inventory per modifier ----------------
    op_inventory: list[dict] = []
    attr_rows: list[dict] = []
    mod_docs: dict[str, boe_diario.DiarioDoc] = {}
    for m in report.get("modifiers", []):
        mb = m["boe_id"]
        xml = ev.dev_xml(by_url, mb)
        if xml is None:
            failures.append({"target": target, "modifier": mb,
                             "stage": "acquire",
                             "failure_class": "ACQUISITION_FAILURE",
                             "symptom": "modifier XML not in evidence",
                             "status": "OPEN"})
            continue
        mres = boe_diario.parse_diario(xml)
        if not mres.doc:
            continue
        mod_docs[mb] = mres.doc
        leaf_ix = _leaf_index(mres.doc)
        secs = _sections(mres.doc)
        sec_of = {i: s for s in secs
                  for i in range(s["start"], s["end"])}
        for ni, c in sorted(leaf_ix.items()):
            if c["is_container"]:
                continue
            sec = sec_of.get(ni, {"targets": [], "heading": "",
                                  "start": 0, "end": 0})
            att = attribute_operation(target_ref, target, mres.doc,
                                      c, sec)
            rec_ = {"target": target, "modifier": mb,
                    "node_index": ni,
                    "clause_excerpt": c["clause"][:200],
                    "expected_status": att["status"],
                    "expected_method": att["method"],
                    "chosen": att["chosen"],
                    "section_targets": att["section_targets"],
                    "clause_refs": att["clause_refs"],
                    "corrigendum": att["corrigendum"],
                    "corrected_instrument":
                        att["corrected_instrument"]}
            attr_rows.append(rec_)
            op_inventory.append({"target": target, "modifier": mb,
                                 "node_index": ni,
                                 "leaf": True,
                                 "expected_status": att["status"]})

    # runtime's own accounting (post-G2.1 reports it; baseline has none)
    inv = report.get("operation_inventory") or {}
    if inv:
        leaf_parsed = inv.get("leaf_operations_parsed", 0)
        dispo = inv.get("attribution_dispositions", {})
        if leaf_parsed != sum(dispo.values()):
            failures.append({
                "target": target, "stage": "attribution",
                "failure_class": "PROTOCOL_FAILURE",
                "symptom": f"leaf_operations_parsed={leaf_parsed} "
                           f"!= dispositions {dispo}",
                "status": "OPEN"})

    # -- applicability (unchanged) --------------------------------------
    app_eligible, app_ok = [], []
    for m in report.get("modifiers", []):
        mb = m["boe_id"]
        xml = ev.dev_xml(by_url, mb)
        if xml is None or not ev.modifier_declares_applicability(xml):
            continue
        app_eligible.append(mb)
        try:
            applicability.build(conn, data_dir, mb, target)
            conn.commit()
            n = conn.execute(
                """SELECT COUNT(*) FROM applicability_clauses c
                   JOIN instruments i
                     ON i.instrument_id = c.declaring_instrument_id
                   WHERE i.boe_id=?""", (mb,)).fetchone()[0]
            if n > 0:
                app_ok.append(mb)
            else:
                failures.append({"target": target, "modifier": mb,
                                 "stage": "applicability",
                                 "failure_class":
                                 "OPERATION_PARSER_FAILURE",
                                 "symptom": "disposicion sections "
                                            "present but 0 clauses",
                                 "status": "OPEN"})
        except Exception as exc:  # noqa: BLE001
            failures.append({"target": target, "modifier": mb,
                             "stage": "applicability",
                             "failure_class":
                             "QUERY_EVALUATION_FAILURE",
                             "symptom": f"{type(exc).__name__}: {exc}",
                             "status": "OPEN"})

    # -- docs for the binding audit -------------------------------------
    docs: dict[str, boe_diario.DiarioDoc] = dict(mod_docs)
    for bid in {target} | {r["before_instrument"] for r in rows
                           if r["before_instrument"]} | \
            {r["after_instrument"] for r in rows
             if r["after_instrument"]}:
        if bid in docs:
            continue
        xml = ev.dev_xml(by_url, bid)
        if xml is not None:
            res = boe_diario.parse_diario(xml)
            if res.doc:
                docs[bid] = res.doc

    # -- chain context (as G1) ------------------------------------------
    by_sub: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda x: (x["publication_date"] or "",
                                         x["relation_id"])):
        by_sub.setdefault(r["locator_key"], []).append(r)
    chain_ctxs: dict[str, dict] = {}
    for key, hops in by_sub.items():
        for i, r in enumerate(hops):
            chain_ctxs[r["relation_id"]] = {
                r["locator_key"]: {
                    "after_id": hops[i - 1]["after_representation_id"],
                    "relation_id": hops[i - 1]["relation_id"],
                    "operation_kind": hops[i - 1]["operation_kind"]}} \
                if i > 0 else {}
    for r in rows:
        parts = r["locator_key"].split(".")
        ancestors = {".".join(parts[:i])
                     for i in range(1, len(parts))}
        born = any(
            h["after_representation_id"]
            and (h["publication_date"] or "")
            < (r["publication_date"] or "")
            for a in ancestors for h in by_sub.get(a, []))
        if born:
            chain_ctxs.setdefault(r["relation_id"], {})[
                "_ancestor_born"] = True

    # -- audit ----------------------------------------------------------
    leaf_ixs = {mb: _leaf_index(d) for mb, d in mod_docs.items()}
    audit_rows, bindings_rows, lifecycle_rows = [], [], []
    for r in rows:
        ctx = chain_ctxs.get(r["relation_id"], {})
        a = eg1.audit_relation(r, docs, by_url, gold_ids, gold_palabra,
                               meta_texts, ctx, target, rows_by_id)
        # retire the conflated G1 claim; O1/O2 replace it
        a["claims_checked"].pop("target_locator_resolves", None)

        # O1 — re-derived attribution
        mdoc = mod_docs.get(r["modifier_boe"])
        o1 = {"status": "NOT_CHECKABLE", "reason": "modifier doc absent"}
        o2 = {"verdict": "NOT_CHECKABLE", "reason": "modifier doc absent"}
        if mdoc is not None:
            lix = leaf_ixs[r["modifier_boe"]]
            ni, how = _find_clause_node(mdoc, r["locator_raw"] or "",
                                        r["locator_key"], lix)
            clause = lix.get(ni) if ni is not None else None
            if clause is None and ni is not None:
                sec = next((s for s in _sections(mdoc)
                            if s["start"] <= ni < s["end"]),
                           {"targets": [], "heading": "",
                            "start": 0, "end": 0})
                node = mdoc.nodes[ni]
                clause = {"node_index": ni, "marker": "",
                          "clause": node.text, "prefix": "",
                          "ctx": {}, "is_container": False,
                          "section": sec}
            if clause is not None:
                att = attribute_operation(
                    target_ref, target, mdoc, clause,
                    clause.get("section") or {})
                o1 = {"status": att["status"], "method": att["method"],
                      "chosen": att["chosen"],
                      "corrected_instrument":
                          att["corrected_instrument"],
                      "clause_source": how}
                o2 = o2_locator_check(r["locator_key"], clause)
                o2["clause_source"] = how

        prev = (ctx.get(r["locator_key"]) or {}) if ctx else {}
        o3 = o3_expected(
            r, docs.get(target),
            {"after_representation_id": prev.get("after_id"),
             "relation_id": prev.get("relation_id"),
             "operation_kind": prev.get("operation_kind")}
            if prev else None,
            bool(ctx.get("_ancestor_born")))

        a["claims_checked"]["o1_targets_instrument"] = (
            "VERIFIED" if o1["status"] == "TARGET_PROVEN"
            else "NOT_CHECKABLE" if o1["status"] == "NOT_CHECKABLE"
            else "CONTRADICTED")
        a["claims_checked"]["o2_declares_locator"] = o2["verdict"]
        sp = r.get("subject_proof") or {}
        sp_o3 = ((sp.get("existence_before") or {}).get("status"))
        if sp_o3 in ("PRESENT", "ABSENT", "DELETED") \
                and o3["status"] in ("PRESENT", "ABSENT", "DELETED") \
                and sp_o3 != o3["status"]:
            a["claims_checked"]["o3_existence_before"] = "CONTRADICTED"
        else:
            a["claims_checked"]["o3_existence_before"] = "VERIFIED" \
                if sp_o3 else "NOT_CHECKABLE"

        bad = [k for k, v in a["claims_checked"].items()
               if v in ("CONTRADICTED", "BINDING_FALSE")]
        rcc = sorted({eg1.CLAIM_RCC.get(k, "QUERY_EVALUATION_FAILURE")
                      for k in bad})
        if a["claims_checked"].get(
                "o1_targets_instrument") == "CONTRADICTED":
            rcc.append("RUNTIME_WRONG_TARGET_ATTRIBUTION")
        if a["claims_checked"].get(
                "o2_declares_locator") == "CONTRADICTED":
            rcc.append("RUNTIME_WRONG_LOCATOR")
        a["truth_verdict"] = "FALSE_FACT" if bad else "PASS"
        a["root_cause_class"] = sorted(set(rcc))
        a["false_binding"] = any(
            a["claims_checked"].get(s) == "BINDING_FALSE"
            for s in ("before_binding", "after_binding"))
        a["false_subject_attribution"] = a["claims_checked"].get(
            "o1_targets_instrument") == "CONTRADICTED"
        a["false_locator_declaration"] = a["claims_checked"].get(
            "o2_declares_locator") == "CONTRADICTED"
        a["o1"] = o1
        a["o2"] = o2
        a["o3_expected"] = o3
        a.update(run_id=run_id, target=target,
                 relation_id=r["relation_id"],
                 locator_key=r["locator_key"],
                 modifier=r["modifier_boe"],
                 operation_kind=r["operation_kind"],
                 evidence_quote=None)
        audit_rows.append(a)
        for side in ("before", "after"):
            bindings_rows.append({
                "run_id": run_id, "target": target,
                "relation_id": r["relation_id"], "side": side,
                "locator_key": r["locator_key"],
                "representation_id": r[f"{side}_representation_id"],
                "verdict": a["claims_checked"][f"{side}_binding"],
                "locator": r[f"{side}_locator"]})
        lifecycle_rows.append({
            "run_id": run_id, "target": target,
            "relation_id": r["relation_id"],
            "locator_key": r["locator_key"],
            "modifier": r["modifier_boe"],
            "expected_existence_before": o3["status"],
            "expected_method": o3["method"],
            "declared_existence_before": sp_o3})
        if a["truth_verdict"] == "FALSE_FACT":
            failures.append({
                "target": target, "relation_id": r["relation_id"],
                "stage": "audit", "failure_class":
                "QUERY_EVALUATION_FAILURE",
                "symptom": "FALSE_FACT: " + ", ".join(
                    a["root_cause_class"]),
                "status": "OPEN"})

    for an in report.get("anomalies", []):
        failures.append({"target": target, "stage": "reconstruct",
                         "failure_class": "OPERATION_PARSER_FAILURE",
                         "symptom": json.dumps(an, ensure_ascii=False)
                         [:300], "status": "OPEN"})

    qres = ev.run_queries(conn, target, rows)
    for name, res in qres.items():
        if res["status"] != "OK":
            failures.append({"target": target, "stage": "query",
                             "failure_class":
                             "QUERY_EVALUATION_FAILURE",
                             "symptom": f"{name}: {res['error']}",
                             "status": "OPEN"})

    chains = ev.chain_metrics(conn)
    n_rel = len(rows)
    attr_dist = Counter(a["expected_status"] for a in attr_rows)
    metrics = {
        "declared_modifier_recall": {
            "num": len(rec), "den": len(gold_ids),
            "value": len(rec) / len(gold_ids) if gold_ids else None},
        "operation_parsing_rate": {
            "num": sum(1 for r in rows
                       if r["operation_kind"] in ev.VALID_OPS),
            "den": n_rel,
            "value": (sum(1 for r in rows
                          if r["operation_kind"] in ev.VALID_OPS)
                      / n_rel) if n_rel else None},
        "representation_binding": {
            "num": sum(1 for r in rows if ev.required_bound(r)),
            "den": n_rel,
            "value": (sum(1 for r in rows if ev.required_bound(r))
                      / n_rel) if n_rel else None},
        "chain_reconstruction": {
            "num": chains["CHAIN_PROVEN"],
            "den": chains["multi_hop_subjects"],
            "value": (chains["CHAIN_PROVEN"]
                      / chains["multi_hop_subjects"])
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
            sum(1 for a in audit_rows
                if a["truth_verdict"] == "FALSE_FACT"),
        "false_binding_count":
            sum(1 for a in audit_rows if a["false_binding"]),
        "false_subject_attribution_count":
            sum(1 for a in audit_rows
                if a["false_subject_attribution"]),
        "false_locator_declaration_count":
            sum(1 for a in audit_rows
                if a["false_locator_declaration"]),
        "source_limitations":
            sum(1 for f in failures
                if f["failure_class"] == "SOURCE_LIMITATION"),
        "evaluator_attribution_distribution": dict(attr_dist),
    }

    inventory = {
        "subjects": conn.execute("SELECT COUNT(*) FROM subjects")
        .fetchone()[0],
        "representations":
            conn.execute("SELECT COUNT(*) FROM representations")
            .fetchone()[0],
        "relations": n_rel,
        "resolution": dict(conn.execute(
            "SELECT resolution, COUNT(*) FROM modification_relations"
            " GROUP BY 1").fetchall()),
        "anomalies": report.get("anomaly_count", 0),
        "runtime_operation_inventory": inv,
        "evaluator_leaf_operations": len(op_inventory),
    }
    return {"target": target, "cell": cell,
            "report": {"modifiers": report.get("modifiers", [])},
            "metrics": metrics, "inventory": inventory,
            "query_execution": qres,
            "app_eligible": app_eligible,
            "NON_GATE_DIAGNOSTIC": {
                "gold_count": len(gold_ids),
                "discovered_count": len(discovered),
                "reverse_cross_checked_count": len(rec),
                "chains": chains},
            "audit": audit_rows, "bindings": bindings_rows,
            "lifecycle": lifecycle_rows,
            "operations": op_inventory,
            "attribution": attr_rows,
            "failures": failures, "relations": rows,
            "chain_ctx": chain_ctxs}


# ---------------------------------------------------------------------------
# G1.2 four-case reclassification (stable identity, not just relation_id)
# ---------------------------------------------------------------------------


def reclassify_four_cases(four: dict, all_rows: dict[str, list[dict]],
                          audits: dict[str, dict]) -> dict:
    results = []
    counts = Counter()
    for c in four["cases"]:
        rows = all_rows.get(c["target"], [])
        # stable identity: modifier + (old relation_id OR locator/op)
        matches = [r for r in rows
                   if r["modifier_boe"] == c["modifier"]
                   and (r["relation_id"] == c["old_relation_id"]
                        or (r["locator_key"] == c["locator_key"]
                            and r["operation_kind"]
                            == c["operation_kind"]))]
        audits_m = [audits.get(r["relation_id"]) for r in matches]
        outcome = None
        if not matches:
            outcome = "NOT_EMITTED"
        else:
            bad = [a for a in audits_m
                   if a and a["truth_verdict"] == "FALSE_FACT"]
            outcome = "REPRODUCED_FALSE_FACT" if bad else "CLEAN"
        counts[outcome] += 1
        results.append({
            "old_relation_id": c["old_relation_id"],
            "target": c["target"], "modifier": c["modifier"],
            "locator_key": c["locator_key"],
            "expected_root_cause": c["new_root_cause"],
            "matched_relation_ids":
                [r["relation_id"] for r in matches],
            "matched_locator_keys":
                sorted({r["locator_key"] for r in matches}),
            "new_root_cause_classes": sorted({
                rc for a in audits_m if a
                for rc in a["root_cause_class"]}),
            "outcome": outcome})
    return {"total": len(results), "counts": dict(counts),
            "cases": results}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def run_split(targets: dict[str, str], by_url: dict[str, dict],
              gold: dict, corpus: dict, four: dict,
              run_id: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_audit, all_bindings, all_failures = [], [], []
    all_ops, all_attr, all_life = [], [], []
    all_rows: dict[str, list[dict]] = {}
    audits_by_rid: dict[str, dict] = {}
    per_target = {}
    with tempfile.TemporaryDirectory() as tmp:
        for t in sorted(targets):
            print(f"evaluating {t} ({targets[t]})", flush=True)
            res = evaluate_target(t, targets[t], by_url, gold,
                                  run_id, Path(tmp))
            per_target[t] = {k: v for k, v in res.items()
                             if k not in ("audit", "bindings",
                                          "failures", "relations",
                                          "chain_ctx", "lifecycle",
                                          "operations", "attribution")}
            all_rows[t] = res.get("relations", [])
            for a in res.get("audit", []):
                audits_by_rid[a["relation_id"]] = a
            all_audit += res.get("audit", [])
            all_bindings += res.get("bindings", [])
            all_life += res.get("lifecycle", [])
            all_ops += res.get("operations", [])
            all_attr += res.get("attribution", [])
            all_failures += res.get("failures", [])

    corpus_result = eg1.reclassify_corpus(corpus, all_rows,
                                          audits_by_rid, {})
    four_result = reclassify_four_cases(four, all_rows, audits_by_rid)

    def agg(key):
        num = sum(v["metrics"][key]["num"]
                  for v in per_target.values())
        den = sum(v["metrics"][key]["den"]
                  for v in per_target.values())
        return {"num": num, "den": den,
                "value": num / den if den else None}

    metric_keys = ("declared_modifier_recall", "operation_parsing_rate",
                   "representation_binding", "chain_reconstruction",
                   "applicability_extraction", "query_execution")
    metrics = {k: agg(k) for k in metric_keys}
    for k in ("false_positive_facts", "false_binding_count",
              "false_subject_attribution_count",
              "false_locator_declaration_count", "source_limitations"):
        metrics[k] = sum(v["metrics"][k] for v in per_target.values())
    metrics["old_false_fact_reproduction_count"] = \
        corpus_result["counts"].get("REPRODUCED_FALSE_FACT", 0)
    metrics["g1_four_case_reproduction_count"] = \
        four_result["counts"].get("REPRODUCED_FALSE_FACT", 0)
    metrics["evaluator_attribution_distribution"] = dict(
        Counter(a["expected_status"] for a in all_attr))
    metrics["evaluator_lifecycle_distribution"] = dict(
        Counter(l["expected_existence_before"] for l in all_life))

    _wtext(out_dir / "metrics.json", json.dumps(
        {"aggregate": metrics,
         "per_target": {t: v["metrics"]
                        for t, v in per_target.items()},
         "corpus_73": corpus_result["counts"],
         "four_cases": four_result["counts"]},
        indent=2, sort_keys=True) + "\n")
    _wtext(out_dir / "targets.json", json.dumps(
        per_target, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    def _dump(name, rows_):
        with (out_dir / name).open("w", encoding="utf-8",
                              newline="") as fh:
            for x in rows_:
                fh.write(json.dumps(x, ensure_ascii=False) + "\n")

    _dump("audit.jsonl", all_audit)
    _dump("bindings.jsonl", all_bindings)
    _dump("failures.jsonl", all_failures)
    _dump("lifecycle.jsonl", all_life)
    _dump("operations.jsonl", all_ops)
    _dump("attribution.jsonl", all_attr)
    _dump("relations.jsonl", [
        {**{k: r[k] for k in ("relation_id", "kind", "operation_kind",
                              "locator_key", "modifier_boe",
                              "publication_date", "resolution",
                              "before_representation_id",
                              "after_representation_id")},
         "target": t}
        for t, rows in all_rows.items() for r in rows])
    _wtext(out_dir / "corpus-73.json", json.dumps(
        corpus_result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    _wtext(out_dir / "four-cases.json", json.dumps(
        four_result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    lines = ["# G2.1 DEV evaluation", "", f"run_id: {run_id}", "",
             "| target | relations | FALSE_FACT | FALSE_BINDING | "
             "FALSE_ATTR | FALSE_LOC |",
             "|---|---|---|---|---|---|"]
    for t in sorted(per_target):
        m = per_target[t]["metrics"]
        lines.append(
            f"| {t} | {per_target[t]['inventory']['relations']}"
            f" | {m['false_positive_facts']}"
            f" | {m['false_binding_count']}"
            f" | {m['false_subject_attribution_count']}"
            f" | {m['false_locator_declaration_count']} |")
    lines += ["", "corpus-73:",
              json.dumps(corpus_result["counts"], indent=2),
              "", "four-cases:",
              json.dumps(four_result["counts"], indent=2)]
    _wtext(out_dir / "report.md", "\n".join(lines) + "\n")
    return {"metrics": metrics, "corpus": corpus_result,
            "four_cases": four_result, "audit_rows": len(all_audit)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-manifest", required=True, type=Path)
    ap.add_argument("--targets", required=True, type=Path)
    ap.add_argument("--gold", type=Path,
                    default=G2 / "dev" / "declared_modifiers.json")
    ap.add_argument("--corpus", type=Path,
                    default=ROOT / "evidence" / "g1" / "dev"
                    / "g0-false-binding-corpus.json")
    ap.add_argument("--four-cases", type=Path,
                    default=G2 / "root-cause" / "g1-four-cases.json")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--run-id", default="g2")
    ap.add_argument("--only", default=None,
                    help="comma-separated boe_id allowlist (debug)")
    args = ap.parse_args()

    man = json.loads(args.dev_manifest.read_text(encoding="utf-8"))
    by_url = {e["url"]: e for e in man["entries"].values()}
    tj = json.loads(args.targets.read_text(encoding="utf-8"))
    targets = {b: t["cell"] for b, t in tj["targets"].items()}
    if args.only:
        keep = set(args.only.split(","))
        targets = {b: c for b, c in targets.items() if b in keep}
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    four = json.loads(args.four_cases.read_text(encoding="utf-8"))

    started = datetime.now(timezone.utc).isoformat()
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    src_tree = subprocess.run(["git", "rev-parse", "HEAD:src/regdelta"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()

    result = run_split(targets, by_url, gold, corpus, four,
                       args.run_id, args.output)
    finished = datetime.now(timezone.utc).isoformat()

    run = {
        "run_id": args.run_id,
        "runtime_head": head,
        "evaluation_head": head,
        "src_tree_sha256": src_tree,
        "evaluator": EVALUATOR_NAME,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_sha256": _sha256(Path(__file__).read_bytes()),
        "dev_manifest_sha256": _sha256(args.dev_manifest.read_bytes()),
        "targets_sha256": _sha256(args.targets.read_bytes()),
        "corpus_73_sha256": _sha256(args.corpus.read_bytes()),
        "four_cases_sha256": _sha256(args.four_cases.read_bytes()),
        "started_at": started, "finished_at": finished,
        "audit_rows": result["audit_rows"],
        "aggregate": result["metrics"],
    }
    _wtext(args.output / "run.json", json.dumps(
        run, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"run_dir": str(args.output),
                      "aggregate": result["metrics"],
                      "corpus_73": result["corpus"]["counts"],
                      "four_cases": result["four_cases"]["counts"],
                      "audit_rows": result["audit_rows"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
