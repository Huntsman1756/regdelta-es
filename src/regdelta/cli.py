from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import diffing, query
from .util import madrid_local_date
from .watcher import run

_STRICT_ISO_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _iso(text: str) -> date:
    if not _STRICT_ISO_RE.fullmatch(text or ""):
        raise query.InvalidDateRange(f"not a strict ISO date: {text!r}")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise query.InvalidDateRange(f"not a strict ISO date: {text!r}")


def _query_out(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2,
                     sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="regdelta")
    subparsers = parser.add_subparsers(dest="command", required=True)

    watch = subparsers.add_parser(
        "watch", help="observe BOE sumario and BdE consultations")
    watch.add_argument("--date", required=True,
                       help="sumario date, YYYY-MM-DD")
    watch.add_argument("--data-dir", default="data",
                       help="data directory (default: ./data)")

    p = subparsers.add_parser(
        "changes", help="relations published inside a date window")
    p.add_argument("--since", required=True, help="YYYY-MM-DD")
    p.add_argument("--until", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--target", help="target instrument ref")
    p.add_argument("--data-dir", default="data")

    p = subparsers.add_parser(
        "affects", help="relations recorded against an instrument")
    p.add_argument("target", help="BOE-A-* id or 'Circular N/YYYY'")
    p.add_argument("--subject", help="exact locator_key")
    p.add_argument("--modifier", help="exact modifier BOE id")
    p.add_argument("--data-dir", default="data")

    p = subparsers.add_parser(
        "upcoming", help="dated applicability effects in a window")
    p.add_argument("--from", dest="from_date",
                   help="YYYY-MM-DD (default: today, Europe/Madrid)")
    p.add_argument("--days", type=int, required=True)
    p.add_argument("--target", help="target instrument ref")
    p.add_argument("--data-dir", default="data")

    p = subparsers.add_parser(
        "as-of", help="legal-time facts published up to a date")
    p.add_argument("target", help="BOE-A-* id or 'Circular N/YYYY'")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--subject", help="exact locator_key")
    p.add_argument("--data-dir", default="data")

    p = subparsers.add_parser(
        "diff", help="representation-aware deltas in a publication window")
    p.add_argument("target", help="BOE-A-* id or 'Circular N/YYYY'")
    p.add_argument("--from", dest="from_date", required=True,
                   help="YYYY-MM-DD (exclusive baseline)")
    p.add_argument("--to", dest="to_date", required=True,
                   help="YYYY-MM-DD (inclusive)")
    p.add_argument("--subject", help="exact locator_key")
    p.add_argument("--data-dir", default="data")

    args = parser.parse_args(argv)
    try:
        for name in ("date", "since", "until", "from_date", "to_date"):
            value = getattr(args, name, None)
            if value is not None:
                setattr(args, name, _iso(value))
        if args.command == "watch":
            summary = run(args.date.isoformat(), Path(args.data_dir))
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return summary["exit_code"]
        if args.command == "changes" and args.until is not None \
                and args.until < args.since:
            raise query.InvalidDateRange(
                f"since {args.since} > until {args.until}")
        if args.command == "diff" and args.to_date < args.from_date:
            raise query.InvalidDateRange(
                f"to {args.to_date} < from {args.from_date}")
        if args.command == "upcoming":
            if args.from_date is None:
                args.from_date = madrid_local_date(datetime.now(timezone.utc))
            query._upcoming_end(args.from_date, args.days)
        conn = query.connect_readonly(Path(args.data_dir))
        try:
            if args.command == "changes":
                out = query.changes(
                    conn, since=args.since, until=args.until,
                    target=args.target)
            elif args.command == "affects":
                out = query.affects(
                    conn, target=args.target, subject=args.subject,
                    modifier=args.modifier)
            elif args.command == "upcoming":
                out = query.upcoming(conn, from_date=args.from_date,
                                     days=args.days, target=args.target)
            elif args.command == "as-of":
                out = query.as_of(conn, target=args.target,
                                  as_of_date=args.date,
                                  subject=args.subject)
            elif args.command == "diff":
                out = diffing.diff(conn, target=args.target,
                                   from_date=args.from_date,
                                   to_date=args.to_date,
                                   subject=args.subject)
            else:  # pragma: no cover - argparse enforces choices
                return 1
        finally:
            conn.close()
    except query.QueryError as exc:
        _query_out({"error": {"code": exc.code, "message": str(exc)}})
        return 2
    except OSError as exc:
        _query_out({"error": {"code": "FILESYSTEM_ERROR",
                              "message": str(exc)}})
        return 2
    except sqlite3.DatabaseError as exc:
        if not isinstance(exc, sqlite3.OperationalError) \
                and type(exc) is not sqlite3.DatabaseError:
            raise
        _query_out({"error": {"code": "DATABASE_ERROR",
                              "message": str(exc)}})
        return 2
    _query_out(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
