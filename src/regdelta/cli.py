from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .watcher import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="regdelta")
    subparsers = parser.add_subparsers(dest="command", required=True)
    watch = subparsers.add_parser("watch", help="observe BOE sumario and BdE consultations")
    watch.add_argument("--date", required=True, help="sumario date, YYYY-MM-DD")
    watch.add_argument("--data-dir", default="data", help="data directory (default: ./data)")
    args = parser.parse_args(argv)
    if args.command == "watch":
        summary = run(args.date, Path(args.data_dir))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary["exit_code"]
    return 0


if __name__ == "__main__":
    sys.exit(main())
