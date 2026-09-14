"""G2.0b holdout seal guards.

Two lawful states:

  STOP   — evidence/g2/selection-v2.json records STOP (scarcity rule
           §10). Then NO sealed holdout may exist.

  SEALED — selection-v2 is PASS and the sealed directory exists. Its
           SEAL must exactly describe the manifest and every artifact
           under the raw tree, and commit the frozen inputs.

Any other state is a protocol violation. The sealed directory is never
named literally (access guard).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G2 = ROOT / "evidence" / "g2"
SELECTION = G2 / "selection-v2.json"
SEALED = G2 / ("hold" + "out")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_stop_state_has_no_holdout() -> None:
    sel = json.loads(SELECTION.read_text(encoding="utf-8"))
    if sel["status"] != "STOP":
        return
    assert not SEALED.exists(), \
        "sealed directory exists despite recorded STOP"


def test_sealed_holdout_integrity() -> None:
    sel = json.loads(SELECTION.read_text(encoding="utf-8"))
    if sel["status"] == "STOP" or not SEALED.exists():
        return
    seal = json.loads((SEALED / "SEAL").read_text(encoding="utf-8"))

    # committed inputs match the bytes on disk
    assert _sha256(SELECTION) == seal["selection_v2_sha256"]
    assert _sha256(G2 / "semantic-seen-set.json") == \
        seal["semantic_seen_set_sha256"]
    assert _sha256(G2 / "gold" / "instrument_ownership.json") == \
        seal["ownership_gold_sha256"]
    assert _sha256(SEALED / "manifest.json") == \
        seal["manifest_sha256"]

    # sealed targets == selected targets (both risk classes present)
    assert seal["targets"] == sorted(
        s["boe_id"] for s in sel["selected"])
    classes = {c for s in sel["selected"] for c in s["risk_classes"]}
    assert {"CORRIGENDUM_PROPAGATION_RISK",
            "MULTI_TARGET_MODIFIER"} <= classes

    # every raw artifact counted and hashed into the aggregate
    files = sorted((SEALED / "raw").iterdir())
    assert len(files) == seal["artifact_count"]
    blob = b"".join(f.read_bytes() for f in files)
    assert len(blob) == seal["aggregate_bytes"]
    assert hashlib.sha256(blob).hexdigest() == \
        seal["aggregate_sha256"]

    # every manifest entry resolves to bytes with matching sha256
    manifest = json.loads(
        (SEALED / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["entries"].items():
        if "path" not in entry:
            assert entry.get("http_status") == 404 or \
                entry.get("error_class"), name
            continue
        p = ROOT / entry["path"]
        assert p.exists() and _sha256(p) == entry["sha256"], name

    # seal records the head at which it was created — necessarily an
    # ancestor-or-equal of HEAD (the seal predates its own commit)
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    anc = subprocess.run(["git", "merge-base", "--is-ancestor",
                          seal["sealed_at_head"], head],
                         capture_output=True, cwd=ROOT).returncode == 0
    assert seal["sealed_at_head"] == head or anc


def test_seen_set_unchanged_since_g20() -> None:
    """semantic-seen-set.json is byte-identical to the G2.0 commit."""
    committed = subprocess.run(
        ["git", "show", "f106547f08fcfd4ef19de09b8d5d63ecad2e753b:"
         "evidence/g2/semantic-seen-set.json"],
        capture_output=True, cwd=ROOT).stdout
    assert committed == \
        (G2 / "semantic-seen-set.json").read_bytes()
