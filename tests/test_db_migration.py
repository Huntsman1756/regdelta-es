import sqlite3

import pytest

from regdelta import db as dbm


CREATE_SQL = (
    "CREATE TABLE items (id INTEGER PRIMARY KEY,"
    " parent_id INTEGER NOT NULL REFERENCES parents(id),"
    " value INTEGER NOT NULL CHECK (value >= 0))"
)
POST_SQL = (
    "CREATE INDEX idx_items_value ON items(value)",
    "CREATE INDEX idx_items_parent ON items(parent_id)",
)


@pytest.fixture
def migration_db(tmp_path):
    path = tmp_path / "migration.sqlite"
    conn = sqlite3.connect(path, isolation_level=None, timeout=0)
    conn.executescript(
        "CREATE TABLE parents (id INTEGER PRIMARY KEY);"
        "CREATE TABLE other_parents (id INTEGER PRIMARY KEY);"
        + CREATE_SQL.replace("value >= 0", "value > 0") + ";"
        "CREATE INDEX idx_items_value ON items(value);"
        "CREATE TABLE children (id INTEGER PRIMARY KEY,"
        " item_id INTEGER REFERENCES items(id) ON DELETE CASCADE);"
        "INSERT INTO parents VALUES (1);"
        "INSERT INTO items VALUES (1, 1, 7), (2, 1, 7);"
        "INSERT INTO children VALUES (1, 1);"
    )
    try:
        yield conn, path
    finally:
        conn.close()


def _rebuild(conn, create_sql=CREATE_SQL, post_sql=POST_SQL):
    dbm._rebuild_table(conn, "items", "id, parent_id, value",
                       create_sql, post_sql)


def _state(conn):
    return (
        conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master"
            " ORDER BY type, name").fetchall(),
        conn.execute("SELECT * FROM items ORDER BY id").fetchall(),
        conn.execute("SELECT * FROM children ORDER BY id").fetchall(),
    )


@pytest.mark.parametrize("foreign_keys", [0, 1])
@pytest.mark.parametrize("isolation_level", [None, ""])
def test_rebuild_commits_rows_indexes_and_inbound_foreign_keys(
        migration_db, foreign_keys, isolation_level):
    conn, path = migration_db
    conn.isolation_level = isolation_level
    conn.execute(f"PRAGMA foreign_keys = {foreign_keys}")
    before = _state(conn)

    _rebuild(conn)

    assert not conn.in_transaction
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (foreign_keys,)
    assert _state(conn)[1:] == before[1:]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_key_list(children)").fetchone()[2] == "items"
    assert {r[1] for r in conn.execute("PRAGMA index_list(items)")} == {
        "idx_items_value", "idx_items_parent"}
    assert "value >= 0" in conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='items'").fetchone()[0]
    reopened = sqlite3.connect(path)
    try:
        assert _state(reopened) == _state(conn)
    finally:
        reopened.close()


@pytest.mark.parametrize("foreign_keys", [0, 1])
@pytest.mark.parametrize("failure", ["create", "copy", "index", "foreign_key"])
def test_rebuild_failure_preserves_schema_rows_and_indexes(
        migration_db, foreign_keys, failure):
    conn, path = migration_db
    conn.execute(f"PRAGMA foreign_keys = {foreign_keys}")
    before = _state(conn)
    create_sql = CREATE_SQL
    post_sql = POST_SQL
    if failure == "create":
        create_sql = CREATE_SQL + " INVALID"
        error, message = sqlite3.OperationalError, "syntax error|unknown table option"
    elif failure == "copy":
        create_sql = CREATE_SQL.replace("value >= 0", "value > 7")
        error, message = sqlite3.IntegrityError, "CHECK constraint failed"
    elif failure == "index":
        post_sql += ("CREATE UNIQUE INDEX idx_items_unique ON items(value)",)
        error, message = sqlite3.IntegrityError, "UNIQUE constraint failed"
    else:
        create_sql = CREATE_SQL.replace("REFERENCES parents", "REFERENCES other_parents")
        error, message = sqlite3.IntegrityError, "foreign_key_check failed"

    with pytest.raises(error, match=message):
        _rebuild(conn, create_sql, post_sql)

    assert not conn.in_transaction
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (foreign_keys,)
    assert _state(conn) == before
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    reopened = sqlite3.connect(path)
    try:
        assert _state(reopened) == before
    finally:
        reopened.close()


@pytest.mark.parametrize("foreign_keys", [0, 1])
def test_rebuild_rejects_active_transaction_without_changing_it(
        migration_db, foreign_keys):
    conn, _ = migration_db
    conn.execute(f"PRAGMA foreign_keys = {foreign_keys}")
    conn.execute("BEGIN")
    conn.execute("INSERT INTO items VALUES (3, 1, 8)")
    before = _state(conn)

    with pytest.raises(sqlite3.OperationalError, match="active transaction"):
        _rebuild(conn)

    assert conn.in_transaction
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (foreign_keys,)
    assert _state(conn) == before
    conn.execute("ROLLBACK")
    assert conn.execute("SELECT count(*) FROM items").fetchone() == (2,)


@pytest.mark.parametrize("foreign_keys", [0, 1])
@pytest.mark.parametrize("failure", ["begin", "commit"])
def test_rebuild_lock_failure_restores_foreign_keys(migration_db, foreign_keys, failure):
    conn, path = migration_db
    conn.execute(f"PRAGMA foreign_keys = {foreign_keys}")
    before = _state(conn)
    blocker = sqlite3.connect(path, isolation_level=None, timeout=0)
    try:
        if failure == "begin":
            blocker.execute("BEGIN IMMEDIATE")
        else:
            blocker.execute("BEGIN")
            blocker.execute("SELECT * FROM items").fetchall()
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            _rebuild(conn)
    finally:
        blocker.close()

    assert not conn.in_transaction
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (foreign_keys,)
    assert _state(conn) == before


def test_connect_migrates_legacy_source_tables_and_preserves_children(tmp_path):
    path = tmp_path / "legacy.sqlite"
    legacy_sql = dbm.SCHEMA.replace(
        "TEXT NOT NULL REFERENCES source_registry(source_id)",
        "TEXT NOT NULL CHECK (source_id IN ('boe_diario'))")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(legacy_sql)
        conn.execute("INSERT INTO source_blobs VALUES (?, 1, 't')", ("a" * 64,))
        conn.execute(
            "INSERT INTO source_snapshots"
            " (snapshot_id, source_id, source_url, blob_sha256, parse_status,"
            " parser_name, parser_version, first_checked_at)"
            " VALUES (?, 'boe_diario', 'u', ?, 'COMPLETE', 'p', 'v', 't')",
            ("b" * 64, "a" * 64))
        conn.execute(
            "INSERT INTO source_checks"
            " (check_id, source_id, source_url, checked_at, status, snapshot_id)"
            " VALUES (?, 'boe_diario', 'u', 't', 'OK', ?)",
            ("c" * 64, "b" * 64))
        conn.execute("INSERT INTO boe_items VALUES ('item', ?)", ("b" * 64,))
        tables = ("source_snapshots", "source_checks", "boe_items")
        before = {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
        for table in tables[:2]:
            assert dbm._has_source_id_check(conn.execute(
                "SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0])
        conn.commit()
    finally:
        conn.close()

    for _ in range(2):
        conn = dbm.connect(path)
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            assert {t: conn.execute(f"SELECT * FROM {t}").fetchall()
                    for t in tables} == before
            for table in tables[:2]:
                assert not dbm._has_source_id_check(conn.execute(
                    "SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0])
                assert "source_registry" in {
                    r[2] for r in conn.execute(f"PRAGMA foreign_key_list({table})")}
            assert "idx_checks_source_time" in {
                r[1] for r in conn.execute("PRAGMA index_list(source_checks)")}
        finally:
            conn.close()
