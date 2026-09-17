"""PORT-CNMV-1 — per-operation locator-proof diagnostic.

Replays DEV modifier documents and prints, for every leaf operation
attributed TARGET_PROVEN, each subject's locator_key plus its O2
prove_locator status. Diagnostic only — nothing is persisted.

Usage:
    PYTHONPATH=src python -X utf8 scripts/port-cnmv/diag_ops.py \
        --target BOE-A-2010-13162
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import regdelta.profiles.cnmv  # noqa: E402,F401
from regdelta.profile import use_profile  # noqa: E402

use_profile("cnmv-circular")

from regdelta import operations, ownership  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402

DEV = ROOT / "evidence" / "port-cnmv" / "split-v2" / "dev"


def _dev_xml(boe_id: str) -> bytes | None:
    man = json.loads((DEV / "manifest.json").read_text(encoding="utf-8"))
    name = f"boe_diario_xml__{boe_id}.xml"
    e = man["entries"].get(name)
    if e is None:
        return None
    return (ROOT / e["path"]).read_bytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    args = ap.parse_args()

    body = _dev_xml(args.target)
    if body is None:
        raise SystemExit(f"no dev diario xml for {args.target}")
    res = boe_diario.parse_diario(body)
    doc = res.doc
    print(f"{args.target} parse={res.parse_status}")

    import re
    m = re.search(r"Circular\s+(\d+)\s*/\s*(\d{4})",
                  doc.metadata.get("titulo", ""))
    target_ref = (int(m.group(1)), int(m.group(2))) if m else None
    print(f"target_ref={target_ref} titulo={doc.metadata.get('titulo','')[:90]}")

    for ref in doc.posteriores:
        if not any(w in ref.palabra.upper()
                   for w in ("CORREG", "CORREC")):
            mb = ref.referencia
            mbody = _dev_xml(mb)
            if mbody is None:
                print(f"  modifier {mb}: NO DEV XML")
                continue
            mres = boe_diario.parse_diario(mbody)
            if not mres.doc:
                print(f"  modifier {mb}: parse {mres.parse_status}")
                continue
            result = operations.parse_all_operations(mres.doc)
            for op in result.operations:
                if op.is_container:
                    continue
                att = ownership.attribute_operation(
                    op, mres.doc, target_ref, args.target)
                tag = att.status
                line = (f"  [{tag}] {op.operation_kind} "
                        f"{op.clause_text[:90]!r}")
                print(line)
                if tag == "TARGET_PROVEN":
                    for s in op.subjects:
                        decl = ownership.prove_locator(op, s)
                        print(f"      subj {s.locator_key} kind={s.kind}"
                              f" label={s.label[:40]!r}"
                              f" -> {decl.status} ({decl.method})")


if __name__ == "__main__":
    main()
