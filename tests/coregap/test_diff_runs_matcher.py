"""CORE-GAP regression fixture: diff_runs._match_expected.

WS-C found a harness bug: an expected-delta entry carrying only
``match_key_prefix`` or only ``match_contains`` had an empty ``match``
predicate, and ``all()`` over an empty predicate is vacuously True —
so the FIRST entry registered for a file swallowed every differing
row of that file as "expected". That silently mis-adjudicated real
deltas under the wrong case.

This test pins the fixed behavior: an entry without ``match`` fields
is not a catch-all; it only matches via its own declared predicate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "diff_runs", ROOT / "scripts" / "core-gap" / "diff_runs.py")
diff_runs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diff_runs)

_match = diff_runs._match_expected


def test_prefix_only_entry_does_not_match_unrelated_key():
    deltas = [{"case": "X", "file": "audit.jsonl",
               "match_key_prefix": "abc123"}]
    assert _match(deltas, "audit.jsonl", "zzz999",
                  {"relation_id": "zzz999"}) is None


def test_prefix_only_entry_matches_prefix_key():
    deltas = [{"case": "X", "file": "audit.jsonl",
               "match_key_prefix": "abc123"}]
    assert _match(deltas, "audit.jsonl", "abc123deadbeef",
                  {"relation_id": "abc123deadbeef"}) == "X"


def test_contains_only_entry_does_not_match_unrelated_row():
    deltas = [{"case": "X", "file": "failures.jsonl",
               "match_contains": "norma:10"}]
    row = {"symptom": "{\"subject\": \"anejo:5.indice\"}"}
    assert _match(deltas, "failures.jsonl", "key", row) is None


def test_contains_only_entry_matches_substring():
    deltas = [{"case": "X", "file": "failures.jsonl",
               "match_contains": "anejo:5.indice"}]
    row = {"symptom": "{\"subject\": \"anejo:5.indice\"}"}
    assert _match(deltas, "failures.jsonl", "key", row) == "X"


def test_empty_match_entry_does_not_shadow_later_entry():
    """Regression: the first file entry with no `match` swallowed every
    row — rows that should have hit a later entry were mislabeled."""
    deltas = [
        {"case": "CATCH_ALL_BUG", "file": "audit.jsonl",
         "match_key_prefix": "does-not-match"},
        {"case": "CORRECT", "file": "audit.jsonl",
         "match": {"locator_key": "anejo:1"}},
    ]
    row = {"locator_key": "anejo:1"}
    assert _match(deltas, "audit.jsonl", "anykey", row) == "CORRECT"


def test_empty_match_entry_yields_unexpected_not_mislabeled():
    """A row matching nothing must fall through to UNEXPECTED, not be
    claimed by a prefix/contains-only entry."""
    deltas = [
        {"case": "P", "file": "relations.jsonl",
         "match_key_prefix": "aaa"},
        {"case": "C", "file": "relations.jsonl",
         "match_contains": "bbb"},
    ]
    row = {"locator_key": "unrelated"}
    assert _match(deltas, "relations.jsonl", "ccc", row) is None


def test_match_dict_still_requires_all_fields():
    deltas = [{"case": "X", "file": "relations.jsonl",
               "match": {"locator_key": "anejo:1",
                         "modifier_boe": "BOE-A-2018-17880"}}]
    assert _match(deltas, "relations.jsonl", "k",
                  {"locator_key": "anejo:1",
                   "modifier_boe": "BOE-A-2018-17880"}) == "X"
    assert _match(deltas, "relations.jsonl", "k",
                  {"locator_key": "anejo:1",
                   "modifier_boe": "BOE-A-2020-6186"}) is None
