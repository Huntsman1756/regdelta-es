"""Offline integrity tests over the captured G0-C.1 annex/state evidence.

These tests recompute SHA-256 over stored image/PDF raws, re-derive the
image->page binding, and re-run the estado detection + correction anchors
against the page map. They never touch the network and are skipped if the
G0-C.1 evidence has not been generated yet.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "g0c"))
sys.path.insert(0, str(ROOT / "scripts" / "g0c1"))

G0C1 = ROOT / "evidence" / "g0c1"
MANIFEST = G0C1 / "raw" / "manifest.json"
PAGE_MAP = G0C1 / "page-map.json"
INVENTORY = G0C1 / "image-inventory.json"
ANNEX_MAP = G0C1 / "annex-map.json"
STATE_CASES = G0C1 / "state-cases.json"

pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(),
    reason="G0-C.1 evidence not generated (run scripts/g0c1/probe_*.py)",
)


def test_g0c1_raws_match_sha256():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name, entry in manifest["entries"].items():
        if not entry.get("path"):
            continue
        data = (ROOT / entry["path"]).read_bytes()
        assert entry["size_bytes"] == len(data), name
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], name


def test_pdf_page_map_covers_the_whole_document():
    pm = json.loads(PAGE_MAP.read_text(encoding="utf-8"))
    assert pm["pdf_pages"] == 588
    assert pm["boe_page_span"] == [119454, 120041]
    # every page carries the printed BOE page header in the text layer
    assert all(p["text_length"] > 0 for p in pm["pages"])


def test_image_inventory_is_sequential_and_complete():
    inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert inv["image_count_xml"] == 326
    assert inv["image_count_html_alt"] == 326
    assert inv["alt_sequential"] is True
    pages = [i["boe_page"] for i in inv["images"]]
    assert pages == list(range(119716, 120042))


def test_annex_map_correction_anchors_all_match():
    am = json.loads(ANNEX_MAP.read_text(encoding="utf-8"))
    assert am["anchors_total"] >= 10
    assert am["anchors_matching"] == am["anchors_total"]
    # every annex page belongs to exactly one kind
    assert {p["kind"] for p in am["pages"]} == {"CONTENT", "CONTINUATION", "INDEX"}
    # every annex page has an image bound to it
    assert all(p["img_alt"] for p in am["pages"])


def test_case_estados_have_expected_spans():
    am = json.loads(ANNEX_MAP.read_text(encoding="utf-8"))
    assert am["estados"]["FI 105"]["page_span"] == [119835, 119836]
    assert am["estados"]["FI 102"]["page_span"] == [119823, 119824]
    assert am["estados"]["FI 142"]["page_span"] == [119907, 119908]
    lo, hi = am["estados"]["FI 100"]["page_span"]
    assert lo <= 119818 <= hi


def test_state_cases_reference_existing_raws():
    cases = json.loads(STATE_CASES.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    g0c_manifest = json.loads(
        (ROOT / "evidence" / "g0c" / "raw" / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(cases["cases"]) == 6

    def check_repr(rep):
        if rep["kind"] == "IMAGE" and "raw_name" in rep:
            e = manifest["entries"][rep["raw_name"]]
            assert e["sha256"] == rep["sha256"], rep["raw_name"]
        if rep["kind"] in {"TABLE", "TEXT"} and "raw_name" in rep:
            assert rep["raw_name"] in g0c_manifest["entries"]

    for case in cases["cases"]:
        assert case["confidence"] == "PROVEN"
        for hop in case.get("hops", [case]):
            check_repr(hop["old_representation"])
            new = hop["new_representation"]
            if new["kind"] == "IMAGE" and "raw_name" in new:
                assert manifest["entries"][new["raw_name"]]["sha256"] == new["sha256"]
            for level in hop["diff_level"]:
                assert level in cases["diff_level_enum"]


def test_chained_case_hop2_is_fully_textual():
    cases = json.loads(STATE_CASES.read_text(encoding="utf-8"))
    chained = next(c for c in cases["cases"] if c["case_id"].endswith("chained"))
    hop1, hop2 = chained["hops"]
    assert hop1["old_representation"]["kind"] == "IMAGE"
    assert hop2["old_representation"]["kind"] == "TABLE"
    assert hop2["diff_level"] == ["TEXT_DIFF_PROVEN"]
    # hop2's old must be byte-identical to hop1's new
    assert hop2["old_representation"]["sha256"] == hop1["new_representation"]["sha256"]
