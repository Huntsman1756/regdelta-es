"""COV-2 §8 — semantic seen-set extension.

Extends the frozen G2.0 seen-set with every instrument semantically
opened through G2.2 and COV-1. Mechanical derivation — no human
recall:

  1. evidence/g2/semantic-seen-set.json          (G2.0 base, 58 ids)
  2. evidence/g2/selection-v2.json               (4 sealed targets,
                                                  opened at G2.2)
  3. evidence/g2/gold/instrument_ownership.json  (sealed gold:
                                                  declared posteriores
                                                  + risk-event M/C ids
                                                  the evaluator loaded)
  4. every BOE-A id occurring inside G2.2 run artifacts
     (evidence/g2/g2.2/**) — the sealed runner + evaluator parsed the
     target, each discovered modifier and every before/after
     instrument referenced by an emitted relation
  5. every BOE-A id inside COV-1 experiment case/result artifacts
     (evidence/cov/exp-*/**) — EXP-B1/EXP-L1 replayed the frozen
     ledgers and modifier documents evaluator-side

DEV-equivalence artifacts are scanned too: those instruments were
already seen, so the union is unchanged in spirit but exact in fact.

CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN: discovery-v2 and cov3
eligibility fetches (metadatos/referencias only) do NOT enter the
seen-set. Scanning artifacts is deliberately over-inclusive: an id
that was only ever referenced (never parsed) may be excluded from
future holdout candidacy — a conservative exclusion, never a
contamination.

Usage: uv run python -X utf8 scripts/cov/build_seen_set.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G2 = ROOT / "evidence" / "g2"
COV = ROOT / "evidence" / "cov"
OUT = COV / "semantic-seen-set.json"

BOE_ID_RE = re.compile(r"BOE-A-\d{4}-\d+")


def _boe_ids_in_file(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(BOE_ID_RE.findall(text))


def _boe_ids_under(d: Path, patterns: tuple[str, ...]) -> set[str]:
    out: set[str] = set()
    for pat in patterns:
        for p in sorted(d.glob(pat)):
            if p.is_file():
                out |= _boe_ids_in_file(p)
    return out


def main() -> int:
    sources: dict[str, list[str]] = {}

    g2 = json.loads((G2 / "semantic-seen-set.json")
                    .read_text(encoding="utf-8"))
    sources["g2_semantic_seen_set"] = g2["boe_ids"]

    sel = json.loads((G2 / "selection-v2.json").read_text(
        encoding="utf-8"))
    sources["g22_sealed_targets_opened"] = sorted(
        t["boe_id"] for t in sel["selected"])

    gold = json.loads((G2 / "gold" / "instrument_ownership.json")
                      .read_text(encoding="utf-8"))
    gold_ids: set[str] = set(gold)
    for g in gold.values():
        for d in g.get("declared_posteriores", []):
            if d.get("referencia"):
                gold_ids.add(d["referencia"])
        for e in g.get("corrigendum_risk_events", []):
            gold_ids.add(e["corrigendum"])
            gold_ids.add(e["corrected_instrument"])
        for e in g.get("multi_target_events", []):
            gold_ids.update(e.get("modified_instruments", []))
    sources["g2_ownership_gold_ids"] = sorted(gold_ids)

    sources["g22_run_artifact_ids"] = sorted(_boe_ids_under(
        G2 / "g2.2", ("**/*.jsonl", "**/*.json")))
    sources["cov1_experiment_artifact_ids"] = sorted(_boe_ids_under(
        COV, ("exp-*/*.json", "exp-*/*.jsonl")))

    seen = sorted(set().union(*[set(v) for v in sources.values()]))

    out = {
        "gate": "COV-2",
        "rule": ("SEMANTICALLY_SEEN = G2.0 seen-set UNION every "
                 "instrument semantically opened by the G2.2 sealed "
                 "run, the G2.2 DEV-equivalence re-run, the G2 gold "
                 "loader and the COV-1 experiments. "
                 "CAPTURED_STRUCTURALLY does not count."),
        "extends": "evidence/g2/semantic-seen-set.json",
        "derived_from": {k: len(v) for k, v in sources.items()},
        "boe_ids": seen,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True,
                              ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"COV-2 semantic seen-set: {len(seen)} instruments")
    for k, v in sources.items():
        print(f"  {k}: {len(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
