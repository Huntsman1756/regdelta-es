"""COV-0 — coverage debt cross-tabulation baseline.

Pure statistics over the frozen G2.2 artifacts (sealed run +
dev-equivalence run). No runtime code, no evaluation, no verdicts:
this baseline decides *which* oss-recon problem owns how much debt
before any coverage gate is preregistered.

Usage:
    python scripts/cov/cov0.py

Reads:
    evidence/g2/g2.2/run/                (sealed run, 4 targets)
    evidence/g2/g2.2/dev-equivalence/    (DEV equivalence, 16 targets)

Writes:
    evidence/cov/cov0/cross-tabs.json
    evidence/cov/cov0/COV-0.md
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = {
    "sealed": ROOT / "evidence/g2/g2.2/run",
    "dev": ROOT / "evidence/g2/g2.2/dev-equivalence",
}
# §66 layout: sealed audit/failures live at g2.2/, not inside run/
ALT = {
    "sealed": {"failures.jsonl": ROOT / "evidence/g2/g2.2",
               "audit.jsonl": ROOT / "evidence/g2/g2.2"},
}
OUT = ROOT / "evidence/cov/cov0"


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in
            p.read_text(encoding="utf-8").splitlines() if l.strip()]


_KIND_RE = re.compile(r'"kind"\s*:\s*"([^"]+)"')


def _symptom_kind(symptom: str) -> str:
    """failure.symptom is a (possibly truncated) JSON-ish blob; the
    anomaly kind is its first "kind" field."""
    m = _KIND_RE.search(symptom)
    return m.group(1) if m else symptom[:60]


def crosstab(rows: list[dict], *keys) -> dict:
    """Nested Counter over the given row keys (missing -> '<none>')."""
    def walk(rs, ks):
        if not ks:
            return len(rs)
        out: dict[str, dict] = {}
        groups: dict[str, list] = {}
        for r in rs:
            groups.setdefault(str(r.get(ks[0], "<none>")), []).append(r)
        for g, rs2 in groups.items():
            out[g] = walk(rs2, ks[1:])
        return out
    return walk(rows, keys)


def symptom_kind_breakdown(fails: list[dict]) -> dict:
    kinds = Counter()
    for f in fails:
        if f["failure_class"] == "OPERATION_PARSER_FAILURE":
            kinds[_symptom_kind(f["symptom"])] += 1
        else:
            kinds[f["failure_class"]] += 1
    return dict(kinds)


# journal kind -> oss-recon problem owner (frozen mapping for COV-0)
PROBLEM_MAP = {
    "BINDING_NOT_PROVABLE": "representation-binding-evidence",
    "BINDING_NOT_FOUND": "representation-binding-evidence",
    "AMBIGUOUS_BINDING": "representation-binding-evidence",
    "UNBOUND_SUBJECT": "representation-binding-evidence",
    "CHAIN_DISCONTINUITY": "version-chains",
    "ACQUISITION_FAILURE": "evidence-capture (out of oss-recon scope)",
    "FETCH_ERROR": "evidence-capture (out of oss-recon scope)",
    "OPERATION_PARSER_FAILURE": "amendment-actions",
    "disposicion sections present but 0 clauses":
        "amendment-actions",
}


def analyze(run_dir: Path, split: str) -> dict:
    alt = ALT.get(split, {})

    def loc(name: str) -> Path:
        return (alt.get(name) or run_dir) / name

    fails = _jsonl(loc("failures.jsonl"))
    subj = _jsonl(run_dir / "subject-outcomes.jsonl")
    recon = _jsonl(run_dir / "reconciliation.jsonl")
    binds = _jsonl(run_dir / "bindings.jsonl")
    life = _jsonl(run_dir / "lifecycle.jsonl")
    rels = _jsonl(run_dir / "relations.jsonl")
    audit = _jsonl(loc("audit.jsonl"))

    # debt ownership: every journaled abstention mapped to the
    # oss-recon problem that would have to fix it
    kind_by_target: dict[str, Counter] = {}
    for f in fails:
        k = (_symptom_kind(f["symptom"])
             if f["failure_class"] == "OPERATION_PARSER_FAILURE"
             else f["failure_class"])
        kind_by_target.setdefault(f.get("target", "?"),
                                  Counter())[k] += 1
    problem_debt = Counter()
    for t, kinds in kind_by_target.items():
        for k, n in kinds.items():
            problem_debt[PROBLEM_MAP.get(k, "unmapped:" + k)] += n

    # non-emission accounting per target
    ne_by_target = crosstab(
        [r for r in subj if r["non_emission_reason"]],
        "target", "non_emission_reason")

    # O1 unattribution per modifier — where leaf ops lose ownership
    unatt = Counter()
    unatt_mod = Counter()
    for r in recon:
        for s, n in r["o1_distribution"].items():
            if s in ("NOT_PROVABLE", "AMBIGUOUS"):
                unatt[r["target"]] += n
                unatt_mod[f'{r["target"]}|{r["modifier"]}'] += n

    # zero-relation TARGET_PROVEN ops: subject-less vs O2-failed
    tp_zero = {"NO_SUBJECT_CANDIDATES": 0, "O2_FAILED": 0}
    tp_subj = [r for r in subj
               if r["o1_status"] == "TARGET_PROVEN"
               and r["candidate_locator"] is not None]
    per_op: dict[tuple, list] = {}
    for r in tp_subj:
        per_op.setdefault(
            (r["target"], r["modifier"], r["node_index"]),
            []).append(r)
    for (t, m, ni), rows in per_op.items():
        if not any(r["emitted_relation_id"] for r in rows):
            tp_zero["O2_FAILED"] += 1
    no_subj_ops = {(r["target"], r["modifier"], r["node_index"])
                   for r in subj
                   if r["non_emission_reason"]
                   == "NO_SUBJECT_CANDIDATES"}
    tp_zero["NO_SUBJECT_CANDIDATES"] = len(no_subj_ops)

    return {
        "failures": {
            "total": len(fails),
            "kind_breakdown": symptom_kind_breakdown(fails),
            "kind_by_target": {t: dict(c)
                               for t, c in kind_by_target.items()},
            "problem_debt": dict(problem_debt)},
        "subject_outcomes": {
            "rows": len(subj),
            "o2_by_target": crosstab(
                [r for r in subj if r["o2_status"]],
                "target", "o2_status"),
            "non_emission_by_target": ne_by_target},
        "ownership": {
            "unattributed_by_target": dict(unatt),
            "top_unattributed_modifiers":
                dict(unatt_mod.most_common(10))},
        "emission": {
            "relations": len(rels),
            "resolution": dict(Counter(r["resolution"]
                                       for r in rels)),
            "target_proven_zero_relation_ops": tp_zero},
        "bindings": {
            "verdicts": dict(Counter(
                f'{b["side"]}:{b["verdict"]}' for b in binds))},
        "lifecycle": dict(Counter(l["expected_existence_before"]
                                  for l in life)),
        "audit": {
            "rows": len(audit),
            "truth_verdicts": dict(Counter(
                a["truth_verdict"] for a in audit))},
    }


def report(ct: dict) -> str:
    L = ["# COV-0 — coverage debt baseline", ""]
    for split in ("sealed", "dev"):
        a = ct[split]
        L += [f"## {split}", "",
              f"journal entries: {a['failures']['total']}", "",
              "| symptom kind | count |", "|---|---|"]
        for k, n in sorted(a["failures"]["kind_breakdown"].items(),
                           key=lambda x: -x[1]):
            L.append(f"| {k} | {n} |")
        L += ["", "debt by oss-recon problem:", "",
              "| problem | journal entries |", "|---|---|"]
        for k, n in sorted(a["failures"]["problem_debt"].items(),
                           key=lambda x: -x[1]):
            L.append(f"| {k} | {n} |")
        L += ["", "O1 unattributed leaf ops by target:", "",
              "| target | NOT_PROVABLE+AMBIGUOUS |", "|---|---|"]
        for t, n in sorted(a["ownership"]
                           ["unattributed_by_target"].items(),
                           key=lambda x: -x[1]):
            L.append(f"| {t} | {n} |")
        L += ["", "top unattributed modifiers:", "",
              "| target \\| modifier | unattributed |", "|---|---|"]
        for m, n in a["ownership"][
                "top_unattributed_modifiers"].items():
            L.append(f"| {m} | {n} |")
        L += ["",
              f"emission: {a['emission']['relations']} relations, "
              f"resolution {a['emission']['resolution']}",
              f"zero-relation TP ops: "
              f"{a['emission']['target_proven_zero_relation_ops']}",
              f"binding verdicts: {a['bindings']['verdicts']}",
              f"lifecycle: {a['lifecycle']}",
              f"audit rows: {a['audit']['rows']} "
              f"verdicts {a['audit']['truth_verdicts']}", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ct = {split: analyze(d, split) for split, d in RUNS.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cross-tabs.json").write_text(
        json.dumps(ct, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n", encoding="utf-8")
    (OUT / "COV-0.md").write_text(report(ct), encoding="utf-8")
    print(f"wrote {OUT / 'cross-tabs.json'}")
    print(f"wrote {OUT / 'COV-0.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
