from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from regdelta.http import FetchResult
from regdelta.watcher import run

FIXTURES = Path(__file__).parent / "fixtures"

TABLES = [
    "source_blobs",
    "source_snapshots",
    "source_checks",
    "boe_items",
    "boe_item_placements",
    "bde_consultations",
    "bde_snapshot_memberships",
    "anomalies",
]


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeFetch:
    def __init__(self):
        self.responses = {}
        self.calls = []

    def set_url(self, needle: str, body: bytes | None, media_type: str = "application/xml",
                http_status: int = 200, error_class: str | None = None) -> None:
        self.responses[needle] = (body, media_type, http_status, error_class)

    def __call__(self, url: str, accept: str) -> FetchResult:
        self.calls.append(url)
        for needle, (body, media_type, http_status, error_class) in self.responses.items():
            if needle in url:
                if error_class is not None:
                    return FetchResult(url, None, None, None, error_class, "injected failure")
                if http_status != 200:
                    return FetchResult(url, http_status, media_type, None, "HTTP_ERROR",
                                       f"http {http_status}")
                return FetchResult(url, 200, media_type, body, None, None)
        raise AssertionError(f"no fixture configured for {url}")


def make_fetch(sumario_date_iso: str, sumario_fixture: str, consultas_fixture: str = "bde_pi.html") -> FakeFetch:
    fake = FakeFetch()
    fake.set_url("boe/sumario/" + sumario_date_iso.replace("-", ""), load(sumario_fixture))
    fake.set_url("consultas-publicas", load(consultas_fixture), "text/html; charset=utf-8")
    return fake


def run_offline(tmp_path: Path, fetch, date_iso: str = "2025-12-29") -> dict:
    return run(date_iso, tmp_path, fetch)


def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "regdelta.sqlite")
    return conn


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


@pytest.fixture
def fresh_dir(tmp_path: Path) -> Path:
    return tmp_path
