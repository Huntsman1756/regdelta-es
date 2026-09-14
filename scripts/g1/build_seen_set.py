"""G1.0 semantic seen-set: every instrument whose normative content was
semantically parsed during any previous phase.

Mechanical derivation — no human recall:

  1. evidence/g0g/seen-set.json          (pre-G0: evidence/** + fixtures)
  2. evidence/g0g/selection.json         (all 12 G0-G targets)
  3. evidence/g0g/gold/declared_modifiers.json
         every declared modifier id — the evaluator loaded each one's
         diario XML for recall verification, and history.reconstruct
         parsed the bodies of those present in the manifests
  4. modifier ids inside every relations/failures artifact of the G0-G
     DEV runs and the G0-G.2 sealed run (evaluator + runtime loads)

CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN: bytes that were only fetched,
hashed or structurally classified (index HTML, sumario items, consolidada
probes, candidate XML posteriores counts, images/PDFs of non-selected
candidates) do NOT mark an instrument as seen and are documented here as
excluded-by-rule, not enumerated per file.

Usage: uv run python -X utf8 scripts/g1/build_seen_set.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
OUT = ROOT / "evidence" / "g1" / "semantic-seen-set.json"

BOE_ID_RE = re.compile(r"BOE-A-\d{4}-\d+")


def _boe_ids_in_jsonl(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.update(BOE_ID_RE.findall(line))
    return ids


def main() -> int:
    sources: dict[str, list[str]] = {}

    pre = json.loads((G0G / "seen-set.json").read_text(encoding="utf-8"))
    sources["pre_g0_seen_set"] = pre["boe_ids"]

    sel = json.loads((G0G / "selection.json").read_text(encoding="utf-8"))
    targets = sorted(
        {b for c in sel["cells"].values()
         for k, v in c.items() if isinstance(v, list) for b in v})
    sources["g0g_targets"] = targets

    gold = json.loads((G0G / "gold" / "declared_modifiers.json")
                      .read_text(encoding="utf-8"))
    mods = sorted({d["modifier_boe_id"] for g in gold.values()
                   for d in g.get("declared", [])})
    sources["g0g_gold_declared_modifiers"] = mods

    run_ids: set[str] = set()
    for p in sorted(G0G.glob("dev/runs/*/relations.jsonl")) + [
            G0G / "g0g2" / "run" / "relations.jsonl"]:
        run_ids |= _boe_ids_in_jsonl(p)
    for p in sorted(G0G.glob("dev/runs/*/failures.jsonl")) + [
            G0G / "g0g2" / "run" / "failures.jsonl",
            G0G / "g0g2" / "failures.jsonl"]:
        run_ids |= _boe_ids_in_jsonl(p)
    run_ids -= set(targets)  # target id also appears as "target" field
    sources["g0g_run_artifacts_modifier_ids"] = sorted(run_ids)

    seen = sorted(set().union(*[set(v) for v in sources.values()]))

    out = {
        "gate": "G1.0",
        "rule": ("SEMANTICALLY_SEEN = instruments whose normative body "
                 "was parsed by the RegDelta pipeline or the frozen "
                 "evaluator during pre-G0 work, G0-G.1 or G0-G.2. "
                 "CAPTURED_STRUCTURALLY (index/sumario/consolidada "
                 "probes/candidate XML markup counts) does not count."),
        "derived_from": {k: len(v) for k, v in sources.items()},
        "boe_ids": seen,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True,
                              ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"semantic seen-set: {len(seen)} instruments")
    for k, v in sources.items():
        print(f"  {k}: {len(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
