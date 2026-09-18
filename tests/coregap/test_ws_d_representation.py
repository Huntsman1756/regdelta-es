"""CORE-GAP WS-D: representation evidence.

EXP-D1 falsified byte-equality between the signed diario PDF and the
served /datos/imagenes/disp PNGs: the PDF embeds the annex figures as
vector content — there is no embedded raster stream to equate. The
outcome is REPRESENTATION_ASSOCIATION_ONLY:

  * the IMAGE representation identity is unchanged — locator keeps
    boe_page / img_alt / url / blob_sha256 of the official served
    asset;
  * the deterministic association to the authentic signed PDF
    (sha256 + /Pages index per bound page) is recorded as binding
    evidence — corroboration, never identity;
  * no claim of byte equality between the two channels is made.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import regdelta.profiles  # noqa: E402,F401
from regdelta import annexmap, history  # noqa: E402
from regdelta.profile import use_profile  # noqa: E402

use_profile("bde-circular")


class _Art:
    def __init__(self, snap, sha):
        self.snapshot_id = snap
        self.blob_sha256 = sha


class _Acq:
    def __init__(self):
        self.calls = []

    def get(self, kind, url, media, pname, pver, checked_at):
        self.calls.append((kind, url))
        return _Art(f"snap-{url[-12:]}", "a" * 64)


def _ctx(conn):
    ctx = history._Ctx(conn=conn, acquirer=_Acq(), checked_at="t")
    ctx.doc_images["BOE-X"] = [
        type("I", (), {"src": "/datos/imagenes/disp/x/1.png"})(),
        type("I", (), {"src": "/datos/imagenes/disp/x/2.png"})(),
    ]
    ctx.annex_pdf_sha["BOE-X"] = "f" * 64
    return ctx


def _amap():
    return annexmap.AnnexMap(
        pages=[
            annexmap.PageEntry(9, 100, "CONTENT", "FI 1", img_alt=1),
            annexmap.PageEntry(10, 101, "CONTENT", "FI 2", img_alt=2),
        ],
        img_by_page={100: 1, 101: 2},
        anchored=True,
    )


def _schema_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE representations (representation_id TEXT,"
        " subject_id TEXT, representation_kind TEXT, content_sha256"
        " TEXT, text_content TEXT, artifact_locator TEXT,"
        " source_snapshot_id TEXT, binding TEXT, binding_evidence"
        " TEXT, parser_name TEXT, parser_version TEXT)")
    return conn


def _insert(ctx):
    return history._image_representation(
        ctx, "sid", "BOE-X", [100, 101], _amap(), "ANCHORED_DERIVED",
        {"rule": "alt sequence"})


def test_pdf_anchor_recorded_as_evidence_not_identity():
    conn = _schema_conn()
    rid = _insert(_ctx(conn))
    row = conn.execute(
        "SELECT artifact_locator, binding_evidence FROM representations"
        " WHERE representation_id=?", (rid,)).fetchone()
    loc = json.loads(row[0])
    ev = json.loads(row[1])
    assert "pdf_sha256" not in json.dumps(loc)
    assert "pdf_page_index" not in json.dumps(loc)
    assert ev["pdf_anchor"]["sha256"] == "f" * 64
    assert ev["pdf_anchor"]["page_indexes"] == [9, 10]
    assert ev["pdf_anchor"]["relation"] == "ASSOCIATION_ONLY"


def test_association_is_deterministic():
    conn1, conn2 = _schema_conn(), _schema_conn()
    assert _insert(_ctx(conn1)) == _insert(_ctx(conn2))


def test_locator_identity_unchanged_by_pdf_anchor():
    """The pdf anchor lives in evidence only — the locator (which keys
    the representation id) must carry exactly the pre-WS-D fields."""
    conn = _schema_conn()
    rid = _insert(_ctx(conn))
    loc = json.loads(conn.execute(
        "SELECT artifact_locator FROM representations"
        " WHERE representation_id=?", (rid,)).fetchone()[0])
    assert set(loc) == {"instrument", "type", "pages"}
    assert all(set(p) == {"boe_page", "img_alt", "url", "blob_sha256"}
               for p in loc["pages"])
