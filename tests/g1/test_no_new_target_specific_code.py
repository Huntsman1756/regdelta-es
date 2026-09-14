"""G1 anti-hardcoding guard: no NEW target-specific literals.

Same delta rule as the G0 guard, keyed to the G1.0 base HEAD:
current literals(src/regdelta) - evidence/g1 baseline = empty.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "evidence" / "g1" / "runtime-literals-baseline.json"


def _current_literals() -> set[tuple[str, str, str]]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    pats = {n: re.compile(p)
            for n, p in baseline["patterns"].items()}
    found: set[tuple[str, str, str]] = set()
    for py in sorted((ROOT / "src" / "regdelta").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) \
                    and isinstance(node.value, str):
                for name, pat in pats.items():
                    for m in pat.finditer(node.value):
                        found.add((str(py.relative_to(ROOT)), name,
                                   m.group(0)))
    return found


def test_no_new_target_specific_literals() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    base = {(d["file"], d["pattern"], d["literal"])
            for d in baseline["literals"]}
    new = _current_literals() - base
    assert new == set(), \
        f"new target-specific literals in runtime: {sorted(new)}"
