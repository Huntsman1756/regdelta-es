"""G1.2A PREOPEN.json generator.

Hash-only pre-open commitment (protocol §12): reads evidence bytes
solely to compute SHA-256 integrity values — never to evaluate. The
sealed corpus directory is located by convention relative to
evidence/g1; its name is never written literally here.

Usage:
    uv run python -X utf8 scripts/g1/preopen.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G1 = ROOT / "evidence" / "g1"
SEALED = G1 / ("hold" "out")
G12 = G1 / "g1.2"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _file_sha(p: Path) -> str:
    return _sha256(p.read_bytes())


def _dir_sha(d: Path) -> str:
    """Aggregate sha256 over every file under d, sorted by relative
    path."""
    h = hashlib.sha256()
    for f in sorted(d.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(d)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _src_tree_sha() -> str:
    h = hashlib.sha256()
    for f in sorted((ROOT / "src" / "regdelta").rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(ROOT)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    seal_bytes = (SEALED / "SEAL").read_bytes()
    seal = json.loads(seal_bytes)
    manifest_bytes = (SEALED / "manifest.json").read_bytes()
    raw_files = sorted((SEALED / "raw").iterdir())
    blob = b"".join(f.read_bytes() for f in raw_files)
    assert _sha256(manifest_bytes) == seal["manifest_sha256"]
    assert _sha256(blob) == seal["aggregate_sha256"]
    assert len(raw_files) == seal["artifact_count"]

    preopen = {
        "gate": "G1.2",
        "runtime_head": head,
        "evaluation_head": None,  # this commit's SHA; recorded as
        # G1_EVALUATION_HEAD once the freeze commit lands
        "src_tree_sha256": _src_tree_sha(),
        "runner_sha256": _file_sha(
            ROOT / "scripts" / "g1" / "evaluate_sealed_g1.py"),
        "evaluator_sha256": _file_sha(
            ROOT / "scripts" / "g1" / "evaluate_g1.py"),
        "g0g_evaluator_sha256": _file_sha(
            ROOT / "scripts" / "g0g" / "evaluate_dev.py"),
        "evaluator_contract_sha256": _file_sha(
            ROOT / "evidence" / "g0g" / "dev" / "EVALUATOR.md"),
        "prereg_sha256": _file_sha(G1 / "PREREG.md"),
        "protocol_sha256": _file_sha(G1 / "protocol.md"),
        "g1_0b_amendment_sha256": _file_sha(G1 / "G1.0b-AMENDMENT.md"),
        "selection_v2_sha256": _file_sha(G1 / "selection-v2.json"),
        "semantic_seen_set_sha256": _file_sha(
            G1 / "semantic-seen-set.json"),
        "gold_sha256": _file_sha(
            G1 / "gold" / "declared_modifiers.json"),
        "seal_sha256": _sha256(seal_bytes),
        "holdout_manifest_sha256": _sha256(manifest_bytes),
        "aggregate_holdout_sha256": seal["aggregate_sha256"],
        "runtime_literals_baseline_sha256": _file_sha(
            G1 / "runtime-literals-baseline.json"),
        "corpus_73_sha256": _file_sha(
            G1 / "dev" / "g0-false-binding-corpus.json"),
        "dev_manifest_sha256": _file_sha(G1 / "dev" / "manifest.json"),
        "dev_equivalence_artifact_sha256": _dir_sha(
            G12 / "dev-equivalence"),
        "sealed_targets": seal["targets"],
    }
    G12.mkdir(exist_ok=True)
    (G12 / "PREOPEN.json").write_text(json.dumps(
        preopen, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(preopen, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
