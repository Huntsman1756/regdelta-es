"""G0-D runtime tests: production applicability ledger.

Reconstructs the G0-C ledger offline from the captured evidence manifests
and runs ``applicability.build`` for BOE-A-2025-26847 → BOE-A-2017-14334.
No network, no LLM, no OCR. Asserts the preregistered §23 tests plus the
D1–D11 acceptance cases against persisted rows — the frozen discovery
JSONs are used only as oracle values, never read by the runtime.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from regdelta import applicability, db as dbm, history, rawstore  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402

MODIFIER = "BOE-A-2025-26847"
TARGET = "BOE-A-2017-14334"
MANIFESTS = [
    ROOT / "evidence" / "g0c" / "raw" / "manifest.json",
    ROOT / "evidence" / "g0c1" / "raw" / "manifest.json",
    ROOT / "evidence" / "g0c2" / "raw" / "manifest.json",
]

pytestmark = pytest.mark.skipif(
    not all(m.exists() for m in MANIFESTS),
    reason="G0-C evidence not generated",
)

_BY_URL: dict[str, dict] = {}
if all(m.exists() for m in MANIFESTS):
    for mp in MANIFESTS:
        for e in json.loads(mp.read_text(encoding="utf-8"))["entries"].values():
            _BY_URL[e["url"]] = e


def _fetch(url: str, accept: str) -> FetchResult:
    e = _BY_URL.get(url)
    if e is None:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in captured evidence",
                           via=EVIDENCE_IMPORT)
    return FetchResult(url, 200, "application/octet-stream",
                       (ROOT / e["path"]).read_bytes(), None, None,
                       via=EVIDENCE_IMPORT)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("g0d")
    conn = dbm.connect(data_dir / "regdelta.sqlite")
    conn.row_factory = sqlite3.Row
    history.reconstruct(conn, data_dir, TARGET, _fetch)
    conn.commit()
    report = applicability.build(conn, data_dir, MODIFIER, TARGET)
    conn.commit()
    yield conn, data_dir, report
    conn.close()


def _clause(conn, key) -> dict | None:
    r = conn.execute(
        "SELECT * FROM applicability_clauses WHERE clause_key=?",
        (key,)).fetchone()
    return dict(r) if r else None


def _effects(conn, clause_key) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT e.* FROM applicability_effects e
           JOIN applicability_clauses c ON c.clause_id = e.clause_id
           WHERE c.clause_key=?""", (clause_key,))]


def _targets(conn, clause_key) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT t.* FROM applicability_targets t
           JOIN applicability_clauses c ON c.clause_id = t.clause_id
           WHERE c.clause_key=?""", (clause_key,))]


def _relation_ids(conn, locator_key) -> list[str]:
    return [r[0] for r in conn.execute(
        """SELECT mr.relation_id FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           JOIN instruments i
             ON i.instrument_id = mr.modifier_instrument_id
           WHERE s.locator_key=? AND i.boe_id=?""",
        (locator_key, MODIFIER))]


# ---------------------------------------------------------------------------
# migration: effective_date -> instrument_effective_date
# ---------------------------------------------------------------------------


def test_migration_effective_date_to_instrument_effective_date_preserves_rows(
        tmp_path):
    """A realistic old-schema DB migrates losslessly: same rows, same ids,
    NULLs preserved; reopening is idempotent."""
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    old_schema = dbm.SCHEMA.replace("instrument_effective_date",
                                    "effective_date")
    assert "instrument_effective_date" not in old_schema
    conn.executescript(old_schema)
    conn.execute(
        "INSERT INTO instruments (instrument_id, boe_id, titulo, origin)"
        " VALUES (?,?,?,?)", ("i" * 64, "BOE-X-1", "t", "REFERENCED"))
    conn.execute(
        "INSERT INTO subjects (subject_id, instrument_id, locator_key,"
        " label, subject_kind) VALUES (?,?,?,?,?)",
        ("s" * 64, "i" * 64, "norma:1", "n", "NORMA"))
    rows = [
        ("a" * 64, "MODIFICATION", "SUBSTITUTE", "s" * 64, "i" * 64,
         "apartado 1", None, None, None, "2025-01-01", "2025-02-01",
         None, "[]", "RESOLVED", None, "[]", "p", "v"),
        ("b" * 64, "CORRECTION", "CORRECT", "s" * 64, "i" * 64,
         "apartado 2", None, None, None, "2025-01-01", None,
         None, "[]", "PARTIAL", None, "[]", "p", "v"),
    ]
    conn.executemany(
        "INSERT INTO modification_relations (relation_id, kind,"
        " operation_kind, target_subject_id, modifier_instrument_id,"
        " locator_raw, relation_raw, before_representation_id,"
        " after_representation_id, publication_date, effective_date,"
        " declared_literals, diff_levels, resolution, resolution_notes,"
        " source_snapshot_ids, parser_name, parser_version)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    migrated = dbm.connect(path)
    cols = [r[1] for r in migrated.execute(
        "PRAGMA table_info(modification_relations)")]
    assert "instrument_effective_date" in cols
    assert "effective_date" not in cols
    out = migrated.execute(
        """SELECT relation_id, kind, operation_kind, target_subject_id,
                  modifier_instrument_id, locator_raw, relation_raw,
                  before_representation_id, after_representation_id,
                  publication_date, instrument_effective_date,
                  declared_literals, diff_levels, resolution,
                  resolution_notes, source_snapshot_ids, parser_name,
                  parser_version
           FROM modification_relations ORDER BY relation_id""").fetchall()
    assert [tuple(r) for r in out] == sorted(tuple(r) for r in rows)
    assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
    migrated.close()

    # reopening an already-migrated DB is a no-op, repeatedly
    for _ in range(2):
        again = dbm.connect(path)
        assert again.execute(
            "SELECT COUNT(*) FROM modification_relations"
        ).fetchone()[0] == 2
        again.close()


# ---------------------------------------------------------------------------
# counts, epistemic, taxonomy
# ---------------------------------------------------------------------------


def test_clause_count_26(built):
    conn, _, _ = built
    assert conn.execute(
        "SELECT COUNT(*) FROM applicability_clauses").fetchone()[0] == 26


def test_epistemic_22_observed_4_derived(built):
    conn, _, _ = built
    dist = dict(conn.execute(
        "SELECT epistemic, COUNT(*) FROM applicability_clauses"
        " GROUP BY epistemic").fetchall())
    assert dist == {"OBSERVED": 22, "DERIVED": 4}


def test_no_inferred_can_be_persisted(built):
    conn, _, _ = built
    iid = conn.execute(
        "SELECT instrument_id FROM instruments WHERE boe_id=?",
        (MODIFIER,)).fetchone()[0]
    snap = conn.execute(
        "SELECT source_snapshot_id FROM applicability_clauses LIMIT 1"
    ).fetchone()[0]
    conn.execute("SAVEPOINT sp_inferred")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO applicability_clauses
                   (clause_id, declaring_instrument_id, clause_key,
                    modality, evidence_text, evidence_locator, epistemic,
                    source_snapshot_id, parser_name, parser_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                ("f" * 64, iid, "test:inferred", "DECLARED_RULE", "x",
                 "{}", "INFERRED", snap, "t", "v"))
        cid = conn.execute(
            "SELECT clause_id FROM applicability_clauses LIMIT 1"
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO applicability_effects
                   (effect_id, clause_id, temporal_effect,
                    evidence_locator, epistemic, parser_name,
                    parser_version)
                   VALUES (?,?,?,?,?,?,?)""",
                ("e" * 64, cid, "APPLY_FROM", "{}", "INFERRED", "t", "v"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO applicability_targets
                   (target_id, clause_id, target_kind,
                    target_instrument_id, binding_method,
                    binding_evidence, source_snapshot_ids, epistemic)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("g" * 64, cid, "INSTRUMENT", iid, "INSTRUMENT_SCOPE",
                 "{}", "[]", "INFERRED"))
    finally:
        conn.execute("ROLLBACK TO sp_inferred")
        conn.execute("RELEASE sp_inferred")


def test_taxonomies_closed(built):
    conn, _, _ = built
    effs = {r[0] for r in conn.execute(
        "SELECT DISTINCT temporal_effect FROM applicability_effects")}
    assert effs <= {
        "INSTRUMENT_EFFECTIVE_FROM", "APPLY_FROM", "FIRST_REFERENCE_DATE",
        "LAST_REFERENCE_DATE", "RETROACTIVE_APPLICATION",
        "INITIAL_APPLICATION_DATE", "PROSPECTIVE_APPLICATION",
        "SCOPE_PERIOD"}
    assert len(effs) == 8
    mods = {r[0] for r in conn.execute(
        "SELECT DISTINCT modality FROM applicability_clauses")}
    assert mods == {"DECLARED_RULE", "OBLIGATION", "OPTION",
                    "ABSENCE_OF_OBLIGATION", "NON_APPLICATION"}
    rels = {r[0] for r in conn.execute(
        """SELECT DISTINCT relation_to_parent FROM applicability_clauses
           WHERE relation_to_parent IS NOT NULL""")}
    assert rels <= {"PART_OF", "EXCEPTION", "ALTERNATIVE", "QUALIFIER"}


# ---------------------------------------------------------------------------
# clause tree
# ---------------------------------------------------------------------------


def _parentage(conn) -> dict:
    rows = conn.execute(
        "SELECT clause_id, clause_key, parent_clause_id,"
        " relation_to_parent FROM applicability_clauses").fetchall()
    keys = {r["clause_key"]: (r["clause_id"], r["parent_clause_id"],
                             r["relation_to_parent"]) for r in rows}
    id2key = {v[0]: k for k, v in keys.items()}

    def parent(key):
        cid, pid, rel = keys[key]
        return id2key.get(pid), rel

    return keys, parent


def test_clause_tree_parentage(built):
    conn, _, _ = built
    keys, parent = _parentage(conn)
    # roots carry no fake BASE edge
    for key in ("dt1:1:s1", "dt2:1:s1", "dt3:único:s1", "dfu:base:s1"):
        cid, pid, rel = keys[key]
        assert pid is None and rel is None
    assert parent("dt1:2:s1") == ("dt1:1:s2", "EXCEPTION")
    assert parent("dt1:2:s2") == ("dt1:2:s1", "QUALIFIER")
    assert parent("dt1:4:s1") == ("dt1:1:s2", "EXCEPTION")
    assert parent("dt1:4:s2") == ("dt1:4:s1", "ALTERNATIVE")
    assert parent("dt2:2:s1") == ("dt2:1:s2", "EXCEPTION")
    assert parent("dt2:2:s2") == ("dt2:2:s1", "QUALIFIER")
    assert parent("dfu:e:s1:carveout") == ("dfu:e:s1", "EXCEPTION")
    for letter in "abcdef":
        pk, rel = parent(f"dfu:{letter}:s1")
        assert pk == "dfu:base:s1" and rel == "EXCEPTION"


def test_instrument_scope_not_duplicated_per_relation(built):
    conn, _, _ = built
    assert conn.execute(
        """SELECT COUNT(*) FROM applicability_targets
           WHERE target_kind='INSTRUMENT'""").fetchone()[0] == 1


def test_inherited_target_not_persisted_as_direct(built):
    """A clause inheriting scope through its parent must not fabricate
    direct target rows re-naming the parent's relations; the query layer
    distinguishes DIRECT from INHERITED."""
    conn, _, _ = built
    # neither the exception option nor the conditioned consequences nor
    # the carveout cite own subjects → zero fabricated target rows
    for key in ("dt1:2:s1", "dt1:2:s2", "dt2:2:s2",
                "dfu:e:s1:carveout"):
        assert _targets(conn, key) == []
    # the retroactive base cites its subjects → direct bindings
    assert _targets(conn, "dt1:1:s2") != []

    rid = _relation_ids(conn, "norma:31.apartado:3")[0]
    out = applicability.applicability_for_relation(conn, rid)

    def walk(node):
        yield node
        for ch in node["children"]:
            yield from walk(ch)

    origins = {n["clause"]["clause_key"]: n["target_origin"]
               for tr in out["specific_clause_trees"] for n in walk(tr)}
    assert origins["dt1:1:s2"] == "DIRECT"
    assert origins["dt1:2:s2"] == "INHERITED"


# ---------------------------------------------------------------------------
# query tree scoping (G0-D.R)
# ---------------------------------------------------------------------------


def _tree_keys(node):
    yield node["clause"]["clause_key"], node["target_origin"]
    for ch in node["children"]:
        yield from _tree_keys(ch)


def _all_keys(out):
    return {k for tr in out["specific_clause_trees"]
            for k, _ in _tree_keys(tr)}


def test_sibling_exclusion_in_specific_tree(built):
    """norma:22.apartado:2 binds only to dfu:b:s1 — the dfu tree must not
    surface siblings dfu:a/c/d/e/f as inherited applicability."""
    conn, _, _ = built
    rid = _relation_ids(conn, "norma:22.apartado:2")[0]
    out = applicability.applicability_for_relation(conn, rid)
    dfu_trees = [tr for tr in out["specific_clause_trees"]
                 if tr["clause"]["clause_key"] == "dfu:base:s1"]
    assert len(dfu_trees) == 1
    seen = dict(_tree_keys(dfu_trees[0]))
    assert seen["dfu:b:s1"] == "DIRECT"
    for letter in "acdef":
        assert f"dfu:{letter}:s1" not in seen
    assert "dfu:e:s1:carveout" not in seen


def test_descendant_inheritance_kept(built):
    """Targetless juridical dependents of a bound clause stay INHERITED —
    scoping must prune foreign-targeted siblings, not real children."""
    conn, _, _ = built
    rid = _relation_ids(conn, "norma:31.apartado:3")[0]
    out = applicability.applicability_for_relation(conn, rid)
    nodes = {k: o for tr in out["specific_clause_trees"]
             for k, o in _tree_keys(tr)}
    assert nodes["dt1:1:s2"] == "DIRECT"
    for key in ("dt1:2:s1", "dt1:2:s2", "dt1:3:s1", "dt1:4:s1",
                "dt1:4:s2", "dt1:6:s1", "dt1:1:s3"):
        assert nodes.get(key) == "INHERITED", key
    # dt1:5:s1 carries its own target (norma:60.apartado:56) — for this
    # relation it is a foreign-targeted branch, not inherited scope
    assert "dt1:5:s1" not in nodes


def test_bound_descendant_under_foreign_targeted_ancestor(built):
    """dt1:5:s1 binds norma:60.apartado:56 but sits under dt1:1:s2, which
    targets other relations — the query must still surface it, re-rooted
    at its highest targetless ancestor (the option clause dt1:2:s1)."""
    conn, _, _ = built
    rid = _relation_ids(conn, "norma:60.apartado:56")[0]
    out = applicability.applicability_for_relation(conn, rid)
    assert out["classification"] == "SPECIFIC_BOUND"
    trees = {tr["clause"]["clause_key"]: tr
             for tr in out["specific_clause_trees"]}
    node = trees["dt1:2:s1"]
    kids = dict(_tree_keys(node))
    assert kids["dt1:5:s1"] == "DIRECT"


def test_sibling_targeted_elsewhere_excluded(built):
    """Two siblings bound to different relations: each query contains its
    own clause and excludes the other's."""
    conn, _, _ = built
    rid_a = _relation_ids(conn, "norma:19.apartado:10")[0]  # dfu:a
    rid_b = _relation_ids(conn, "norma:22.apartado:2")[0]   # dfu:b
    keys_a = _all_keys(applicability.applicability_for_relation(conn, rid_a))
    keys_b = _all_keys(applicability.applicability_for_relation(conn, rid_b))
    assert "dfu:a:s1" in keys_a and "dfu:b:s1" not in keys_a
    assert "dfu:b:s1" in keys_b and "dfu:a:s1" not in keys_b


def test_instrument_rules_exclude_specific_branches(built):
    """GENERAL_ONLY relation: instrument_rules carries the entry-into-
    force rule, never the specific dfu:a–f branches."""
    conn, _, _ = built
    rid = _relation_ids(conn, "norma:18.apartado:4")[0]
    out = applicability.applicability_for_relation(conn, rid)
    assert out["classification"] == "GENERAL_ONLY"
    assert out["instrument_rules"]
    keys = {k for n in out["instrument_rules"] for k, _ in _tree_keys(n)}
    assert "dfu:base:s1" in keys
    for letter in "abcdef":
        assert f"dfu:{letter}:s1" not in keys
    effs = [e for n in out["instrument_rules"]
            for e in _all_effects(n)]
    assert any(e["temporal_effect"] == "INSTRUMENT_EFFECTIVE_FROM"
               and e["date_value"] == "2025-12-30" for e in effs)


def _all_effects(node):
    effs = list(node["effects"])
    for ch in node["children"]:
        effs += _all_effects(ch)
    return effs


def test_anomaly_scoped_to_modifier_target(built):
    """An unbound anomaly for a different modifier/target pair must not
    flip this relation to SPECIFIC_EXPECTED_BUT_UNBOUND."""
    conn, _, _ = built
    rid = _relation_ids(conn, "norma:18.apartado:4")[0]
    key = "norma:18.apartado:4"
    snap = conn.execute(
        "SELECT snapshot_id FROM source_snapshots LIMIT 1").fetchone()[0]
    assert applicability.applicability_for_relation(
        conn, rid)["classification"] == "GENERAL_ONLY"
    conn.execute("SAVEPOINT sp_iso")
    try:
        # foreign pair, same locator_key — must be ignored
        conn.execute(
            """INSERT INTO anomalies
               (anomaly_id, kind, snapshot_id, detail, detected_at)
               VALUES (?,?,?,?,?)""",
            ("f" * 64, applicability.ANOMALY_TARGET_UNBOUND, snap,
             json.dumps({"clause_key": "x", "locator_key": key,
                         "modifier": "BOE-A-9999-1",
                         "target": "BOE-A-9999-2", "raw": key}), "t"))
        assert applicability.applicability_for_relation(
            conn, rid)["classification"] == "GENERAL_ONLY"
        # same modifier+target+locator — flips
        conn.execute(
            """INSERT INTO anomalies
               (anomaly_id, kind, snapshot_id, detail, detected_at)
               VALUES (?,?,?,?,?)""",
            ("e" * 64, applicability.ANOMALY_TARGET_UNBOUND, snap,
             json.dumps({"clause_key": "x", "locator_key": key,
                         "modifier": MODIFIER, "target": TARGET,
                         "raw": key}), "t"))
        assert applicability.applicability_for_relation(
            conn, rid)["classification"] == \
            "SPECIFIC_EXPECTED_BUT_UNBOUND"
    finally:
        conn.execute("ROLLBACK TO sp_iso")
        conn.execute("RELEASE sp_iso")


# ---------------------------------------------------------------------------
# target classification
# ---------------------------------------------------------------------------


def test_target_classification_53_0_16_0(built):
    conn, _, report = built
    expected = {"SPECIFIC_BOUND": 53, "SPECIFIC_EXPECTED_BUT_UNBOUND": 0,
                "GENERAL_ONLY": 16, "NOT_APPLICABLE": 0}
    assert report["classification"] == expected
    mod_iid = conn.execute(
        "SELECT instrument_id FROM instruments WHERE boe_id=?",
        (MODIFIER,)).fetchone()[0]
    tgt_iid = conn.execute(
        "SELECT instrument_id FROM instruments WHERE boe_id=?",
        (TARGET,)).fetchone()[0]
    assert applicability.classify(conn, mod_iid, tgt_iid) == expected


def test_unbound_explicit_target_creates_anomaly_not_general_only(built):
    """Mechanism test: a cited-but-unbindable locator surfaces as
    SPECIFIC_EXPECTED_BUT_UNBOUND + anomaly, never GENERAL_ONLY."""
    conn, _, _ = built
    rid, key = conn.execute(
        """SELECT mr.relation_id, s.locator_key
           FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           JOIN instruments i
             ON i.instrument_id = mr.modifier_instrument_id
           WHERE i.boe_id=? AND NOT EXISTS(
             SELECT 1 FROM applicability_targets t
             WHERE t.modification_relation_id = mr.relation_id)
           LIMIT 1""", (MODIFIER,)).fetchone()
    assert applicability.applicability_for_relation(
        conn, rid)["classification"] == "GENERAL_ONLY"
    snap = conn.execute(
        "SELECT snapshot_id FROM source_snapshots LIMIT 1").fetchone()[0]
    conn.execute("SAVEPOINT sp_unbound")
    try:
        conn.execute(
            """INSERT INTO anomalies
               (anomaly_id, kind, snapshot_id, detail, detected_at)
               VALUES (?,?,?,?,?)""",
            ("u" * 64, applicability.ANOMALY_TARGET_UNBOUND, snap,
             json.dumps({"clause_key": "x", "locator_key": key,
                         "modifier": MODIFIER, "target": TARGET,
                         "raw": key}), "t"))
        assert applicability.applicability_for_relation(
            conn, rid)["classification"] == \
            "SPECIFIC_EXPECTED_BUT_UNBOUND"
    finally:
        conn.execute("ROLLBACK TO sp_unbound")
        conn.execute("RELEASE sp_unbound")
    assert applicability.applicability_for_relation(
        conn, rid)["classification"] == "GENERAL_ONLY"


def test_build_persists_unbound_target_anomaly(built):
    """End-to-end: when a cited locator loses its relation, build must
    persist an APPLICABILITY_TARGET_UNBOUND anomaly — not crash, not
    degrade silently."""
    conn, data_dir, _ = built
    key = "norma:31.apartado:3"
    rids = _relation_ids(conn, key)
    assert rids
    conn.execute("SAVEPOINT sp_unbound_build")
    try:
        ph = ",".join("?" * len(rids))
        conn.execute(
            "DELETE FROM applicability_targets"
            f" WHERE modification_relation_id IN ({ph})", rids)
        conn.execute(
            "DELETE FROM modification_relations"
            f" WHERE relation_id IN ({ph})", rids)
        applicability.build(conn, data_dir, MODIFIER, TARGET)
        anoms = [json.loads(r[0]) for r in conn.execute(
            "SELECT detail FROM anomalies WHERE kind=?",
            (applicability.ANOMALY_TARGET_UNBOUND,))]
        assert any(a["locator_key"] == key and a["modifier"] == MODIFIER
                   and a["target"] == TARGET for a in anoms)
    finally:
        conn.execute("ROLLBACK TO sp_unbound_build")
        conn.execute("RELEASE sp_unbound_build")


# ---------------------------------------------------------------------------
# frequency provenance (D3–D5 mechanism)
# ---------------------------------------------------------------------------


def _freq_targets(conn, periodicity) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT t.*, c.clause_key FROM applicability_targets t
           JOIN applicability_clauses c ON c.clause_id = t.clause_id
           WHERE t.binding_method='DECLARED_FREQUENCY'
             AND json_extract(t.binding_evidence,'$.periodicity')=?""",
        (periodicity,))]


def _assert_freq_chain(conn, periodicity, expected_date):
    """relation → target subject → official periodicity evidence →
    conditioned FIRST_REFERENCE_DATE effect."""
    rows = _freq_targets(conn, periodicity)
    assert rows, f"no DECLARED_FREQUENCY target with {periodicity}"
    for t in rows:
        ev = json.loads(t["binding_evidence"])
        assert ev["periodicity"] == periodicity
        assert "node_index" in ev["frequency_table"]
        snaps = json.loads(t["source_snapshot_ids"])
        assert len(snaps) == 2  # modifier + target snapshots
        for s in snaps:
            assert conn.execute(
                "SELECT blob_sha256 FROM source_snapshots"
                " WHERE snapshot_id=?", (s,)).fetchone()
        assert t["modification_relation_id"]
    clause_key = rows[0]["clause_key"]
    hits = [e for e in _effects(conn, clause_key)
            if e["temporal_effect"] == "FIRST_REFERENCE_DATE"
            and e["date_value"] == expected_date
            and periodicity in json.loads(
                e["condition_normalized"] or "{}").get(
                    "frequency_in", [])]
    assert hits, f"{periodicity}: no conditioned {expected_date} effect"


def test_monthly_frequency_provenance(built):
    conn, _, _ = built
    _assert_freq_chain(conn, "MONTHLY", "2026-03-31")


def test_semiannual_frequency_provenance(built):
    """SEMIANNUAL is declared by the official norma-67 table (FI 160-162)
    and conditions the 2026-06-30 FIRST_REFERENCE_DATE effect; the chain
    resolves to the target snapshot/blob even though no bound relation
    happens to be semiannual in this corpus."""
    conn, data_dir, _ = built
    effs = _effects(conn, "dfu:e:s1")
    semi = [e for e in effs
            if e["temporal_effect"] == "FIRST_REFERENCE_DATE"
            and e["date_value"] == "2026-06-30"
            and "SEMIANNUAL" in json.loads(
                e["condition_normalized"] or "{}").get(
                    "frequency_in", [])]
    assert semi
    # every DECLARED_FREQUENCY target's evidence resolves to both
    # snapshots and the official table node
    for t in _freq_targets(conn, "QUARTERLY") + _freq_targets(
            conn, "MONTHLY"):
        ev = json.loads(t["binding_evidence"])
        assert ev["frequency_table"]["source"] == "norma 67 table"
        tgt_snap = json.loads(t["source_snapshot_ids"])[1]
        sha = conn.execute(
            "SELECT blob_sha256 FROM source_snapshots"
            " WHERE snapshot_id=?", (tgt_snap,)).fetchone()[0]
        assert rawstore.blob_path(data_dir, sha).exists()


def test_annual_frequency_provenance(built):
    conn, _, _ = built
    effs = _effects(conn, "dfu:e:s1")
    assert any(e["temporal_effect"] == "FIRST_REFERENCE_DATE"
               and e["date_value"] == "2026-12-31"
               and "ANNUAL" in json.loads(
                   e["condition_normalized"] or "{}").get(
                       "frequency_in", []) for e in effs)


# ---------------------------------------------------------------------------
# D1–D11 acceptance
# ---------------------------------------------------------------------------


def test_d1_general_entry_into_force(built):
    conn, _, _ = built
    effs = _effects(conn, "dfu:base:s1")
    e = [x for x in effs
         if x["temporal_effect"] == "INSTRUMENT_EFFECTIVE_FROM"]
    assert len(e) == 1
    assert e[0]["date_value"] == "2025-12-30"
    assert e[0]["epistemic"] == "DERIVED"
    t = _targets(conn, "dfu:base:s1")
    assert len(t) == 1 and t[0]["target_kind"] == "INSTRUMENT"
    assert t[0]["binding_method"] == "INSTRUMENT_SCOPE"


def test_d2_apply_from_distinct(built):
    conn, _, _ = built
    for letter in "abcd":
        effs = _effects(conn, f"dfu:{letter}:s1")
        assert any(e["temporal_effect"] == "APPLY_FROM"
                   and e["date_value"] == "2026-01-01" for e in effs)


def test_d3_monthly_quarterly_first_reference(built):
    conn, _, _ = built
    _assert_freq_chain(conn, "MONTHLY", "2026-03-31")
    _assert_freq_chain(conn, "QUARTERLY", "2026-03-31")


def test_d4_semiannual_first_reference(built):
    test_semiannual_frequency_provenance(built)


def test_d5_annual_first_reference(built):
    test_annual_frequency_provenance(built)


def test_d6_riesgo_pais(built):
    """riesgo-país: dfu:f via marker paths p/vii+p/viii → anejo 9
    punto 132 / apartado IV → FIRST_REFERENCE_DATE 2026-06-30."""
    conn, _, _ = built
    effs = _effects(conn, "dfu:f:s1")
    assert any(e["temporal_effect"] == "FIRST_REFERENCE_DATE"
               and e["date_value"] == "2026-06-30" for e in effs)
    evs = [json.loads(t["binding_evidence"])
           for t in _targets(conn, "dfu:f:s1")]
    keys = {e["locator_key"] for e in evs}
    assert {"anejo:9.apartado:IV", "anejo:9.punto:132"} <= keys
    paths = {p for e in evs for p in e.get("paths", [])}
    assert {"p/vii", "p/viii"} & paths


def test_d7_last_reference_fi131_fi141(built):
    conn, _, _ = built
    effs = _effects(conn, "dt3:único:s1")
    assert any(e["temporal_effect"] == "LAST_REFERENCE_DATE"
               and e["date_value"] == "2026-06-30" for e in effs)
    targets = {json.loads(t["binding_evidence"]).get("locator_key")
               for t in _targets(conn, "dt3:único:s1")}
    assert {"estado:FI 131", "estado:FI 141"} <= targets
    # coexists with dfu:e through the sin-perjuicio EXCEPTION edge
    keys, parent = _parentage(conn)
    assert parent("dfu:e:s1:carveout") == ("dfu:e:s1", "EXCEPTION")


def test_first_and_last_reference_coexist(built):
    """FI 131 / FI 141 relations expose FIRST and LAST reference dates
    simultaneously — never collapsed to one."""
    conn, _, _ = built

    def all_effects(node):
        effs = list(node["effects"])
        for ch in node["children"]:
            effs += all_effects(ch)
        return effs

    for loc in ("estado:FI 131", "estado:FI 141"):
        rid = _relation_ids(conn, loc)[0]
        out = applicability.applicability_for_relation(conn, rid)
        assert out["classification"] == "SPECIFIC_BOUND"
        effs = [e for tr in out["specific_clause_trees"]
                for e in all_effects(tr)]
        kinds = {e["temporal_effect"] for e in effs}
        assert "FIRST_REFERENCE_DATE" in kinds
        assert "LAST_REFERENCE_DATE" in kinds


def test_d8_retroactivity_not_replaced_by_date(built):
    conn, _, _ = built
    assert any(e["temporal_effect"] == "RETROACTIVE_APPLICATION"
               and e["date_value"] is None
               for e in _effects(conn, "dt1:1:s2"))
    assert any(e["temporal_effect"] == "INITIAL_APPLICATION_DATE"
               and e["date_value"] == "2026-01-01"
               for e in _effects(conn, "dt1:1:s3"))


def test_d9_absence_of_obligation_is_not_option(built):
    conn, _, _ = built
    c = _clause(conn, "dt1:2:s1")
    assert c["modality"] == "ABSENCE_OF_OBLIGATION"
    assert "no estará obligada a reexpresar" in c["evidence_text"]
    assert c["relation_to_parent"] == "EXCEPTION"


def test_d10_conditioned_consequence_is_qualifier(built):
    conn, _, _ = built
    keys, parent = _parentage(conn)
    assert parent("dt1:2:s2") == ("dt1:2:s1", "QUALIFIER")
    c = _clause(conn, "dt1:2:s2")
    text = (c["condition_raw"] or "") + " " + c["evidence_text"]
    assert "Si optara por no reexpresarla" in text


def test_retroactive_option_consequence_tree(built):
    """dt1: SCOPE_PERIOD root → RETROACTIVE child → EXCEPTION option
    (ABSENCE_OF_OBLIGATION) → QUALIFIER conditioned consequence."""
    conn, _, _ = built
    rid = _relation_ids(conn, "norma:31.apartado:3")[0]
    out = applicability.applicability_for_relation(conn, rid)

    def find(node, pred, path=()):
        if pred(node):
            return path + (node,)
        for ch in node["children"]:
            r = find(ch, pred, path + (node,))
            if r:
                return r
        return None

    found = None
    for tr in out["specific_clause_trees"]:
        r = find(tr, lambda n: n["clause"]["clause_key"] == "dt1:2:s2")
        if r:
            found = r
            break
    assert found is not None
    keys = [n["clause"]["clause_key"] for n in found]
    assert keys[:2] == ["dt1:1:s1", "dt1:1:s2"]
    assert keys[-2:] == ["dt1:2:s1", "dt1:2:s2"]
    assert "RETROACTIVE_APPLICATION" in {
        e["temporal_effect"] for e in found[1]["effects"]}
    assert found[-2]["clause"]["modality"] == "ABSENCE_OF_OBLIGATION"


def test_dt2_not_hardcoded_to_dt1(built):
    conn, _, _ = built
    assert any(e["temporal_effect"] == "RETROACTIVE_APPLICATION"
               for e in _effects(conn, "dt2:1:s2"))
    keys, parent = _parentage(conn)
    assert parent("dt2:2:s1") == ("dt2:1:s2", "EXCEPTION")
    assert parent("dt2:2:s2") == ("dt2:2:s1", "QUALIFIER")


def test_d11_second_transitoria_full_shape(built):
    conn, _, _ = built
    for key in ("dt2:1:s1", "dt2:1:s2", "dt2:2:s1", "dt2:2:s2",
                "dt2:3:s1", "dt2:4:s1", "dt2:5:s1"):
        assert _clause(conn, key) is not None


# ---------------------------------------------------------------------------
# auditability + determinism
# ---------------------------------------------------------------------------


def test_all_clauses_resolve_to_snapshot_blob_sha(built):
    conn, data_dir, _ = built
    rows = conn.execute(
        """SELECT c.clause_id, c.evidence_text, c.evidence_locator,
                  s.blob_sha256
           FROM applicability_clauses c
           JOIN source_snapshots s
             ON s.snapshot_id = c.source_snapshot_id""").fetchall()
    assert len(rows) == 26
    for cid, text, loc, sha in rows:
        assert text and loc
        json.loads(loc)
        blob = rawstore.blob_path(data_dir, sha)
        assert blob.exists()
        assert hashlib.sha256(blob.read_bytes()).hexdigest() == sha


def test_all_effects_resolve_to_clause_evidence(built):
    conn, _, _ = built
    assert conn.execute(
        """SELECT COUNT(*) FROM applicability_effects e
           LEFT JOIN applicability_clauses c ON c.clause_id = e.clause_id
           WHERE c.clause_id IS NULL""").fetchone()[0] == 0
    assert conn.execute(
        """SELECT COUNT(*) FROM applicability_effects e
           JOIN applicability_clauses c ON c.clause_id = e.clause_id
           WHERE c.evidence_text IS NULL OR c.evidence_text=''
              OR e.evidence_locator IS NULL""").fetchone()[0] == 0


def test_all_targets_resolve_to_relation_or_instrument(built):
    conn, _, _ = built
    assert conn.execute(
        """SELECT COUNT(*) FROM applicability_targets t
           LEFT JOIN instruments i
             ON i.instrument_id = t.target_instrument_id
           LEFT JOIN modification_relations mr
             ON mr.relation_id = t.modification_relation_id
           WHERE i.instrument_id IS NULL AND mr.relation_id IS NULL"""
    ).fetchone()[0] == 0
    assert conn.execute(
        """SELECT COUNT(*) FROM applicability_targets
           WHERE target_instrument_id IS NOT NULL
             AND modification_relation_id IS NOT NULL""").fetchone()[0] == 0


def test_same_input_rerun_is_idempotent(built):
    conn, data_dir, _ = built
    before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("applicability_clauses", "applicability_effects",
                        "applicability_targets", "anomalies")}
    out = applicability.build(conn, data_dir, MODIFIER, TARGET)
    conn.commit()
    assert out["clauses_inserted"] == 0
    assert out["effects_inserted"] == 0
    assert out["targets_inserted"] == 0
    after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in before}
    assert after == before


def test_g0c_counts_unchanged(built):
    # G1_INTENTIONAL_SEMANTIC_CHANGE (G1.1 §40):
    #   old counts: representations=335, RESOLVED=182, PARTIAL=93,
    #     UNRESOLVED=17, non-applicability anomalies=23.
    #   why changed: the proof-or-abstain binder no longer persists
    #     first-hit/global-fallback representations, so 15 bindings
    #     that could not be structurally proven are abstained
    #     (320 representations); every declared operation still emits a
    #     relation (292 unchanged); resolution shifts honestly toward
    #     UNRESOLVED, and abstentions are recorded as generic
    #     BINDING_* / CHAIN_DISCONTINUITY anomalies.
    #   new fail-closed behavior: coverage sacrificed is exactly the
    #     set of relations whose proof says AMBIGUOUS / NOT_FOUND /
    #     NOT_PROVABLE — auditable via binding_proof.
    # G1_INTENTIONAL_SEMANTIC_CHANGE (G1.1 §32, second pass):
    #   representations 320 -> 189, UNRESOLVED 39 -> 123: the subject-
    #   scope rule now also abstains when the clause acts on an
    #   unmodelled sub-element (nota/párrafo/numeral/columna/dimensión
    #   inside the recorded subject) or on a differently-qualified
    #   entity ('norma N ter'), and the content-owner rule refuses
    #   following content governed by a different sub-clause. Every
    #   sampled abstention was verified honest — these clauses were the
    #   historical FALSE_FACT class.
    # G2.1_INTENTIONAL_SEMANTIC_CHANGE:
    #   subjects 221 -> 223 (enumerated estado codes the old parser
    #     collapsed), representations 189 -> 186 (the coverage gate now
    #     abstains on bound spans that cannot restate the subject
    #     locator), relations 292 unchanged, anomalies 448 -> 457
    #     (abstention events replace the removed OUT_OF_TARGET_OPS
    #     anomaly — foreign operations are journaled dispositions, not
    #     defects).
    # COV-2_INTENTIONAL_SEMANTIC_CHANGE (F1+F2):
    #   representations 186 -> 255, UNRESOLVED 126 -> 78: the before
    #   side of sub-scoped operations is no longer gated (F1 — the
    #   subject's prior representation is ordinary provable state),
    #   and tolerant structural marker enumeration resolves markers
    #   the strict patterns missed (F2 — undotted numerals, compound
    #   dotted codes, level-aware regions). Relations 292 unchanged —
    #   coverage grew, the factual surface did not shrink.
    conn, _, _ = built
    assert conn.execute(
        "SELECT COUNT(*) FROM subjects").fetchone()[0] == 223
    assert conn.execute(
        "SELECT COUNT(*) FROM representations").fetchone()[0] == 255
    assert conn.execute(
        "SELECT COUNT(*) FROM modification_relations").fetchone()[0] == 292
    dist = dict(conn.execute(
        "SELECT resolution, COUNT(*) FROM modification_relations"
        " GROUP BY resolution").fetchall())
    assert dist == {"RESOLVED": 110, "PARTIAL": 104, "UNRESOLVED": 78}
    kinds = dict(conn.execute(
        "SELECT kind, COUNT(*) FROM anomalies GROUP BY kind").fetchall())
    assert kinds.get(applicability.ANOMALY_TARGET_UNBOUND, 0) == 0
    # abstention anomalies explain the coverage loss
    assert sum(kinds.values()) == 361
    assert kinds["BINDING_NOT_FOUND"] == 40
    assert kinds["BINDING_NOT_PROVABLE"] == 198
    assert kinds["CHAIN_DISCONTINUITY"] == 43
    assert kinds["UNBOUND_SUBJECT"] == 78
    # G2.1: foreign-target abstentions are inventory dispositions, not
    # anomalies — this kind no longer exists in the ledger
    assert kinds.get("OUT_OF_TARGET_OPS", 0) == 0


def test_no_scalar_effective_date_answer(built):
    """The query API must not flatten to a single effective date."""
    conn, _, _ = built
    rid = _relation_ids(conn, "estado:FI 131")[0]
    out = applicability.applicability_for_relation(conn, rid)
    assert "effective_date" not in out
    assert isinstance(out["specific_clause_trees"], list)
    assert isinstance(out["instrument_rules"], list)
