"""G1 DEV manifest: logical union of the already-open G0 evidence.

References existing artifact paths and hashes — nothing is downloaded
or duplicated. Sources:

  evidence/g0g/dev/manifest.json            (8 GENERALIZATION_DEV)
  the former G0-G sealed manifest           (4 former targets, globbed)

Output: evidence/g1/dev/manifest.json keyed by artifact name, plus a
target allowlist section for the 12 G1 DEV targets.

Usage: uv run python -X utf8 scripts/g1/build_dev_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
OUT = ROOT / "evidence" / "g1" / "dev" / "manifest.json"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    dev_m = json.loads((G0G / "dev" / "manifest.json")
                       .read_text(encoding="utf-8"))
    sealed = [p for p in G0G.glob("*/manifest.json")
              if p.parent.name not in ("raw", "dev")]
    assert len(sealed) == 1, sealed
    se_m = json.loads(sealed[0].read_text(encoding="utf-8"))

    entries: dict[str, dict] = dict(dev_m["entries"])
    reused = merged = 0
    for name, e in se_m["entries"].items():
        if name in entries:
            continue
        if "path" in e:
            p = ROOT / e["path"]
            if p.exists() and _sha256(p.read_bytes()) == e["sha256"]:
                merged += 1
            else:
                e = {k: v for k, v in e.items() if k != "path"}
        entries[f"former_{name}"] = e
        reused += 1

    sel = json.loads((G0G / "selection.json").read_text(encoding="utf-8"))
    dev_targets = {b: c for c, cell in sel["cells"].items()
                   for b in cell["GENERALIZATION_DEV"]}
    former = {b: c for c, cell in sel["cells"].items()
              for b in cell["SEALED_HOLDOUT"]}
    targets = {**dev_targets, **former}

    out = {
        "gate": "G1.1",
        "description": "logical union of G0-G DEV + former G0-G sealed "
                       "evidence; paths reference existing artifacts",
        "sources": ["evidence/g0g/dev/manifest.json",
                    str(sealed[0].relative_to(ROOT))],
        "targets": targets,
        "entries": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True,
                              ensure_ascii=False), encoding="utf-8")
    print(f"targets: {len(targets)}, entries: {len(entries)} "
          f"(merged {merged}, 404/errors {reused - merged})")
    print("manifest_sha256:", _sha256(OUT.read_bytes()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
