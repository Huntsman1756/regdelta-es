from __future__ import annotations

import json
import sqlite3
from datetime import date

import pytest

from regdelta import cli, query


def run_main(capsys, argv):
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


@pytest.fixture
def empty_ledger(tmp_path):
    conn = sqlite3.connect(tmp_path / "regdelta.sqlite")
    conn.execute("CREATE TABLE instruments (instrument_id TEXT PRIMARY KEY,"
                 " boe_id TEXT, titulo TEXT)")
    conn.commit()
    conn.close()
    return tmp_path


@pytest.mark.parametrize("bad", [
    "20251229", "2025-12-29T00:00", "2025-13-01", "not-a-date", "",
])
def test_invalid_dates_rejected_as_json_before_db_open(capsys, tmp_path, bad):
    code, payload = run_main(
        capsys, ["changes", "--since", bad, "--data-dir", str(tmp_path)])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_DATE_RANGE"
    assert not (tmp_path / "regdelta.sqlite").exists()


@pytest.mark.parametrize("argv", [
    ["changes", "--since", "2025-01-02", "--until", "2025-01-01"],
    ["diff", "BOE-A-2025-1", "--from", "2025-01-02", "--to", "2025-01-01"],
])
def test_inverted_windows_rejected(capsys, tmp_path, argv):
    code, payload = run_main(
        capsys, argv + ["--data-dir", str(tmp_path)])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_DATE_RANGE"


@pytest.mark.parametrize("bad", ["2025-13-01", "20251229"])
def test_watch_invalid_date_json_before_side_effects(capsys, tmp_path, bad):
    code, payload = run_main(
        capsys, ["watch", "--date", bad, "--data-dir", str(tmp_path)])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_DATE_RANGE"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_watch_valid_date_invokes_runner(
        capsys, tmp_path, monkeypatch, exit_code):
    seen = {}

    def fake_run(date_iso, data_dir):
        seen["date"] = date_iso
        seen["dir"] = data_dir
        return {"exit_code": exit_code}

    monkeypatch.setattr(cli, "run", fake_run)
    code, payload = run_main(
        capsys, ["watch", "--date", "2025-12-29",
                 "--data-dir", str(tmp_path)])
    assert code == exit_code
    assert seen == {"date": "2025-12-29", "dir": tmp_path}
    assert payload == {"exit_code": exit_code}


def test_missing_database_json_error(capsys, tmp_path):
    code, payload = run_main(
        capsys, ["affects", "BOE-A-2025-1", "--data-dir", str(tmp_path)])
    assert code == 2
    assert payload["error"]["code"] == "DATABASE_NOT_FOUND"


def test_corrupt_database_json_error(capsys, tmp_path):
    (tmp_path / "regdelta.sqlite").write_bytes(b"not a database at all")
    code, payload = run_main(
        capsys, ["affects", "BOE-A-2025-1", "--data-dir", str(tmp_path)])
    assert code == 2
    assert payload["error"]["code"] == "DATABASE_ERROR"


def test_unknown_instrument_json_error(capsys, empty_ledger):
    code, payload = run_main(
        capsys, ["affects", "BOE-A-9999-1",
                 "--data-dir", str(empty_ledger)])
    assert code == 2
    assert payload["error"]["code"] == "INSTRUMENT_NOT_FOUND"


def test_upcoming_overflow_is_invalid_date_range():
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(query.InvalidDateRange):
            query.upcoming(conn, from_date=date(2025, 12, 29),
                           days=10**9)
    finally:
        conn.close()


@pytest.mark.parametrize("argv", [
    ["watch", "--date"],
    ["changes", "--since"],
    ["changes", "--since", "2025-01-01", "--until"],
    ["upcoming", "--days", "1", "--from"],
    ["as-of", "BOE-A-2025-1", "--date"],
    ["diff", "BOE-A-2025-1", "--to", "2025-12-31", "--from"],
    ["diff", "BOE-A-2025-1", "--from", "2025-01-01", "--to"],
])
@pytest.mark.parametrize("bad", [
    "", "20251229", "2025-W01-1", "2025-02-29", "2025-1-01",
    " 2025-12-29", "2025-12-29\n", "２０２５-１２-２９",
])
def test_all_date_flags_validate_before_io(
        capsys, tmp_path, monkeypatch, argv, bad):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid date reached I/O")

    monkeypatch.setattr(cli, "run", unexpected)
    monkeypatch.setattr(query, "connect_readonly", unexpected)
    code, payload = run_main(
        capsys, argv + [bad, "--data-dir", str(tmp_path / "absent")])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_DATE_RANGE"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("from_date,days", [
    ("9999-12-31", 1), ("2025-01-01", 10**9),
    ("2025-01-01", 10**30), ("2025-01-01", -1),
])
def test_upcoming_invalid_window_before_io(
        capsys, tmp_path, monkeypatch, from_date, days):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid window opened database")

    monkeypatch.setattr(query, "connect_readonly", unexpected)
    code, payload = run_main(
        capsys, ["upcoming", "--from", from_date, "--days", str(days),
                 "--data-dir", str(tmp_path)])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_DATE_RANGE"
    with pytest.raises(query.InvalidDateRange):
        query.upcoming(None, from_date=date.fromisoformat(from_date),
                       days=days)


@pytest.mark.parametrize("command", ["watch", "affects"])
@pytest.mark.parametrize("error,expected", [
    (PermissionError("access denied"), "FILESYSTEM_ERROR"),
    (FileExistsError("already exists"), "FILESYSTEM_ERROR"),
    (NotADirectoryError("not a directory"), "FILESYSTEM_ERROR"),
    (sqlite3.OperationalError("database is locked"), "DATABASE_ERROR"),
    (sqlite3.DatabaseError("database disk image is malformed"), "DATABASE_ERROR"),
])
def test_operational_errors_json(
        capsys, tmp_path, monkeypatch, command, error, expected):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "run", fail)
    monkeypatch.setattr(query, "connect_readonly", fail)
    argv = (["watch", "--date", "2025-01-01"] if command == "watch"
            else ["affects", "BOE-A-2025-1"])
    code, payload = run_main(
        capsys, argv + ["--data-dir", str(tmp_path)])
    assert code == 2
    assert payload == {"error": {"code": expected, "message": str(error)}}


@pytest.mark.parametrize("command", ["watch", "affects"])
@pytest.mark.parametrize("error", [
    ValueError("bug"), TypeError("bug"), RuntimeError("bug"),
    sqlite3.ProgrammingError("bad binding"),
    sqlite3.IntegrityError("constraint failed"),
    sqlite3.DataError("bad data"), sqlite3.InternalError("internal error"),
])
def test_unexpected_errors_propagate(capsys, monkeypatch, command, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "run", fail)
    monkeypatch.setattr(query, "connect_readonly", fail)
    argv = (["watch", "--date", "2025-01-01"] if command == "watch"
            else ["affects", "BOE-A-2025-1"])
    with pytest.raises(type(error), match=str(error)):
        cli.main(argv)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("error", [
    sqlite3.OperationalError("database is locked"), RuntimeError("bug"),
])
def test_query_failure_closes_connection(capsys, monkeypatch, error):
    conn = sqlite3.connect(":memory:")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(query, "connect_readonly", lambda path: conn)
    monkeypatch.setattr(query, "affects", fail)
    if isinstance(error, sqlite3.OperationalError):
        code, payload = run_main(capsys, ["affects", "BOE-A-2025-1"])
        assert code == 2
        assert payload["error"]["code"] == "DATABASE_ERROR"
    else:
        with pytest.raises(RuntimeError, match="bug"):
            cli.main(["affects", "BOE-A-2025-1"])
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


def test_readonly_connection_setup_failure_closes(monkeypatch, empty_ledger):
    class FailedConnection:
        closed = False

        def execute(self, sql):
            raise sqlite3.OperationalError("setup failed")

        def close(self):
            self.closed = True

    conn = FailedConnection()
    monkeypatch.setattr(query.sqlite3, "connect", lambda *a, **kw: conn)
    with pytest.raises(sqlite3.OperationalError, match="setup failed"):
        query.connect_readonly(empty_ledger)
    assert conn.closed


def test_readonly_connection_preserves_ledger(empty_ledger):
    path = empty_ledger / "regdelta.sqlite"
    before = path.read_bytes()
    conn = query.connect_readonly(empty_ledger)
    try:
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE forbidden (id INTEGER)")
    finally:
        conn.close()
    assert path.read_bytes() == before


@pytest.mark.parametrize("argv,module,name,expected", [
    (["changes", "--since", "2024-02-29", "--until", "2024-02-29"],
     query, "changes", {"since": date(2024, 2, 29),
                        "until": date(2024, 2, 29), "target": None}),
    (["as-of", "BOE-A-2025-1", "--date", "2025-01-01"],
     query, "as_of", {"target": "BOE-A-2025-1",
                      "as_of_date": date(2025, 1, 1), "subject": None}),
    (["upcoming", "--from", "9999-12-31", "--days", "0"],
     query, "upcoming", {"from_date": date.max, "days": 0, "target": None}),
    (["diff", "BOE-A-2025-1", "--from", "2025-01-01", "--to", "2025-01-01"],
     cli.diffing, "diff", {"target": "BOE-A-2025-1",
                           "from_date": date(2025, 1, 1),
                           "to_date": date(2025, 1, 1), "subject": None}),
])
def test_valid_dates_dispatched_and_connection_closed(
        capsys, monkeypatch, argv, module, name, expected):
    conn = sqlite3.connect(":memory:")

    def execute(actual_conn, **kwargs):
        assert actual_conn is conn
        assert kwargs == expected
        return {"results": []}

    monkeypatch.setattr(query, "connect_readonly", lambda path: conn)
    monkeypatch.setattr(module, name, execute)
    code, payload = run_main(capsys, argv)
    assert code == 0
    assert payload == {"results": []}
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


def test_iso_helper_rejects_non_strict_formats():
    for bad in ("20251229", "2025-12-29T00:00", "2025-1-1", " 2025-12-29"):
        with pytest.raises(query.InvalidDateRange):
            cli._iso(bad)
    assert cli._iso("2025-12-29") == date(2025, 12, 29)
