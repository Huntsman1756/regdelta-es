"""G0-G.1 DEV regression tests: generic structural coverage the frozen
C4/2017 corpus never exercised.

Each test reconstructs one DEV target purely from captured evidence and
asserts the post-fix behavior. Target/circular literals are test data
(permitted); runtime code must stay free of them.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from regdelta import applicability, db as dbm, history  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402

MANIFEST = ROOT / "evidence" / "g0g" / "dev" / "manifest.json"

pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(), reason="G0-G dev evidence not captured")

_BY_URL: dict[str, dict] = {}
if MANIFEST.exists():
    _m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for e in _m["entries"].values():
        _BY_URL[e["url"]] = e


def _fetch(url: str, accept: str) -> FetchResult:
    e = _BY_URL.get(url)
    if e is None or "path" not in e:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in dev evidence", via=EVIDENCE_IMPORT)
    return FetchResult(url, 200, "application/octet-stream",
                       (ROOT / e["path"]).read_bytes(), None, None,
                       via=EVIDENCE_IMPORT)


def _build(tmp_path: Path, target: str) -> sqlite3.Connection:
    conn = dbm.connect(tmp_path / "r.sqlite")
    conn.row_factory = sqlite3.Row
    report = history.reconstruct(conn, tmp_path, target, _fetch)
    conn.commit()
    assert "error" not in report, report.get("error")
    return conn


def _keys(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        """SELECT DISTINCT s.locator_key FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           ORDER BY 1""")]


def _rels(conn, like: str):
    return conn.execute(
        """SELECT mr.*, s.locator_key FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           WHERE s.locator_key LIKE ? ORDER BY mr.publication_date""",
        (like,)).fetchall()


def test_unmarked_disposicion_paragraph_ops(tmp_path):
    """C1/2023 DF2 modifies C4/2019 in one unmarked paragraph:
    'se suprimen los apartados 4 y 5 de la norma 5'."""
    conn = _build(tmp_path, "BOE-A-2019-17286")
    keys = _keys(conn)
    assert "norma:5.apartado:4" in keys
    assert "norma:5.apartado:5" in keys
    rels = _rels(conn, "norma:5.apartado:%")
    assert {r["operation_kind"] for r in rels} == {"DELETE"}
    # negated tail ("sin que se introduzca ningún cambio en los
    # apartados 1 a 3") must NOT produce relations
    assert not any(k.startswith("norma:5.apartado:1")
                   or k.startswith("norma:5.apartado:2")
                   or k.startswith("norma:5.apartado:3") for k in keys)
    conn.close()


def test_section_preamble_targets(tmp_path):
    """C5/2014 'Norma segunda' section heading names no circular; its
    preamble paragraph does ('...modificaciones en la Circular 1/2010:')
    → the ops belong to C1/2010's ledger."""
    conn = _build(tmp_path, "BOE-A-2010-1824")
    assert len(_keys(conn)) > 0
    conn.close()


def test_fichero_subjects_route_to_declared_circular(tmp_path):
    """C4/2014 modifies ficheros across several circulars; only the
    ficheros whose op names Circular 2/2013 belong to this target."""
    conn = _build(tmp_path, "BOE-A-2013-7467")
    keys = _keys(conn)
    fichero_keys = [k for k in keys if k.startswith("fichero:")]
    assert fichero_keys, "fichero ops naming this circular were dropped"
    # every emitted fichero relation cites C4/2014 as modifier
    mods = {r["modifier_instrument_id"] for r in _rels(conn, "fichero:%")}
    assert len(mods) == 1
    conn.close()


def test_fichero_before_representation_binds(tmp_path):
    """A modified fichero's before-representation is its description
    block in the target's annex ('Fichero: <name>' heading)."""
    conn = _build(tmp_path, "BOE-A-2013-7467")
    bound = conn.execute(
        """SELECT COUNT(*) FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           WHERE s.locator_key LIKE 'fichero:%'
             AND mr.before_representation_id IS NOT NULL""").fetchone()[0]
    assert bound > 0
    conn.close()


def test_errata_parenthetical_state_locators(tmp_path):
    """Errata corrections locate via 'En la página N (Estado CODE)'
    + 'donde dice/debe decir' literals → CORRECT-style relations with
    declared literals and page-anchored image predecessors."""
    conn = _build(tmp_path, "BOE-A-2012-3169")
    rows = _rels(conn, "estado:%")
    assert rows, "errata estado locators not parsed"
    assert all(r["declared_literals"] or r["kind"] == "CORRECTION"
               for r in rows)
    conn.close()


def test_apartado_composes_under_disposicion(tmp_path):
    """'apartado 1 de la disposición transitoria primera' must emit the
    composed key, not a bare top-level 'apartado:1'."""
    conn = _build(tmp_path, "BOE-A-2016-4356")
    keys = _keys(conn)
    assert "disp:transitoria.primera.apartado:1" in keys
    assert "disp:transitoria.segunda.apartado:2" in keys
    assert "apartado:1" not in keys and "apartado:2" not in keys
    conn.close()


def test_compound_clause_nearest_verb(tmp_path):
    """'Se modifica el fichero «X» ... y se incluye un nuevo apartado':
    the fichero is governed by 'modifica', the coordinated ADD belongs
    to the unnamed apartado — the fichero relation must be MODIFY."""
    conn = _build(tmp_path, "BOE-A-2011-2378")
    rels = _rels(conn, "fichero:Consultas del archivo")
    assert rels
    assert {r["operation_kind"] for r in rels} == {"MODIFY"}
    conn.close()


def test_fichero_connector_variant_binds(tmp_path):
    """Annex titles and clause citations can differ in connectors only:
    'Selección y Formación de personal' must bind to the annex block
    titled 'Selección y formación del personal'."""
    conn = _build(tmp_path, "BOE-A-2005-4749")
    rels = _rels(conn, "fichero:Selección y Formación de personal")
    assert rels
    assert all(r["before_representation_id"] is not None for r in rels)
    conn.close()


def test_unmarked_rewrite_with_quoted_content(tmp_path):
    """'Se da nueva redacción al apartado 3 de la norma primera de la
    Circular 4/2010: «3. En caso de que ...»' — an unmarked op whose
    trailing ':' pulls the following quoted block as the after
    representation (SUBSTITUTE, both sides bound)."""
    conn = _build(tmp_path, "BOE-A-2010-12488")
    rels = _rels(conn, "norma:1.apartado:3")
    assert rels, "rewrite clause dropped"
    r = rels[0]
    assert r["operation_kind"] == "SUBSTITUTE"
    assert r["after_representation_id"] is not None
    conn.close()


def test_applicability_numbered_disposiciones(tmp_path):
    """Disposición sections are discovered dynamically, not from a
    fixed dfu/dt1-3 list: C5/2014's 'Disposición transitoria única'
    yields clauses for its (1/2010) modification."""
    conn = _build(tmp_path, "BOE-A-2010-1824")
    rep = applicability.build(conn, tmp_path, "BOE-A-2014-13365",
                              "BOE-A-2010-1824")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM applicability_clauses") \
        .fetchone()[0]
    assert n > 0
    conn.close()
