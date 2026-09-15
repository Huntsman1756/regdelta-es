"""EXP-L1 — same-date lifecycle ordering falsification experiment.

Prereg: evidence/cov/PREREG.md §8. Verdict space:
PATTERN_CONFIRMED | REJECT. Never "adopt Indigo".

Candidate rule (indigo, algorithm only — no code, no AKN storage, no
editorial evidence model): order same-date lifecycle hops by

    (event date, amending work date, instrument subtype,
     natural-sorted instrument number)

and by document order inside a single amending work.

Method (frozen artifacts only; no runtime changes):
  1. Enumerate every (target, locator_key) in the frozen ledgers whose
     relations contain >=2 same-date hops — the order-sensitive groups
     — plus every (target, date) cluster with >=2 distinct modifiers.
  2. The frozen ledger orders same-date hops by relation_id hash
     (evaluate_g2.py sorts by (publication_date, relation_id)). The
     candidate rule orders them by the tuple above: modifiers first by
     official metadata (fecha_disposicion, rango, numero_oficial
     natural-sorted), intra-modifier hops by document position
     (node_index of the emitting clause).
  3. Replay each order-sensitive group under BOTH orders with G1 §28
     transitions (DELETE -> DELETED; bound after-representation ->
     PRESENT; any other write -> UNKNOWN) seeded by the pre-date chain
     state, and compare each simulated before-state to the adjudicated
     expected_existence_before.
  4. Classify per hop:
     - REPRODUCED          simulated state == adjudicated expectation
     - UNPROVEN_UNDER_ORDER  adjudicated chain proof (CHAIN_PREDECESSOR)
                           not reproduced under this order
     - FLOOR_CHANGED       adjudicated floor (ORIGINAL/ANCESTOR)
                           replaced by a different chain state
     - HARD_CONTRADICTION  simulated state provably opposite to an
                           adjudicated chain claim (PRESENT<->DELETED)

Verdict: REJECT if the tuple is non-deterministic on official metadata
(residual tie it cannot order) or if any HARD_CONTRADICTION arises
under the candidate order; else PATTERN_CONFIRMED. Flips of
hash-order-dependent adjudications are reported as findings — they
mark adjudicated expectations that only hold under an order with no
official basis, not falsifications of the candidate rule.

Usage:
    uv run python -X utf8 scripts/cov/exp_l1.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "g0g"))
sys.path.insert(0, str(ROOT / "scripts" / "g2"))
sys.path.insert(0, str(ROOT / "scripts" / "cov"))

import exp_b1  # noqa: E402  (frozen raw-index loader)
import evaluate_dev as ev  # noqa: E402
import evaluate_g2 as eg2  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402

OUT = ROOT / "evidence/cov/exp-l1"

CHAIN_METHODS = {"CHAIN_PREDECESSOR", "ANCESTOR_BORN_BY_CHAIN"}
# head kinds whose bare key identifies a unique instrument-level
# subject; everything else needs the clause's declared parent scope
GLOBAL_HEADS = {"norma", "anejo", "anexo", "disp", "disposicion",
                "estado", "fichero", "titulo", "capitulo", "seccion",
                "articulo"}


def _j(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(
        encoding="utf-8").splitlines() if l.strip()]


def _numkey(num: str) -> tuple:
    """Natural sort key for official numbers like '2/2020'."""
    return tuple(int(t) if t.isdigit() else t
                 for t in re.split(r"(\d+)", num))


def _meta(raw_idx: dict[str, Path], boe_id: str) -> dict:
    """Official ordering metadata from the captured diario XML."""
    p = raw_idx.get(boe_id)
    out = {"fecha_disposicion": "", "rango": "", "numero_oficial": ""}
    if p is None:
        return out
    t = p.read_bytes().decode("utf-8", errors="replace")
    for tag in out:
        m = re.search(rf"<{tag}[^>]*>\s*([^<]*)", t)
        if m:
            out[tag] = m.group(1).strip()
    return out


def _indigo_key(rel: dict, meta: dict, node: int | None) -> tuple:
    """Candidate ordering tuple: (event date, amending work date,
    subtype, natural number, document order)."""
    m = meta[rel["modifier_boe"]]
    return (rel["publication_date"],
            m["fecha_disposicion"],
            m["rango"],
            _numkey(m["numero_oficial"]),
            node if node is not None else 1 << 30)


def _frozen_key(rel: dict) -> tuple:
    return (rel["publication_date"], rel["relation_id"])


def _norma_vals(mentions: dict | None) -> list[str]:
    out = []
    for v in (mentions or {}).get("norma") or []:
        out.append(".".join(str(x) for x in v))
    return out


def _scope_norma(doc, sec: dict, cl: dict) -> list[str]:
    """Norma values declared by the clause itself, its accumulated
    scope context, or its nearest ancestor marker item. Empty list =
    scope not mechanically recoverable."""
    vals = set(_norma_vals(eg2._eval_mentions(cl["clause"])))
    vals.update(_norma_vals(eg2._eval_mentions(
        cl.get("prefix") or "")))
    vals.update(_norma_vals(cl.get("ctx") or {}))
    if vals:
        return sorted(vals)
    for i in range(cl["node_index"] - 1, sec["start"], -1):
        n = doc.nodes[i]
        if not n.text:
            continue
        if re.match(r"^\s*(?:\d+\.|[A-Za-zÁÉÍÓÚáéíóúñ]+\.)",
                    n.text):
            vals.update(_norma_vals(eg2._eval_mentions(n.text)))
            if vals:
                return sorted(vals)
    return []


def _transition(state: str, rel: dict, bound_after: set) -> str:
    if rel["operation_kind"] == "DELETE":
        return "DELETED"
    if rel["relation_id"] in bound_after:
        return "PRESENT"
    if rel["operation_kind"] in ("ADD", "SUBSTITUTE", "MODIFY"):
        return "UNKNOWN"
    return state


def _replay(hops: list[dict], order: list[dict], pre_state: str,
            bound_after: set) -> dict[str, str]:
    """Simulated before-state per relation_id under `order`."""
    st = pre_state
    out = {}
    for r in order:
        out[r["relation_id"]] = st
        st = _transition(st, r, bound_after)
    return out


_CONTAINER_RE = re.compile(
    r"[íi]ndice|cuadro|tabla|encabezamiento|r[úu]brica|"
    r"m[óo]dulo\s+\S+|dimensi[óo]n\b", re.IGNORECASE)


def _subscope(cl: dict) -> str:
    """Sub-element container markers in the operative text — a
    'suprime la dimensión X del módulo C.1' op keyed to 'anejo:2' is
    not the same subject as the whole-anejo key implies."""
    found = sorted({m.group(0).lower()
                    for m in _CONTAINER_RE.finditer(cl["clause"])})
    return "|".join(found)


def _classify(adj: dict, sim: str) -> str:
    exp = adj.get("expected_existence_before")
    method = adj.get("expected_method")
    if exp is None or exp in ("NOT_APPLICABLE",):
        return "NOT_APPLICABLE"
    if exp == sim:
        return "REPRODUCED"
    if method in CHAIN_METHODS:
        # chain-derived expectations are order-conditional claims
        if exp in ("PRESENT", "DELETED") \
                and sim in ("PRESENT", "DELETED"):
            return "HARD_CONTRADICTION"
        return "UNPROVEN_UNDER_ORDER"
    # floor methods (ORIGINAL/ANCESTOR-free) assert order-invariant
    # history — a different simulated chain state does not falsify
    # them, it only shows the proof route changed
    return "FLOOR_CHANGED"


def _test_group(split, t, key, d, same, hops, meta, rid2node,
                bound_after, life, scope_note, single_scope,
                scope_ids) -> dict:
    """Replay one same-subject same-date group under the frozen
    (relation_id hash) order and under the candidate order; classify
    each hop's simulated before-state against its adjudicated
    expectation. `scope_ids` = relation_ids of all hops sharing the
    group's scope signature (the pre-date chain may only include
    same-subject hops)."""
    prior = [r for r in hops if r["publication_date"] < d
             and r["relation_id"] in scope_ids]
    pre = "ABSENT"
    for r in sorted(prior, key=_frozen_key):
        pre = _transition(pre, r, bound_after)
    frozen = sorted(same, key=_frozen_key)
    indigo = sorted(same, key=lambda r: _indigo_key(
        r, meta, rid2node.get(r["relation_id"])))
    sim_f = _replay(hops, frozen, pre, bound_after)
    sim_i = _replay(hops, indigo, pre, bound_after)
    rows = []
    for r in same:
        rid = r["relation_id"]
        adj = life.get(rid, {})
        rows.append({
            "relation_id": rid,
            "modifier": r["modifier_boe"],
            "operation_kind": r["operation_kind"],
            "node_index": rid2node.get(rid),
            "adjudicated_exp": adj.get("expected_existence_before"),
            "adjudicated_method": adj.get("expected_method"),
            "frozen_sim": sim_f[rid],
            "indigo_sim": sim_i[rid],
            "frozen_class": _classify(adj, sim_f[rid]),
            "indigo_class": _classify(adj, sim_i[rid]),
        })
    return {
        "split": split, "target": t, "locator_key": key,
        "date": d, "pre_date_state": pre,
        "order_testable": True,
        "single_scope": single_scope,
        "scope": scope_note,
        "modifiers": sorted({r["modifier_boe"] for r in same}),
        "frozen_order": [r["relation_id"][:10] for r in frozen],
        "indigo_order": [r["relation_id"][:10] for r in indigo],
        "order_changed": [r["relation_id"] for r in frozen]
        != [r["relation_id"] for r in indigo],
        "hops": rows,
    }


def main() -> int:
    raw_idx = exp_b1._raw_index()
    splits = {
        "dev": ROOT / "evidence/g2/g2.2/dev-equivalence",
        "sealed": ROOT / "evidence/g2/g2.2/run",
    }

    groups: list[dict] = []
    clusters: list[dict] = []
    for split, run in splits.items():
        rels = _j(run / "relations.jsonl")
        life = {l["relation_id"]: l for l in _j(run / "lifecycle.jsonl")}
        subj = _j(run / "subject-outcomes.jsonl")
        binds = _j(run / "bindings.jsonl")
        bound_after = {b["relation_id"] for b in binds
                       if b["side"] == "after"
                       and b["verdict"] == "BINDING_CORRECT"}
        rid2node = {s["emitted_relation_id"]: s["node_index"]
                    for s in subj if s.get("emitted_relation_id")}

        by_key: dict[tuple, list] = defaultdict(list)
        for r in rels:
            by_key[(r["target"], r["locator_key"])].append(r)

        meta: dict[str, dict] = {}
        for r in rels:
            for bid in (r["modifier_boe"], r["target"]):
                if bid not in meta:
                    meta[bid] = _meta(raw_idx, bid)

        # inter-modifier same-date clusters (tuple determinism surface)
        by_td: dict[tuple, set] = defaultdict(set)
        for r in rels:
            by_td[(r["target"], r["publication_date"])].add(
                r["modifier_boe"])
        for (t, d), mods in sorted(by_td.items()):
            if len(mods) < 2:
                continue
            keys = [_indigo_key({"modifier_boe": m,
                                 "publication_date": d}, meta, None)
                    for m in mods]
            clusters.append({
                "split": split, "target": t, "date": d,
                "modifiers": sorted(mods),
                "tuples": {m: list(_indigo_key(
                    {"modifier_boe": m, "publication_date": d},
                    meta, None)[:4]) for m in sorted(mods)},
                "deterministic": len(set(keys)) == len(mods),
                "indigo_order": [m for _, m in sorted(
                    zip(keys, mods))],
            })

        # per-modifier docs + leaf index for scope resolution
        man = json.loads(
            (ROOT / "evidence/g2/dev/manifest.json").read_text(
                encoding="utf-8"))
        by_url = {e["url"]: e for e in man["entries"].values()}
        mod_docs: dict[str, object] = {}
        mod_lix: dict[str, dict] = {}
        for r in rels:
            mb = r["modifier_boe"]
            if mb in mod_docs:
                continue
            xml = ev.dev_xml(by_url, mb)
            if xml is None:
                p = raw_idx.get(mb)
                xml = p.read_bytes() if p else None
            if xml is not None:
                doc = boe_diario.parse_diario(xml).doc
                mod_docs[mb] = doc
                mod_lix[mb] = eg2._leaf_index(doc)

        def scope_of(r: dict) -> str:
            """Subject discriminator: head-scope + declared norma
            scope + sub-element container markers + anejo context.
            Ops on different real subjects collapse to one key only
            when this signature coincides."""
            cl = (mod_lix.get(r["modifier_boe"]) or {}).get(
                rid2node.get(r["relation_id"]))
            doc = mod_docs.get(r["modifier_boe"])
            if cl is None or doc is None:
                return "UNSCOPED"
            head_kind = r["locator_key"].split(":")[0].split(".")[0]
            base = "GLOBAL" if head_kind in GLOBAL_HEADS else None
            ns = _scope_norma(doc, cl["section"], cl)
            if base is None:
                if len(ns) == 1:
                    base = f"norma:{ns[0]}"
                elif len(ns) > 1:
                    base = "MULTI"
                else:
                    base = "UNSCOPED"
            anejos = sorted(set(
                [".".join(str(x) for x in v)
                 for v in (cl.get("ctx") or {}).get("anejo") or []]
                + [".".join(str(x) for x in v)
                   for v in (eg2._eval_mentions(cl["clause"])
                             .get("anejo") or [])]))
            sub = _subscope(cl)
            parts = [base]
            if anejos:
                parts.append("anejo_ctx=" + ",".join(anejos))
            if sub:
                parts.append("sub=" + sub)
            return "|".join(parts)

        # order-sensitive same-key same-date groups; scope computed
        # once per relation (bare keys collide across scopes)
        scope_cache: dict[str, str] = {}

        def scoped(r: dict) -> str:
            rid = r["relation_id"]
            if rid not in scope_cache:
                scope_cache[rid] = scope_of(r)
            return scope_cache[rid]

        for (t, key), hops in sorted(by_key.items()):
            by_date: dict[str, list] = defaultdict(list)
            for r in hops:
                by_date[r["publication_date"]].append(r)
            for d, same0 in sorted(by_date.items()):
                if len(same0) < 2:
                    continue
                # split by subject scope: a bare 'apartado:6' under
                # norma 34 and one under norma 66 are different
                # subjects sharing a key — not an ordering case
                by_scope: dict[str, list] = defaultdict(list)
                for r in same0:
                    by_scope[scoped(r)].append(r)
                scope_note = None
                if len(by_scope) > 1:
                    scope_note = {
                        "scopes": {s: len(v)
                                   for s, v in by_scope.items()}}
                # pre-date chain per scope: only same-scope hops
                scope_ids = {s: {r["relation_id"] for r in hops
                                 if scoped(r) == s}
                             for s in by_scope}
                tested = set()
                for s, same in by_scope.items():
                    if len(same) < 2 or s.startswith(
                            ("UNSCOPED", "MULTI")):
                        continue
                    groups.append(_test_group(
                        split, t, key, d, same, hops, meta,
                        rid2node, bound_after, life, scope_note,
                        len(by_scope) == 1, scope_ids[s]))
                    tested.update(r["relation_id"] for r in same)
                untested = [r for r in same0
                            if r["relation_id"] not in tested]
                if untested:
                    groups.append({
                        "split": split, "target": t,
                        "locator_key": key, "date": d,
                        "scope": scope_note,
                        "order_testable": False,
                        "hops": [{
                            "relation_id": r["relation_id"],
                            "modifier": r["modifier_boe"],
                            "operation_kind": r["operation_kind"],
                            "node_index": rid2node.get(
                                r["relation_id"]),
                            "scope": scoped(r)} for r in untested]})

    cls_frozen = defaultdict(int)
    cls_indigo = defaultdict(int)
    n_changed = 0
    n_untestable = 0
    hard = []
    for g in groups:
        if not g.get("order_testable"):
            n_untestable += 1
            continue
        if g["order_changed"]:
            n_changed += 1
        for h in g["hops"]:
            cls_frozen[h["frozen_class"]] += 1
            cls_indigo[h["indigo_class"]] += 1
            if h["indigo_class"] == "HARD_CONTRADICTION":
                hard.append({"group": {k: g[k] for k in
                                       ("split", "target",
                                        "locator_key", "date")},
                             "hop": h})
    nondet = [c for c in clusters if not c["deterministic"]]
    verdict = ("REJECT" if hard or nondet else "PATTERN_CONFIRMED")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "same-date-groups.json").write_text(json.dumps(
        {"experiment": "EXP-L1",
         "inter_modifier_clusters": clusters,
         "order_sensitive_groups": groups,
         "frozen_order_classes": dict(cls_frozen),
         "indigo_order_classes": dict(cls_indigo),
         "groups_where_order_differs": n_changed,
         "groups_untestable_scope": n_untestable,
         "non_deterministic_clusters": nondet,
         "hard_contradictions": hard,
         "verdict": verdict},
        indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(f"clusters={len(clusters)} "
          f"(non-deterministic={len(nondet)})")
    print(f"order-sensitive groups={len(groups)} "
          f"order_changed={n_changed} untestable={n_untestable}")
    print(f"frozen classes={dict(cls_frozen)}")
    print(f"indigo classes={dict(cls_indigo)}")
    print(f"hard_contradictions={len(hard)}")
    print(f"verdict={verdict}")
    for c in clusters:
        print("  cluster", c["split"], c["target"], c["date"],
              "->", c["indigo_order"])
    for g in groups:
        if g.get("order_testable") and g["order_changed"]:
            flips = [h for h in g["hops"]
                     if h["frozen_sim"] != h["indigo_sim"]
                     or h["frozen_class"] != h["indigo_class"]]
            if flips:
                print("  FLIP", g["split"], g["target"],
                      g["locator_key"], g["date"])
                for h in flips:
                    print("    ", h["relation_id"][:10],
                          h["modifier"], h["operation_kind"],
                          "node", h["node_index"],
                          "| adj:", h["adjudicated_exp"],
                          h["adjudicated_method"],
                          "| frozen:", h["frozen_sim"],
                          "-> indigo:", h["indigo_sim"],
                          "|", h["indigo_class"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
