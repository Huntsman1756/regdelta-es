from __future__ import annotations

import sqlite3
from unittest.mock import Mock

import pytest

from regdelta import applicability, rawstore
from regdelta.sources import boe_diario
from regdelta.util import sha256_hex


VALID_XML = b"""<documento>
<metadatos><identificador>synthetic-document</identificador>
<titulo> Synthetic title </titulo></metadatos>
<texto><p class="parrafo">First paragraph.</p><p>Second paragraph.</p></texto>
</documento>"""
SNAPSHOT_ID = "synthetic-snapshot"
BOE_ID = "synthetic-document"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE source_snapshots "
        "(snapshot_id TEXT PRIMARY KEY, blob_sha256 TEXT NOT NULL)"
    )
    try:
        yield connection
    finally:
        connection.close()


def register_snapshot(conn, digest):
    conn.execute(
        "INSERT INTO source_snapshots (snapshot_id, blob_sha256) VALUES (?, ?)",
        (SNAPSHOT_ID, digest),
    )


def test_corrupt_blob_rejected_before_parse(conn, tmp_path, monkeypatch):
    digest, path = rawstore.store_blob(tmp_path, VALID_XML)
    register_snapshot(conn, digest)
    path.write_bytes(VALID_XML.replace(b"First paragraph.", b"Changed paragraph."))
    parser = Mock(side_effect=AssertionError("parser must not be called"))
    monkeypatch.setattr(boe_diario, "parse_diario", parser)

    with pytest.raises(LookupError, match="SHA256 mismatch"):
        applicability._doc_from_snapshot(conn, tmp_path, SNAPSHOT_ID, BOE_ID)

    parser.assert_not_called()


def test_missing_snapshot_rejected_before_parse(conn, tmp_path, monkeypatch):
    parser = Mock(side_effect=AssertionError("parser must not be called"))
    monkeypatch.setattr(boe_diario, "parse_diario", parser)

    with pytest.raises(LookupError, match=f"snapshot {SNAPSHOT_ID} not in ledger"):
        applicability._doc_from_snapshot(conn, tmp_path, SNAPSHOT_ID, BOE_ID)

    parser.assert_not_called()


def test_missing_blob_rejected_before_parse(conn, tmp_path, monkeypatch):
    digest = sha256_hex(VALID_XML)
    register_snapshot(conn, digest)
    parser = Mock(side_effect=AssertionError("parser must not be called"))
    monkeypatch.setattr(boe_diario, "parse_diario", parser)

    with pytest.raises(LookupError, match=f"blob {digest} not stored under"):
        applicability._doc_from_snapshot(conn, tmp_path, SNAPSHOT_ID, BOE_ID)

    parser.assert_not_called()


@pytest.mark.parametrize("body", [b"<documento>", b"<documento />"])
def test_invalid_matching_hash_document_raises_lookup_error(
    conn, tmp_path, monkeypatch, body
):
    digest, _ = rawstore.store_blob(tmp_path, body)
    register_snapshot(conn, digest)
    expected = boe_diario.parse_diario(body)
    assert expected.doc is None
    assert expected.parse_error
    parser = Mock(wraps=boe_diario.parse_diario)
    monkeypatch.setattr(boe_diario, "parse_diario", parser)

    with pytest.raises(LookupError) as exc:
        applicability._doc_from_snapshot(conn, tmp_path, SNAPSHOT_ID, BOE_ID)

    assert str(exc.value) == (
        f"diario blob for {BOE_ID} did not parse: {expected.parse_error}"
    )
    parser.assert_called_once_with(body)


def test_valid_matching_hash_document_parses_unchanged(conn, tmp_path, monkeypatch):
    digest, _ = rawstore.store_blob(tmp_path, VALID_XML)
    register_snapshot(conn, digest)
    expected = boe_diario.parse_diario(VALID_XML).doc
    assert expected is not None
    parser = Mock(wraps=boe_diario.parse_diario)
    monkeypatch.setattr(boe_diario, "parse_diario", parser)

    doc = applicability._doc_from_snapshot(conn, tmp_path, SNAPSHOT_ID, BOE_ID)

    assert doc == expected
    assert doc.metadata == {
        "identificador": BOE_ID,
        "titulo": "Synthetic title",
    }
    assert [node.text for node in doc.nodes] == [
        "First paragraph.", "Second paragraph.",
    ]
    parser.assert_called_once_with(VALID_XML)
