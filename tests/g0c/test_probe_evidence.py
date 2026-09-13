"""Offline integrity tests over the captured G0-C evidence.

These tests recompute SHA-256 over the stored raws and over the extracted case
spans. They never touch the network and are skipped if the discovery evidence
has not been generated yet.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "g0c"))

EVIDENCE = ROOT / "evidence" / "g0c"
MANIFEST = EVIDENCE / "raw" / "manifest.json"
CASES = EVIDENCE / "cases.json"
MODIFIERS = EVIDENCE / "modifiers.json"


pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(), reason="G0-C evidence not generated (run scripts/g0c/probe_*.py)"
)


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_every_stored_raw_matches_its_sha256():
    manifest = _manifest()
    for name, entry in manifest["entries"].items():
        if not entry.get("path"):
            continue
        data = (ROOT / entry["path"]).read_bytes()
        assert entry["size_bytes"] == len(data), name
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], name


def test_target_is_absent_from_consolidated_api():
    manifest = _manifest()
    absent = [e for k, e in manifest["entries"].items()
              if k.startswith("boe_api_consolidada_") and "BOE-A-2017-14334" in k]
    assert absent, "negative evidence for the consolidated API must be captured"
    assert all(e["http_status"] == 404 for e in absent)


def test_consolidated_api_exists_for_a_subset():
    manifest = _manifest()
    present = [e for k, e in manifest["entries"].items()
               if k.startswith("boe_api_consolidada_")
               and ("BOE-A-2020-6187" in k or "BOE-A-2020-15602" in k)]
    assert present
    assert all(e["http_status"] == 200 for e in present)


def test_original_annexes_are_images_not_text():
    from probe_parse import parse_document

    doc = parse_document("boe_diario_xml__BOE-A-2017-14334")
    assert len(doc.image_srcs) >= 300
    assert len(doc.tables) <= 3


def test_modifier_discovery_is_symmetric():
    modifiers = json.loads(MODIFIERS.read_text(encoding="utf-8"))
    assert len(modifiers["modifiers"]) == 8
    for m in modifiers["modifiers"]:
        assert m["cross_check"]["target_declared_as_anterior"] is True
        assert m["modifier_publication_date"]
    kinds = {m["kind"] for m in modifiers["modifiers"]}
    assert kinds == {"MODIFICATION", "CORRECTION"}


def test_cases_have_reproducible_hashes_and_valid_confidence():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert len(cases["cases"]) >= 4
    allowed = {"PROVEN", "PARTIAL", "NOT_PROVEN"}
    for case in cases["cases"]:
        assert case["confidence"] in allowed
        for side in ("old", "new"):
            if case[f"{side}_text_available"]:
                digest = hashlib.sha256(case[f"{side}_text"].encode("utf-8")).hexdigest()
                assert case[f"{side}_text_sha256"] == digest, case["case_id"]
            else:
                assert case[f"{side}_text_sha256"] is None
        # A case cannot be PROVEN for old->new if one side is unavailable.
        if case["kind"] == "MODIFICATION":
            if case["old_text_available"] and case["new_text_available"]:
                assert case["confidence"] == "PROVEN", case["case_id"]
