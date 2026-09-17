"""PORT-CNMV-0R — semantic-isolation split remediation.

The v1 split was target-level; the unit of blindness must be the set
of documents ``reconstruct(T)`` will open semantically:

    DEP(T) = {T}
        UNION posterior referencias (MODIFICATION + CORRECTION)
        — every declared modifier/corrigendum document, each of which
          the pipeline opens as diario XML + doc HTML + PDF + annex
          images (history._target_annex_map applies to modifiers too)

Derived ONLY from <metadatos>/<analisis>/<referencias> in the frozen
corpus frame — never from <texto>.

Conflict graph: T1 ~ T2 iff DEP(T1) ∩ DEP(T2) ≠ ∅. Connected
components are split whole: odd component rank -> DEV_POOL, even ->
HOLDOUT_POOL; top-4 targets per pool by original frozen stress rank.
Components whose DEP touches the semantic seen-set are excluded from
the blind pool.

Usage:
    PYTHONPATH=src python scripts/port-cnmv/split_isolation.py \
        --output evidence/port-cnmv/split-v2 \
        --frame evidence/port-cnmv/corpus-frame.json \
        --selection evidence/port-cnmv/selection.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import scout_cnmv as scout  # noqa: E402

COMPONENT_SEED = "regdelta-port-cnmv-component-v1"
IMG_RE = re.compile(r'src="([^"]+\.(?:png|jpg|gif))"', re.IGNORECASE)
REQUIRED_ARTS = ("xml", "html", "pdf")


def _load_json(path: Path):
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(raw.decode("cp1252"))


def dependency_plan(target: str, by_id: dict) -> set[str]:
    """DEP(target): documents reconstruct(target) may open
    semantically — metadata-derived only."""
    e = by_id[target]
    deps = {target}
    for r in e.get("modification_refs", []) + e.get("correction_refs", []):
        ref = r["referencia"]
        if scout.BOE_ID_RE.fullmatch(ref):
            deps.add(ref)
    return deps


def _components(nodes: list[str], deps: dict[str, set[str]]) -> list[set[str]]:
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if deps[a] & deps[b]:
                union(a, b)
    comps: dict[str, set[str]] = {}
    for n in nodes:
        comps.setdefault(find(n), set()).add(n)
    return list(comps.values())


def _img_urls(html: bytes) -> list[str]:
    urls = []
    for src in IMG_RE.findall(html.decode("utf-8", "replace")):
        u = scout._join(scout.BOE_BASE + "/", src)
        if u not in urls:
            urls.append(u)
    return urls


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--frame", type=Path, required=True)
    ap.add_argument("--selection", type=Path, required=True)
    args = ap.parse_args()
    out_dir: Path = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = _load_json(args.frame)
    sel = _load_json(args.selection)
    by_id = {e["boe_id"]: e for e in frame}
    elig = [e["boe_id"] for e in frame if e.get("eligible")]

    seen = set(scout.SEMANTIC_SEEN)
    seen |= {e["boe_id"] for e in frame if e.get("semantically_seen")}
    prior_seen_path = ROOT / "evidence" / "cov" / "semantic-seen-set.json"
    if prior_seen_path.exists():
        seen |= set(_load_json(prior_seen_path)["boe_ids"])

    # --- DEP sets -----------------------------------------------------
    deps = {t: dependency_plan(t, by_id) for t in elig}

    # --- frozen target stress rank (recomputed; must equal v1) --------
    def rank_key(boe: str):
        e = by_id[boe]
        tie = hashlib.sha256(
            (scout.SPLIT_SEED + "|" + boe).encode()).hexdigest()
        return (-e["declared_modifier_count"],
                -e["multi_target_modifier_event_count"],
                -e["corrigendum_count"], tie)

    ranked = sorted([b for b in elig if by_id[b].get("unseen")],
                    key=rank_key)
    assert ranked == sel["stress_rank"], \
        "recomputed stress rank != frozen selection.json rank"
    rank_pos = {b: i for i, b in enumerate(ranked)}

    # --- conflict components ------------------------------------------
    comps = _components(elig, deps)
    comp_rows = []
    blind = []
    for comp in comps:
        comp_deps = set().union(*(deps[m] for m in comp))
        touched = sorted(comp_deps & seen)
        row = {"targets": sorted(comp),
               "dep_union_size": len(comp_deps),
               "excluded": bool(touched),
               "seen_touch": touched,
               "best_member_rank": min(rank_pos[m] for m in comp)}
        comp_rows.append(row)
        if not touched:
            blind.append(comp)

    def comp_key(comp: set[str]):
        tie = hashlib.sha256(
            (COMPONENT_SEED + "|" + "|".join(sorted(comp)))
            .encode()).hexdigest()
        return (min(rank_pos[m] for m in comp), tie)

    comps_ranked = sorted(blind, key=comp_key)
    dev_pool, hold_pool = [], []
    for i, comp in enumerate(comps_ranked, start=1):
        (dev_pool if i % 2 == 1 else hold_pool).extend(comp)
    dev_pool.sort(key=rank_pos.__getitem__)
    hold_pool.sort(key=rank_pos.__getitem__)
    dev_targets = dev_pool[:4]
    hold_targets = hold_pool[:4]

    # --- hard gates ----------------------------------------------------
    dev_dep = set().union(*(deps[t] for t in dev_targets)) \
        if dev_targets else set()
    hold_dep = set().union(*(deps[t] for t in hold_targets)) \
        if hold_targets else set()
    gates = {
        "dev_targets_eq_4": len(dev_targets) == 4,
        "holdout_targets_eq_4": len(hold_targets) == 4,
        "dev_holdout_dep_disjoint": not (dev_dep & hold_dep),
        "holdout_dep_seen_disjoint": not (hold_dep & seen),
    }
    if not all(gates.values()):
        for name, obj in (
            ("dependency-sets.json", {t: sorted(deps[t]) for t in elig}),
            ("conflict-components.json", comp_rows),
            ("selection.json", {"terminal":
                                "INSUFFICIENT_ISOLATED_CORPUS",
                                "gates": gates,
                                "dev_pool": dev_pool,
                                "holdout_pool": hold_pool}),
        ):
            (out_dir / name).write_text(
                json.dumps(obj, indent=1, ensure_ascii=False))
        print("INSUFFICIENT_ISOLATED_CORPUS", gates)
        return 2

    # --- capture --------------------------------------------------------
    # Every DEP member gets the full artifact trio reconstruct may
    # open (XML + doc HTML + PDF) plus annex images found in the doc
    # HTML. v1 bytes are reused when already captured (sha recorded).
    v1_raw = [out_dir / "dev" / "raw", out_dir / scout.SEALED_SIDE / "raw",
              ROOT / "evidence" / "port-cnmv" / "dev" / "raw",
              ROOT / "evidence" / "port-cnmv" / scout.SEALED_SIDE / "raw"]

    def get_artifact(name: str, url: str, accept: str,
                     raw_dir: Path, entries: dict, cached=None):
        if name in entries and "sha256" in entries[name]:
            return entries[name].get("_bytes")
        body = cached
        if body is None:
            for vd in v1_raw:
                p = vd / name
                if p.exists():
                    body = p.read_bytes()
                    break
        if body is None:
            body = scout._fetch(url)
        if body is None:
            entries[name] = {"name": name, "url": url, "accept": accept,
                             "retrieved_at": scout._now(),
                             "error_class": "FETCH_ERROR"}
            return None
        rel = raw_dir.resolve().relative_to(ROOT) / name
        (raw_dir / name).write_bytes(body)
        entries[name] = {
            "name": name, "url": url, "accept": accept,
            "retrieved_at": scout._now(),
            "path": str(rel).replace("\\", "/"),
            "sha256": scout._sha(body), "size_bytes": len(body),
            "http_status": 200,
        }
        return body

    def capture_side(targets: list[str], side: str):
        raw_dir = out_dir / side / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        entries: dict = {}
        side_dep = set().union(*(deps[t] for t in targets))
        captured_docs: dict[str, set[str]] = {t: set() for t in targets}
        for boe in sorted(side_dep):
            xml = get_artifact("boe_diario_xml__" + boe + ".xml",
                               scout.XML_URL.format(boe=boe),
                               "application/xml", raw_dir, entries)
            html = get_artifact("boe_doc_html__" + boe + ".html",
                                scout.DOC_URL.format(boe=boe),
                                "text/html", raw_dir, entries)
            url_pdf = by_id.get(boe, {}).get("url_pdf")
            if url_pdf is None and xml is not None:
                info = scout.inspect_metadata(xml)
                url_pdf = (info or {}).get("metadata", {}).get("url_pdf")
            if url_pdf:
                get_artifact("boe_dias_pdf__" + boe + ".pdf",
                             url_pdf, "application/pdf", raw_dir, entries)
            if html is not None:
                for img in _img_urls(html):
                    iname = "boe_imagen__" + boe + "__" + \
                        img.rsplit("/", 1)[-1]
                    get_artifact(iname, img, "image/*", raw_dir, entries)
            for t in targets:
                if boe in deps[t]:
                    captured_docs[t].add(boe)
        mpath = out_dir / side / "manifest.json"
        mpath.write_text(json.dumps(
            {"captured_at": scout._now(), "entries": entries},
            indent=1, ensure_ascii=False))
        return entries, captured_docs, mpath

    dev_entries, dev_docs, _ = capture_side(dev_targets, "dev")
    hold_entries, hold_docs, hm_path = \
        capture_side(hold_targets, scout.SEALED_SIDE)

    # --- reconstruct_dependency_plan check -----------------------------
    plan_ok = True
    for targets, captured, entries in (
            (dev_targets, dev_docs, dev_entries),
            (hold_targets, hold_docs, hold_entries)):
        for t in targets:
            if captured[t] != deps[t]:
                plan_ok = False
                continue
            for doc in deps[t]:
                for ext in REQUIRED_ARTS:
                    name = {  # noqa: E501
                        "xml": "boe_diario_xml__" + doc + ".xml",
                        "html": "boe_doc_html__" + doc + ".html",
                        "pdf": "boe_dias_pdf__" + doc + ".pdf"}[ext]
                    e = entries.get(name)
                    if e is None or "sha256" not in e:
                        plan_ok = False
    gates["dependency_plan_eq_captured"] = plan_ok
    if not plan_ok:
        (out_dir / "selection.json").write_text(json.dumps(
            {"terminal": "ACQUISITION_BLOCKED", "gates": gates},
            indent=1, ensure_ascii=False))
        print("ACQUISITION_BLOCKED: captured set != dependency plan")
        return 3

    # --- seal holdout v2 -------------------------------------------------
    hm = json.loads(hm_path.read_text(encoding="utf-8"))
    total_bytes = sum(e.get("size_bytes", 0) for e in hm["entries"].values())
    agg = hashlib.sha256()
    for name in sorted(hm["entries"]):
        e = hm["entries"][name]
        if "sha256" in e:
            agg.update(bytes.fromhex(e["sha256"]))
    seal = {
        "gate": "PORT-CNMV-0R",
        "targets": hold_targets,
        "manifest_sha256": scout._sha(hm_path.read_bytes()),
        "artifact_count": len(hm["entries"]),
        "aggregate_bytes": total_bytes,
        "aggregate_sha256": agg.hexdigest(),
        "capture_script_sha256": scout._sha(Path(__file__).read_bytes()),
        "rule": "no source/test/eval code may read these artifacts "
                "semantically until PORT-CNMV-2 (sealed-runner "
                "protocol); DEP-isolated from DEV",
        "sealed_at_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True,
            text=True, cwd=ROOT).stdout.strip(),
    }
    (out_dir / scout.SEALED_SIDE / "SEAL").write_text(
        json.dumps(seal, indent=1, ensure_ascii=False))

    # --- outputs ---------------------------------------------------------
    selection = {
        "terminal": "READY_FOR_ISOLATED_CNMV_PROFILE_PROBE",
        "split_rule": "component-level: conflict components ranked by "
                      "(best member stress rank, sha256(component "
                      "seed)); odd -> DEV_POOL, even -> HOLDOUT_POOL; "
                      "top-4 per pool by original stress rank",
        "component_rank": ["|".join(sorted(c)) for c in comps_ranked],
        "dev_pool": dev_pool,
        "holdout_pool": hold_pool,
        "dev": dev_targets,
        "sealed_holdout": hold_targets,
        "gates": gates,
        "supersedes": "evidence/port-cnmv/selection.json "
                      "(split-v1 SUPERSEDED_PREOPEN)",
    }
    (out_dir / "dependency-sets.json").write_text(json.dumps(
        {t: sorted(deps[t]) for t in elig}, indent=1,
        ensure_ascii=False))
    (out_dir / "conflict-components.json").write_text(
        json.dumps(comp_rows, indent=1, ensure_ascii=False))
    (out_dir / "selection.json").write_text(
        json.dumps(selection, indent=1, ensure_ascii=False))

    n_err = sum(1 for e in list(dev_entries.values()) +
                list(hold_entries.values()) if "error_class" in e)
    print("READY_FOR_ISOLATED_CNMV_PROFILE_PROBE")
    print(f"components: {len(comps)} total, {len(comps_ranked)} blind, "
          f"{sum(1 for r in comp_rows if r['excluded'])} excluded")
    print(f"dev: {dev_targets}")
    print(f"holdout: {hold_targets}")
    print(f"artifacts dev={len(dev_entries)} holdout="
          f"{len(hold_entries)} errors={n_err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
