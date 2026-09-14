"""G1.0 target-specific literal baseline for src/regdelta at HEAD.

Identical scan to scripts/g0g/gen_baseline.py; writes the G1 baseline
to evidence/g1/runtime-literals-baseline.json so the G1 guard asserts
the delta against THIS gate's base, not the older G0 one.

Usage: uv run python -X utf8 scripts/g1/gen_baseline_g1.py
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PATTERNS = {
    "boe_id": re.compile(r"\bBOE-[A-Z]-\d{4}-\d+\b"),
    "circular_number": re.compile(r"\bCircular \d+/\d{4}\b"),
    "estado_code": re.compile(
        r"\b(?:FI|FC|FR|CG|CN|AN|AP|CU|EX|GO|PR|RE|SO|TR|IG|SA|PR|"
        r"BA|PC|CF|ER|PV|RF)\s?\d+(?:[-.]\d+)*\b"),
    "locator_key": re.compile(
        r"\b(?:norma|estado|anejo|apartado|disposicion|titulo|"
        r"capitulo|seccion|articulo):[^\s'\"]+"),
    "boe_page": re.compile(r"\bboe_page[\"']?\s*[:=]\s*\d{4,}"),
    "boe_url": re.compile(r"boe\.es/\S*disp/\d{4}/\d+/\d+"),
}


def literals_in(path: Path) -> list[dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name, pat in PATTERNS.items():
                for m in pat.finditer(node.value):
                    found.append({"file": str(path.relative_to(ROOT)),
                                  "pattern": name,
                                  "literal": m.group(0),
                                  "lineno": node.lineno})
    return found


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    out = []
    for py in sorted((ROOT / "src" / "regdelta").rglob("*.py")):
        out.extend(literals_in(py))
    baseline = {
        "baseline_head": head,
        "patterns": {name: pat.pattern
                     for name, pat in PATTERNS.items()},
        "description": "target-specific literals present in "
                       "src/regdelta at the G1.0 base; the G1 guard "
                       "asserts the current set minus this set is empty",
        "literals": sorted(out, key=lambda d: (
            d["file"], d["lineno"], d["literal"])),
    }
    dst = ROOT / "evidence" / "g1" / "runtime-literals-baseline.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(baseline, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"{len(out)} baseline literals at {head[:9]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
