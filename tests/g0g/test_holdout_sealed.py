"""G0-G.0 holdout seal guards.

Two properties:

1. SEAL integrity — the committed SEAL must exactly describe the
   holdout manifest and every artifact under evidence/g0g/holdout/raw/.

2. Access rule — nothing outside the whitelist may reference the
   holdout evidence directory. Whitelist per PREREG.md: this verifier,
   the sealer (scripts/g0g/capture.py), and the future G0-G.2
   evaluator.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G0G = ROOT / "evidence" / "g0g"
HOLDOUT = G0G / "holdout"

# Files allowed to name the holdout evidence directory.
_WHITELIST = {
    Path("tests/g0g/test_holdout_sealed.py"),
    Path("scripts/g0g/capture.py"),
    Path("evidence/g0g/PREREG.md"),
    Path("evidence/g0g/protocol.md"),
}

_OTHER_GATE_SEALERS = {
    Path("scripts/port-cnmv/scout_cnmv.py"),
    Path("scripts/port-cnmv/split_isolation.py"),
}

_REF_TOKENS = ("g0g/holdout", "g0g\\holdout", "g0g\" / \"holdout")
_GENERIC_REF_TOKENS = ('"holdout"', "'holdout'")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_seal_integrity() -> None:
    seal = json.loads((HOLDOUT / "SEAL").read_text(encoding="utf-8"))
    manifest_bytes = (HOLDOUT / "manifest.json").read_bytes()
    assert _sha256(manifest_bytes) == seal["manifest_sha256"]

    files = sorted((HOLDOUT / "raw").iterdir())
    assert len(files) == seal["artifact_count"]
    blob = b"".join(f.read_bytes() for f in files)
    assert len(blob) == seal["aggregate_bytes"]
    assert _sha256(blob) == seal["aggregate_sha256"]

    manifest = json.loads(manifest_bytes)
    assert sorted(seal["targets"]) == seal["targets"]
    for name, entry in manifest["entries"].items():
        if "path" not in entry:
            assert entry.get("http_status") == 404, name
            continue
        p = ROOT / entry["path"]
        assert p.read_bytes() and _sha256(p.read_bytes()) \
            == entry["sha256"], name


def test_no_unauthorized_holdout_reference() -> None:
    offenders = []
    for base in ("src", "tests", "scripts"):
        for f in sorted((ROOT / base).rglob("*")):
            if not f.is_file() or f.suffix not in (".py", ".md",
                                                 ".json", ".txt"):
                continue
            rel = f.relative_to(ROOT).as_posix()
            if Path(rel) in _WHITELIST:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if Path(rel) in _OTHER_GATE_SEALERS:
                # These are sealers for a different gate's corpus; they may
                # use the generic word "holdout" but must never point at the
                # g0g holdout directory.
                hits = [tok for tok in _REF_TOKENS if tok in text]
            else:
                hits = [tok for tok in (_REF_TOKENS + _GENERIC_REF_TOKENS)
                        if tok in text]
            if hits:
                offenders.append(str(rel))
    assert offenders == []
