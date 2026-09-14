"""G2.0 semantic seen-set: every instrument whose normative content was
semantically parsed during pre-G0, G0, G1.0/G1.1 or the G1.2 sealed run.

Mechanical derivation — no human recall:

  1. evidence/g1/semantic-seen-set.json   (pre-G0 + G0 + G1, 47 ids)
  2. evidence/g1/selection-v2.json        (3 former G1 holdout targets,
                                           opened at G1.2)
  3. evidence/g1/gold/declared_modifiers.json
         every declared modifier id — the sealed evaluator loaded each
         one's diario XML for recall verification
  4. boe_ids inside every relations/failures/audit artifact of the G1
     DEV runs and the G1.2 sealed run (evaluator + runtime loads)

CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN (same rule as G1.0): bytes
only fetched, hashed or structurally classified do NOT mark an
instrument as seen.

Usage: uv run python -X utf8 scripts/g2/build_seen_set.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G1 = ROOT / "evidence" / "g1"
OUT = ROOT / "evidence" / "g2" / "semantic-seen-set.json"

BOE_ID_RE = re.compile(r"BOE-A-\d{4}-\d+")


def _boe_ids_in_file(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(BOE_ID_RE.findall(
        path.read_text(encoding="utf-8", errors="replace")))


def main() -> int:
    sources: dict[str, list[str]] = {}

    g1 = json.loads((G1 / "semantic-seen-set.json")
                    .read_text(encoding="utf-8"))
    sources["g1_semantic_seen_set"] = g1["boe_ids"]

    sel = json.loads((G1 / "selection-v2.json").read_text(
        encoding="utf-8"))
    sources["g1_holdout_targets_opened_g12"] = sorted(
        sel["SEALED_HOLDOUT"])

    gold = json.loads((G1 / "gold" / "declared_modifiers.json")
                      .read_text(encoding="utf-8"))
    sources["g1_gold_declared_modifiers"] = sorted(
        {d["modifier_boe_id"] for g in gold.values()
         for d in g.get("declared", [])})

    run_ids: set[str] = set()
    for p in sorted(G1.glob("dev/runs/*/relations.jsonl")) + \
            sorted(G1.glob("dev/runs/*/failures.jsonl")) + \
            sorted(G1.glob("dev/runs/*/audit.jsonl")) + \
            sorted((G1 / "g1.2").glob("**/relations.jsonl")) + \
            sorted((G1 / "g1.2").glob("**/failures.jsonl")) + \
            sorted((G1 / "g1.2").glob("audit.jsonl")) + \
            sorted((G1 / "g1.2").glob("run/bindings.jsonl")) + \
            sorted((G1 / "g1.2").glob("run/chains.jsonl")):
        run_ids |= _boe_ids_in_file(p)
    sources["g1_run_artifacts_instrument_ids"] = sorted(run_ids)

    seen = sorted(set().union(*[set(v) for v in sources.values()]))

    out = {
        "gate": "G2.0",
        "rule": ("SEMANTICALLY_SEEN = instruments whose normative body "
                 "was parsed by the RegDelta pipeline or the frozen "
                 "evaluator during pre-G0 work, G0-G.1, G0-G.2, G1.1 or "
                 "G1.2 (incl. the opened G1 holdout and every modifier "
                 "loaded by it). CAPTURED_STRUCTURALLY does not count."),
        "derived_from": {k: len(v) for k, v in sources.items()},
        "boe_ids": seen,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True,
                              ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"G2 semantic seen-set: {len(seen)} instruments")
    for k, v in sources.items():
        print(f"  {k}: {len(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
