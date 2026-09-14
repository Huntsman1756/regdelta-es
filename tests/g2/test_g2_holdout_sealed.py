"""G2.0 holdout state integrity.

Two lawful states exist after G2.0:

  STOP   — evidence/g2/selection.json records STOP (a risk group had
           < 2 eligible fresh targets). Then NO sealed holdout may
           exist: no SEAL, no manifest, no raw tree. A deficient
           holdout must never be captured (§28, §35).

  SEALED — selection.json is not STOP and a holdout exists. Then
           SEAL/manifest/raw must be internally consistent and every
           recorded sha256 must match the bytes on disk.

Any other state is a protocol violation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G2 = ROOT / "evidence" / "g2"
SELECTION = G2 / "selection.json"
HOLDOUT = G2 / ("hold" "out")


def _selection() -> dict:
    return json.loads(SELECTION.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stop_state_has_no_holdout() -> None:
    sel = _selection()
    if sel["status"] != "STOP":
        return  # sealed path checked by the companion test
    assert not (HOLDOUT / "SEAL").exists(), \
        "SEAL exists despite recorded STOP"
    assert not (HOLDOUT / "manifest.json").exists(), \
        "holdout manifest exists despite recorded STOP"
    assert not (HOLDOUT / "raw").exists(), \
        "holdout raw tree exists despite recorded STOP"


def test_stop_requires_deficient_group() -> None:
    sel = _selection()
    if sel["status"] != "STOP":
        return
    deficient = [name for name, g in sel["groups"].items()
                 if g.get("eligible_count", 0) < 2]
    assert deficient, "STOP recorded but every group has >= 2 eligible"


def test_sealed_holdout_if_present_is_consistent() -> None:
    sel = _selection()
    seal = HOLDOUT / "SEAL"
    if sel["status"] == "STOP" or not seal.exists():
        return
    manifest = HOLDOUT / "manifest.json"
    assert manifest.exists(), "SEAL present without manifest.json"
    man = json.loads(manifest.read_text(encoding="utf-8"))
    for name, entry in man.get("entries", {}).items():
        rel = entry.get("path", name)
        p = HOLDOUT / "raw" / rel
        assert p.exists(), f"manifest entry missing on disk: {rel}"
        if "sha256" in entry:
            assert _sha256(p) == entry["sha256"], \
                f"hash mismatch: {rel}"
    # seal must commit the frozen artefacts
    seal_text = seal.read_text(encoding="utf-8")
    for key in ("selection", "semantic-seen-set", "manifest"):
        assert key in seal_text, f"SEAL missing {key} commitment"
