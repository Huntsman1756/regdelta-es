from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

WS_RE = re.compile(r"\s+")
DDMMYYYY_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
COMPACT_DATE_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_utc_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def normalize_ws(text: str) -> str:
    text = text.replace("\xa0", " ")
    return WS_RE.sub(" ", text).strip()


def normalize_title(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.casefold()
    return normalize_ws(normalized)


def parse_ddmmyyyy(text: str) -> str | None:
    match = DDMMYYYY_RE.search(text)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def canonical_date(text: str) -> str | None:
    compact = COMPACT_DATE_RE.fullmatch(text.strip())
    if compact:
        year, month, day = (int(part) for part in compact.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return parse_ddmmyyyy(text)


def _last_sunday(year: int, month: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    while last.weekday() != 6:
        last -= timedelta(days=1)
    return last


def madrid_local_date(utc_dt: datetime) -> date:
    year = utc_dt.astimezone(timezone.utc).year
    cest_start = datetime(year, 3, _last_sunday(year, 3).day, 1, 0, tzinfo=timezone.utc)
    cest_end = datetime(year, 10, _last_sunday(year, 10).day, 1, 0, tzinfo=timezone.utc)
    offset_hours = 2 if cest_start <= utc_dt.astimezone(timezone.utc) < cest_end else 1
    return (utc_dt.astimezone(timezone.utc) + timedelta(hours=offset_hours)).date()
