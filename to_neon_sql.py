#!/usr/bin/env python3
"""Build idempotent Postgres upsert SQL from PiyoLog snapshot files.

No credentials are read. This path is optional. The default store is the local
files written by fetch.py. Apply the SQL yourself with psql and DATABASE_URL,
or use `python3 fetch.py --backend postgres`.

Examples:
  python3 to_neon_sql.py
  python3 to_neon_sql.py --all
  python3 to_neon_sql.py --data-dir data --sql-dir sql snapshot.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import piyolog

BASE_DIR = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build idempotent Postgres upsert SQL from PiyoLog snapshot files. "
            "No credentials are read. Local files from fetch.py are the default store."
        ),
        epilog=(
            "examples:\n"
            "  python3 to_neon_sql.py\n"
            "  python3 to_neon_sql.py --all\n"
            "  python3 to_neon_sql.py --data-dir data --sql-dir sql snapshot.json\n"
            "\n"
            "Apply with psql and DATABASE_URL, or use: python3 fetch.py --backend postgres"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PIYOLOG_DATA_DIR") or str(BASE_DIR / "data"),
        help="Directory of snapshot JSON files (default: <repo>/data, or PIYOLOG_DATA_DIR).",
    )
    parser.add_argument(
        "--sql-dir",
        default=os.environ.get("PIYOLOG_SQL_DIR") or str(BASE_DIR / "sql"),
        help="Where to write upsert.sql and fetchlog.sql (default: <repo>/sql, or PIYOLOG_SQL_DIR).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Read every snapshot JSON in the data directory. Later files win on the same event_id.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Snapshot filenames. Relative names are resolved inside the data directory. Default: the newest snapshot.",
    )
    return parser


def snapshot_paths(data_dir: str, read_all: bool, files: list[str]) -> list[Path]:
    root = Path(data_dir)
    if read_all:
        return sorted(path for path in root.glob("*.json") if path.is_file())
    if files:
        paths = []
        for name in files:
            candidate = Path(name)
            paths.append(candidate if candidate.is_absolute() else root / name)
        return paths
    found = sorted(path for path in root.glob("*.json") if path.is_file())
    return found[-1:]


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    piyolog.reject_url_on_argv(args_list)
    args = build_parser().parse_args(args_list)
    if args.all and args.files:
        print("Pass either --all or file names, not both.", file=sys.stderr)
        return 2
    paths = snapshot_paths(args.data_dir, args.all, args.files)
    try:
        records, logs = piyolog.collect_snapshot_files(paths)
    except FileNotFoundError as exc:
        print(f"Snapshot not found: {exc.filename}", file=sys.stderr)
        return 2
    except piyolog.FeedError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code
    upsert, fetch_log = piyolog.build_sql(records, logs)
    piyolog.write_sql_files(Path(args.sql_dir), upsert, fetch_log)
    print(f"files={len(paths)} unique_records={len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
