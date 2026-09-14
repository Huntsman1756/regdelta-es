"""G0-G fix-admission guard: no NEW target-specific literals.

The frozen runtime already contains target-specific literals (docstrings
and comments describing the C4/2017 corpus). Demanding zero literals
would fail on frozen code, so the rule is a delta:

    current literals(src/regdelta) - baseline literals = empty

The baseline and the pattern definitions are committed at
evidence/g0g/runtime-literals-baseline.json; the test compiles the
patterns from that file so generator and guard cannot drift apart.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "evidence" / "g0g" / "runtime-literals-baseline.json"


def _current_literals() -> set[tuple[str, str, str, int]]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    pats = {n: re.compile(p)
            for n, p in baseline["patterns"].items()}
    found: set[tuple[str, str, str, int]] = set()
    for py in sorted((ROOT / "src" / "regdelta").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) \
                    and isinstance(node.value, str):
                for name, pat in pats.items():
                    for m in pat.finditer(node.value):
                        found.add((str(py.relative_to(ROOT)), name,
                                   m.group(0), node.lineno))
    return found


def test_no_new_target_specific_literals() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    base = {(d["file"], d["pattern"], d["literal"], d["lineno"])
            for d in baseline["literals"]}
    new = _current_literals() - base
    assert new == set(), \
        f"new target-specific literals in runtime: {sorted(new)}"
