"""Freeze the target-specific literal baseline for src/regdelta at HEAD.

Scans every .py under src/regdelta via AST and records string/integer
literals matching target-specific patterns (BOE ids, circular numbers,
estado codes, locator_key syntax, BOE page numbers). The result is the
baseline for tests/g0g/test_no_target_specific_code.py: G0-G.1 may not
introduce NEW target-specific literals into runtime code.

Usage: .venv/Scripts/python.exe -X utf8 scripts/g0g/gen_baseline.py
"""

from __future__ import annotations

import ast
import json
import re
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
            text = node.value
            for name, pat in PATTERNS.items():
                for m in pat.finditer(text):
                    found.append({"file": str(path.relative_to(ROOT)),
                                  "pattern": name,
                                  "literal": m.group(0),
                                  "lineno": node.lineno})
    return found


def main() -> int:
    out = []
    for py in sorted((ROOT / "src" / "regdelta").rglob("*.py")):
        out.extend(literals_in(py))
    baseline = {
        "baseline_head": "ef58530f5ba8787879ab897fecfc2dd9c424ce69",
        "patterns": {name: pat.pattern
                     for name, pat in PATTERNS.items()},
        "description": "target-specific literals already present in "
                       "src/regdelta at G0-G.0 freeze; the guard test "
                       "asserts the current set minus this set is empty",
        "literals": sorted(out, key=lambda d: (
            d["file"], d["lineno"], d["literal"])),
    }
    dst = ROOT / "evidence" / "g0g" / "runtime-literals-baseline.json"
    dst.write_text(json.dumps(baseline, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"{len(out)} baseline literals "
          f"across {len({d['file'] for d in out})} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
