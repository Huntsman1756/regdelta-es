"""EXP-B1 — redesignation-aware pairing falsification experiment.

Prereg: evidence/cov/PREREG.md §8. Verdict space: PORT | REJECT.

Candidate mechanism (words-to-data @ ccc44e0, algorithm only): consult
demonstrated redesignation edges BEFORE positional/same-key pairing —
a clause declaring 'X pasa a ser/denominarse Y' is a continuity edge
old_key -> new_key; the subject's chain state migrates with it.

Method (frozen artifacts only; no runtime changes):
  1. Enumerate 'pasa a ser/denominarse' clauses in DEV modifier
     documents (evaluator-side clause enumeration, shared lexical
     primitives — same contract as the G2 audit).
  2. Classify each clause: CODE_REDESIGNATION (key-changing edge) /
     RELABEL (same code, new rubric) / SUBFIELD_RENAME (below locator
     granularity) / NON_STRUCTURAL / UNPARSEABLE.
  3. For each CODE_REDESIGNATION edge that is actionable in the
     adjudicated ledger (O1 TARGET_PROVEN + O2 ledger row exists),
     replay the target's frozen relation stream and migrate chain
     state old_key -> new_key at the event date.
  4. Compare against the adjudicated lifecycle/binding ledger:
     - FALSE_MERGE: new_key had proven prior existence as a distinct
       subject (original-publication structural or proven prior hop)
       AND old_key existed too — merging is a false continuity.
     - CONTRADICTED: migrated state contradicts an adjudicated
       expected_existence_before on post-event new_key ops.
     - LOST: an adjudicated CHAIN_PROVEN hop is broken by migration.
     - REPAIRED: migrated state proves continuity the frozen ledger
       left UNKNOWN/discontinued, consistent with all adjudication.
     - CONFIRMED: continuity already proven; edge is redundant.
     - NO_LEDGER_INTERACTION: nothing adjudicated touches the edge.

Verdict: REJECT if any FALSE_MERGE / CONTRADICTED / LOST element;
else PORT (repair yield reported, not required).

Usage:
    uv run python -X utf8 scripts/cov/exp_b1.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "g0g"))
sys.path.insert(0, str(ROOT / "scripts" / "g1"))
sys.path.insert(0, str(ROOT / "scripts" / "g2"))

import evaluate_dev as ev  # noqa: E402
import evaluate_g2 as eg2  # noqa: E402
from regdelta import operations  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402

RUN = ROOT / "evidence/g2/g2.2/dev-equivalence"
OUT = ROOT / "evidence/cov/exp-b1"

REDES_RE = re.compile(r"pasa\w*\s+a\s+(ser|denominarse)", re.IGNORECASE)
QUOTED_RE = re.compile(r"«([^»]*)»")
ESTADO_CODE_RE = re.compile(
    r"\b([A-Z]{1,4}\s*\d[\d\-]*(?:\.\d+)?)\b")
SUBFIELD_RE = re.compile(
    r"(?:la|el|las|los)\s+(columna|dimensi[oó]n|partida|campo|"
    r"casilla|r[úu]brica|descripci[oó]n|denominaci[oó]n|"
    r"ep[íi]grafe|celda|fila)\b", re.IGNORECASE)
NOTA_RE = re.compile(r"nota\s*\(?([a-z0-9]+)\)?", re.IGNORECASE)
# boundary where the redesignation's new-side ends and the next
# coordinated operation begins ("... nota (4) y se añaden las notas
# (2) y (3)" — only "la nota (4)" belongs to the redesignation)
_NEXT_OP_RE = re.compile(
    r";\s*|\.\s+|,?\s*(?:y|e)\s+se\s+(?:añad|suprim|elimin|modific|"
    r"sustituy|introduc|inclu|crea|inserta|realiza|sombrea)|"
    r",?\s*se\s+(?:añad|suprim|elimin|modific|sustituy|introduc|"
    r"inclu|crea|inserta)", re.IGNORECASE)


def _j(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in
            p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _target_ref(xml: bytes | None) -> tuple[int, int] | None:
    if xml is None:
        return None
    m = re.search(r"<numero_oficial>\s*(\d+)\s*/\s*(\d{4})",
                  xml.decode("utf-8", errors="replace"))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _new_side_code(kind: str, new_side: str) -> str | None:
    """Extract the redesignated code of `kind` from the post-verb
    text, or None when not mechanically extractable."""
    if kind == "fichero":
        q = QUOTED_RE.search(new_side)
        return _norm_text(q.group(1)) if q else None
    if kind == "estado":
        q = QUOTED_RE.search(new_side)
        src = q.group(1) if q else new_side
        m = ESTADO_CODE_RE.search(src)
        return operations._norm_state_code(
            *re.match(r"\s*([A-Za-z]+)\s*(.*)", m.group(1)).groups()
        ) if m else None
    mentions = eg2._eval_mentions(new_side)
    vals = mentions.get(kind)
    if vals and len(vals) == 1:
        v = vals[0]
        return str(v[0]) if isinstance(v, tuple) else str(v)
    return None


def _old_key_kind(clause_text: str, ctx: dict) -> str | None:
    """Kind of the redesignated subject: own mentions first, then the
    innermost scope mention of a sub-locator kind."""
    own = eg2._eval_mentions(clause_text)
    for k in ("estado", "fichero", "norma", "anejo", "disp",
              "apartado", "punto", "letra", "nota", "numeral"):
        if own.get(k):
            return k
    for k in ("nota", "letra", "punto", "apartado", "numeral"):
        if ctx.get(k):
            return k
    return None


def _replace_leaf(old_key: str, kind: str, new_val: str) -> str | None:
    """Substitute the leaf segment of old_key with kind:new_val."""
    parts = old_key.split(".")
    if not parts:
        return None
    head = parts[0]
    if head.split(":", 1)[0] == kind or \
            (kind in ("punto", "apartado") and
             head.split(":", 1)[0] in ("punto", "apartado")):
        parts[0] = f"{kind}:{new_val}"
        return ".".join(parts)
    if ":" not in parts[-1]:
        return None
    parts[-1] = f"{kind}:{new_val}"
    return ".".join(parts)


def classify_clause(clause: dict) -> dict:
    """Mechanical redesignation classification. Returns a case row."""
    text = clause["clause"]
    m = REDES_RE.search(text)
    old_side, new_side = text[:m.start()], text[m.end():]
    row = {"node_index": clause["node_index"],
           "marker": clause.get("marker") or "",
           "clause_sha256": ev._sha256(text.encode("utf-8")),
           "verb": m.group(0)}

    if SUBFIELD_RE.search(old_side):
        row["class"] = "SUBFIELD_RENAME"
        return row

    kind = _old_key_kind(text, clause.get("ctx") or {})
    if kind is None:
        row["class"] = "NON_STRUCTURAL"
        return row
    row["subject_kind"] = kind

    new_side = _NEXT_OP_RE.split(new_side, 1)[0]
    new_code = _new_side_code(kind, new_side)
    row["new_code"] = new_code
    if kind == "fichero":
        # fichero identity IS its rubric: a rename moves the key
        old_q = QUOTED_RE.search(old_side)
        row["old_code"] = _norm_text(old_q.group(1)) if old_q else None
        row["class"] = ("CODE_REDESIGNATION" if new_code
                        else "UNPARSEABLE")
        return row

    old_mentions = eg2._eval_mentions(old_side)
    old_vals = old_mentions.get(kind) or \
        (clause.get("ctx") or {}).get(kind) or []
    if len(old_vals) != 1:
        row["class"] = "UNPARSEABLE"
        return row
    v0 = old_vals[0]
    old_code = str(v0[0]) if isinstance(v0, tuple) else str(v0)
    if kind == "estado":
        old_code = operations._norm_state_code(
            *re.match(r"\s*([A-Za-z]+)\s*(.*)", old_code).groups())
    row["old_code"] = old_code
    if new_code is None:
        row["class"] = "UNPARSEABLE"
        return row
    if eg2._norm_val(new_code) == eg2._norm_val(old_code):
        row["class"] = "RELABEL_SAME_CODE"
    else:
        row["class"] = "CODE_REDESIGNATION"
    return row


def chain_states(rels: list[dict], bound_after: set[str],
                 up_to_date: str | None = None) -> dict:
    """Replay the frozen relation stream under G1 §28 chain semantics.
    Returns {locator_key: (state, relation_id)}."""
    chain: dict[str, tuple] = {}
    for r in sorted(rels, key=lambda r: (r["publication_date"],)):
        if up_to_date and r["publication_date"] >= up_to_date:
            continue
        key = r["locator_key"]
        rid = r["relation_id"]
        if r["operation_kind"] == "DELETE":
            chain[key] = ("DELETED", rid)
        elif rid in bound_after:
            chain[key] = ("PRESENT", rid)
        elif r["operation_kind"] in ("SUBSTITUTE", "MODIFY", "ADD"):
            chain[key] = ("UNKNOWN", rid)
    return chain


def _raw_index() -> dict[str, Path]:
    """boe_id -> captured diario XML (any frozen raw/ dir)."""
    out = {}
    for p in (ROOT / "evidence").rglob("boe_diario_xml__*.xml"):
        out[p.stem.split("__", 1)[1]] = p
    return out


def _load_run(run_dir: Path, fail_dir: Path, by_url: dict,
              raw_idx: dict[str, Path]):
    def xml_for(boe_id: str) -> bytes | None:
        x = ev.dev_xml(by_url, boe_id)
        if x is not None:
            return x
        p = raw_idx.get(boe_id)
        return p.read_bytes() if p else None
    return {
        "recon": _j(run_dir / "reconciliation.jsonl"),
        "rels": _j(run_dir / "relations.jsonl"),
        "subj": _j(run_dir / "subject-outcomes.jsonl"),
        "life": _j(run_dir / "lifecycle.jsonl"),
        "binds": _j(run_dir / "bindings.jsonl"),
        "fails": _j(fail_dir / "failures.jsonl"),
        "xml_for": xml_for,
    }


def main() -> int:
    man = json.loads(
        (ROOT / "evidence/g2/dev/manifest.json").read_text(
            encoding="utf-8"))
    by_url = {e["url"]: e for e in man["entries"].values()}
    raw_idx = _raw_index()
    splits = {
        "dev": _load_run(RUN, RUN, by_url, raw_idx),
        "sealed": _load_run(ROOT / "evidence/g2/g2.2/run",
                            ROOT / "evidence/g2/g2.2",
                            by_url, raw_idx),
    }
    all_cases: list[dict] = []
    all_edges: list[dict] = []
    for split_name, S in splits.items():
        cases, edges = run_split(split_name, S)
        all_cases += cases
        all_edges += edges

    counts = Counter(c["class"] for c in all_cases)
    by_split_class = {s: dict(Counter(c["class"] for c in all_cases
                                    if c["split"] == s))
                      for s in splits}
    outcomes = Counter(e["outcome"] for e in all_edges)
    by_split_out = {s: dict(Counter(e["outcome"] for e in all_edges
                                    if e["split"] == s))
                    for s in splits}
    fail = (outcomes.get("FALSE_MERGE_RISK", 0)
            + outcomes.get("CONTRADICTED", 0)
            + outcomes.get("LOST", 0))
    verdict = "REJECT" if fail else "PORT"

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cases.json").write_text(json.dumps(
        {"experiment": "EXP-B1",
         "case_count": len(all_cases),
         "class_counts": dict(counts),
         "class_counts_by_split": by_split_class,
         "cases": all_cases},
        indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (OUT / "simulation.json").write_text(json.dumps(
        {"edges": all_edges, "outcome_counts": dict(outcomes),
         "outcome_counts_by_split": by_split_out,
         "verdict": verdict},
        indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(f"cases={len(all_cases)} classes={dict(counts)}")
    print(f"edges={len(all_edges)} outcomes={dict(outcomes)}")
    print(f"by_split_out={by_split_out}")
    print(f"verdict={verdict}")
    for e in all_edges:
        print(" ", e["split"], e["target"], e["modifier"],
              e["old_key"], "->", e["new_key"], "|", e["outcome"])
    return 0


def run_split(split_name: str, S: dict):
    recon = S["recon"]
    rels = S["rels"]
    subj = S["subj"]
    life = S["life"]
    binds = S["binds"]
    fails = S["fails"]
    xml_for = S["xml_for"]

    pairs = sorted({(r["target"], r["modifier"]) for r in recon})
    subj_by_op: dict[tuple, list] = defaultdict(list)
    for s in subj:
        subj_by_op[(s["target"], s["modifier"],
                    s["node_index"])].append(s)
    rels_by_tk: dict[tuple, list] = defaultdict(list)
    for r in rels:
        rels_by_tk[(r["target"], r["locator_key"])].append(r)
    bound_after = {b["relation_id"] for b in binds
                   if b["side"] == "after"
                   and b["verdict"] == "BINDING_CORRECT"}
    life_by_rid = {l["relation_id"]: l for l in life}
    disc = [f for f in fails
            if "CHAIN_DISCONTINUITY" in f.get("symptom", "")]

    tdocs: dict[str, object] = {}
    trefs: dict[str, tuple | None] = {}
    pub_by_mod: dict[str, str] = {}

    cases: list[dict] = []
    for target, mod in pairs:
        xml = xml_for(mod)
        if xml is None:
            continue
        mdoc = boe_diario.parse_diario(xml).doc
        if target not in trefs:
            txml = xml_for(target)
            trefs[target] = _target_ref(txml)
            tdocs[target] = (boe_diario.parse_diario(txml).doc
                             if txml else None)
        mm = re.search(r"<fecha_publicacion>(\d{8})",
                       xml.decode("utf-8", errors="replace"))
        pub_by_mod[mod] = (f"{mm.group(1)[:4]}-{mm.group(1)[4:6]}-"
                           f"{mm.group(1)[6:]}" if mm else "")
        for sec in eg2._sections(mdoc):
            for cl in eg2._leaf_clauses(mdoc, sec):
                if not REDES_RE.search(cl["clause"]):
                    continue
                row = classify_clause(cl)
                row["split"] = split_name
                row["target"] = target
                row["modifier"] = mod
                row["publication_date"] = pub_by_mod[mod]
                row["section_targets"] = [f"{a}/{b}"
                                          for a, b in sec["targets"]]
                att = eg2.attribute_operation(
                    trefs[target], target, mdoc, cl, sec)
                row["o1_status"] = att["status"]
                row["o1_method"] = att["method"]
                ledger = subj_by_op.get((target, mod,
                                         cl["node_index"]), [])
                row["ledger_locators"] = sorted(
                    {s["candidate_locator"] for s in ledger
                     if s["candidate_locator"]})
                row["emitted_relation_ids"] = sorted(
                    {s["emitted_relation_id"] for s in ledger
                     if s["emitted_relation_id"]})
                cases.append(row)

    # ---- build actionable edges ------------------------------------
    # The ledger may record several candidate locators per clause; the
    # redesignation edge uses the one whose leaf kind matches the
    # redesignated subject kind. If none or several remain -> the case
    # is recorded but not simulated (fail-closed, never guessed).
    edges: list[dict] = []
    for c in cases:
        if c["class"] != "CODE_REDESIGNATION":
            continue
        locs = c["ledger_locators"]
        kind = c["subject_kind"]
        kinded = [l for l in locs
                  if l.split(".")[-1].split(":")[0] == kind
                  or l.split(":")[0] == kind]
        if len(kinded) != 1 and locs:
            # rename clauses legitimately mention the destination code;
            # pick the kind-matching locator whose leaf is the OLD code
            oldleaf = [l for l in locs
                       if l.rsplit(":", 1)[-1] == c["old_code"]]
            if len(oldleaf) == 1:
                locs = oldleaf
            else:
                locs = kinded
        else:
            locs = kinded
        if len(locs) != 1:
            c["edge_status"] = "UNPARSEABLE_LOCATOR"
            continue
        old_key = locs[0]
        new_key = _replace_leaf(old_key, c["subject_kind"],
                                c["new_code"])
        if new_key is None or new_key == old_key:
            c["edge_status"] = "UNPARSEABLE_LOCATOR"
            continue
        c["old_key"] = old_key
        c["new_key"] = new_key
        c["edge_status"] = ("ACTIONABLE"
                            if c["o1_status"] == "TARGET_PROVEN"
                            else "NOT_ACTIONABLE_O1_" + c["o1_status"])
        edges.append(c)

    # ---- simulate redesignation-first pairing ----------------------
    results: list[dict] = []
    for e in edges:
        t, d = e["target"], e["publication_date"]
        ok, nk = e["old_key"], e["new_key"]
        tdoc = tdocs.get(t)
        all_rels = rels  # per-target filtered below
        trels = [r for r in all_rels if r["target"] == t]
        st_before = chain_states(trels, bound_after, up_to_date=d)
        old_prior = st_before.get(ok, ("ABSENT", None))[0]
        new_prior = st_before.get(nk, ("ABSENT", None))[0]
        old_orig = bool(tdoc and ev.locator_resolves(tdoc, ok))
        new_orig = bool(tdoc and ev.locator_resolves(tdoc, nk))
        old_exists = old_prior in ("PRESENT", "UNKNOWN") or old_orig
        new_exists = new_prior in ("PRESENT", "UNKNOWN") or new_orig

        post = [r for r in rels_by_tk.get((t, nk), [])
                if r["publication_date"] > d]
        post_old = [r for r in rels_by_tk.get((t, ok), [])
                    if r["publication_date"] > d]
        # same-date ops on either key = the rename event's own ledger
        # rows (a rename is adjudicated as MODIFY old + MODIFY new —
        # the edge must convert that UNKNOWN pair into proven
        # continuity, never leave it dangling)
        event_ids = set(e["emitted_relation_ids"])
        same = [r for r in rels_by_tk.get((t, nk), [])
                + rels_by_tk.get((t, ok), [])
                if r["publication_date"] == d]
        ddisc = [f for f in disc
                 if f.get("target") == t and (nk in f["symptom"]
                                            or ok in f["symptom"])]

        if e["edge_status"] != "ACTIONABLE":
            outcome = "NOT_ACTIONABLE"
        elif new_exists and old_exists:
            outcome = "FALSE_MERGE_RISK"   # rule must abstain here
        else:
            migrated = st_before.get(ok, ("ABSENT", None))[0]
            if migrated == "ABSENT" and old_orig:
                migrated = "PRESENT"
            contradicted = repaired = confirmed = 0
            lost = 0
            # event's own same-date relations. The declared edge
            # presupposes the OLD subject existed and asserts it
            # continued under the NEW key:
            #   old_key PRESENT -> consistent (rename presupposition,
            #     adjudication agrees) -> CONFIRMED
            #   old_key UNKNOWN -> the declaration itself is the
            #     before-evidence the ledger lacked -> REPAIRED
            #   new_key UNKNOWN -> edge supplies proven continuity for
            #     the dangling new-designation op -> REPAIRED
            #   new_key PRESENT -> adjudication proved the new key
            #     already existed as a distinct subject -> declared
            #     merge contradicts the ledger -> CONTRADICTED
            for r in same:
                exp = (life_by_rid.get(r["relation_id"]) or {}
                       ).get("expected_existence_before")
                if r["locator_key"] == ok:
                    if exp == "UNKNOWN":
                        repaired += 1
                    elif exp in ("PRESENT", "DELETED", "NOT_APPLICABLE"):
                        confirmed += 1
                elif r["locator_key"] == nk:
                    if exp == "UNKNOWN":
                        repaired += 1
                    elif exp == "PRESENT":
                        contradicted += 1
            for r in post:
                exp = (life_by_rid.get(r["relation_id"]) or {}
                       ).get("expected_existence_before")
                if exp is None:
                    continue
                if migrated == exp:
                    confirmed += 1
                elif exp == "UNKNOWN" and migrated in (
                        "PRESENT", "DELETED"):
                    repaired += 1
                elif exp in ("PRESENT", "DELETED", "ABSENT") \
                        and migrated != exp:
                    contradicted += 1
            # post-event ops still referencing the old key: migration
            # moves state off it — check the adjudicated expectation
            # does not rely on old_key continuity (lost continuity)
            for r in post_old:
                exp = (life_by_rid.get(r["relation_id"]) or {}
                       ).get("expected_existence_before")
                if exp == "PRESENT" and migrated == "PRESENT":
                    lost += 1   # adjudication expected the old
                                # subject to persist; the edge moved it
            if contradicted:
                outcome = "CONTRADICTED"
            elif lost:
                outcome = "LOST"
            elif repaired:
                outcome = "REPAIRED"
            elif confirmed:
                outcome = "CONFIRMED"
            else:
                outcome = "NO_LEDGER_INTERACTION"
        e["simulation"] = {
            "old_key_prior": old_prior, "new_key_prior": new_prior,
            "old_in_original": old_orig, "new_in_original": new_orig,
            "same_date_ops_on_edge_keys": len(same),
            "post_event_ops_on_new_key": len(post),
            "post_event_ops_on_old_key": len(post_old),
            "discontinuities_on_edge_keys": len(ddisc)}
        e["outcome"] = outcome
        results.append(e)
    return cases, results


if __name__ == "__main__":
    raise SystemExit(main())
