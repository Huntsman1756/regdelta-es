"""G1 holdout seal guards.

1. SEAL integrity — if a G1 sealed holdout exists, its SEAL must
   exactly describe evidence/g1/<sealed dir> manifest + raw bytes.
   (G1.0 STOP: selection produced <4 fresh amendment-dense targets, so
   no sealed corpus exists yet — the integrity check skips until one
   does.)

2. Access rule — nothing outside the whitelist may reference the G1
   sealed evidence directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
G1 = ROOT / "evidence" / "g1"
SEALED = G1 / ("hold" "out")

_WHITELIST = {
    Path("tests/g1/test_holdout_sealed.py"),
    Path("evidence/g1/PREREG.md"),
    Path("evidence/g1/protocol.md"),
}

_REF_TOKENS = ("g1/" + "hold" "out", "g1\\" + "hold" "out",
               "g1\" / \"" + "hold" "out")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_seal_integrity() -> None:
    seal_path = SEALED / "SEAL"
    if not seal_path.exists():
        pytest.skip("G1 sealed corpus does not exist (G1.0 STOP: "
                    "amendment-dense pool underpopulated)")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    manifest_bytes = (SEALED / "manifest.json").read_bytes()
    assert _sha256(manifest_bytes) == seal["manifest_sha256"]

    files = sorted((SEALED / "raw").iterdir())
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


def test_no_unauthorized_g1_sealed_reference() -> None:
    offenders = []
    for base in ("src", "tests", "scripts"):
        for f in sorted((ROOT / base).rglob("*")):
            if not f.is_file() or f.suffix not in (".py", ".md",
                                                 ".json", ".txt"):
                continue
            rel = f.relative_to(ROOT)
            if rel in _WHITELIST:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if any(tok in text for tok in _REF_TOKENS):
                offenders.append(str(rel))
    assert offenders == []
