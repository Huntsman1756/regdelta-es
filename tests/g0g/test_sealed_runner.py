"""G0-G.2A pre-open tests for the sealed-split evaluation runner.

These tests exercise scripts/g0g/evaluate_sealed.py exclusively against
the DEV evidence already used in G0-G.1. No sealed corpus bytes are
read here: the DEV manifest and the frozen run-005 metrics are the only
inputs asserted on.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "g0g"))
sys.path.insert(0, str(ROOT / "src"))

import evaluate_sealed as sr  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT  # noqa: E402

G0G = ROOT / "evidence" / "g0g"
SELECTION = G0G / "selection.json"
DEV_MANIFEST = G0G / "dev" / "manifest.json"
GOLD = G0G / "gold" / "declared_modifiers.json"
FROZEN_005 = G0G / "dev" / "runs" / "005-redaccion-verb" / "metrics.json"

pytestmark = pytest.mark.skipif(
    not (DEV_MANIFEST.exists() and FROZEN_005.exists()),
    reason="G0-G dev evidence not present")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable,
         str(ROOT / "scripts" / "g0g" / "evaluate_sealed.py"), *args],
        capture_output=True, text=True, cwd=ROOT)


def _base_args(out: Path) -> list[str]:
    return ["--selection", str(SELECTION),
            "--manifest", str(DEV_MANIFEST),
            "--gold", str(GOLD),
            "--split", "GENERALIZATION_DEV",
            "--output", str(out)]


def test_selection_determines_allowlist():
    sel = json.loads(SELECTION.read_text(encoding="utf-8"))
    dev = sr.split_allowlist(sel, "GENERALIZATION_DEV")
    sealed = sr.split_allowlist(sel, "SEALED_HOLDOUT")
    assert len(dev) == 8 and len(sealed) == 4
    assert not set(dev) & set(sealed)


def test_runner_rejects_target_outside_split(tmp_path):
    """Asking for a sealed-split id under the DEV split fails closed."""
    sel = json.loads(SELECTION.read_text(encoding="utf-8"))
    sealed_ids = sr.split_allowlist(sel, "SEALED_HOLDOUT")
    t = sorted(sealed_ids)[0]
    r = _run(_base_args(tmp_path / "out") + ["--targets", t])
    assert r.returncode == 2
    assert "FAIL CLOSED" in r.stdout
    assert not (tmp_path / "out" / "run.json").exists()


def test_runner_rejects_unknown_split(tmp_path):
    r = _run(["--selection", str(SELECTION),
              "--manifest", str(DEV_MANIFEST),
              "--gold", str(GOLD),
              "--split", "NOT_A_SPLIT",
              "--output", str(tmp_path / "o")])
    assert r.returncode == 2


def test_fetch_is_evidence_import_only():
    """Every served byte is EVIDENCE_IMPORT; unknown URLs are MISSING,
    never fetched."""
    by_url = sr.load_manifest(DEV_MANIFEST)
    fetch = sr.evidence_fetch(by_url, ROOT)
    url = next(iter(by_url))
    e = by_url[url]
    res = fetch(url, "*/*")
    assert res.via == EVIDENCE_IMPORT
    if "path" in e:
        assert res.body == (ROOT / e["path"]).read_bytes()
    else:
        assert res.error_class == "MISSING"
    miss = fetch("https://example.invalid/nope", "*/*")
    assert miss.via == EVIDENCE_IMPORT
    assert miss.error_class == "MISSING"


def test_metric_names_and_taxonomy_frozen():
    expected = {
        "declared_modifier_recall", "operation_parsing_rate",
        "subject_locator_resolution", "representation_binding",
        "chain_reconstruction", "applicability_extraction",
        "query_execution", "false_positive_facts", "source_limitations",
    }
    assert set(sr.METRIC_KEYS) | {"false_positive_facts",
                                "source_limitations"} == expected
    assert sr.FAILURE_CLASSES == {
        "SOURCE_LIMITATION", "ACQUISITION_FAILURE", "PARSER_FAILURE",
        "SCHEMA_FAILURE", "EVALUATION_FAILURE"}


def test_runner_dev_equivalence(tmp_path):
    """The sealed runner on the DEV split executes deterministically
    and audits 100% of emitted relations without mutating evidence.

    G1_INTENTIONAL_SEMANTIC_CHANGE: equality with the frozen G0-G.1
    metrics (runs/005) is no longer asserted — that state was produced
    by the pre-binder runtime and encodes the false bindings G1.1
    removes. The frozen artifact remains immutable history; the G1
    comparison point is evidence/g1/dev/runs/000-baseline + final."""
    before = hashlib.sha256(DEV_MANIFEST.read_bytes()).hexdigest()
    out = tmp_path / "equiv"
    r = _run(_base_args(out))
    assert r.returncode == 0, r.stderr[-2000:]
    assert hashlib.sha256(DEV_MANIFEST.read_bytes()).hexdigest() \
        == before

    tg = json.loads((out / "targets.json").read_text(encoding="utf-8"))
    ft = json.loads((G0G / "dev" / "runs" / "005-redaccion-verb"
                     / "targets.json").read_text(encoding="utf-8"))
    for t, v in ft.items():
        assert tg[t]["inventory"]["relations"] \
            == v["inventory"]["relations"], t
    # audit coverage: one row per emitted relation
    rels = sum(v["inventory"]["relations"] for v in tg.values())
    audit = (out / "audit.jsonl").read_text(encoding="utf-8")
    assert sum(1 for l in audit.splitlines() if l.strip()) == rels
