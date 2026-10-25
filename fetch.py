#!/usr/bin/env python3
"""Fetch a PiyoLog data feed into the local store.

The feed URL is read from PIYOLOG_FEED_URL or from a local file (.feed_url by default).
It is never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import piyolog

BASE_DIR = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a PiyoLog data feed and merge it into the local store."
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PIYOLOG_DATA_DIR") or str(BASE_DIR / "data"),
        help="Directory for snapshots and the local store (default: <repo>/data, or PIYOLOG_DATA_DIR).",
    )
    parser.add_argument(
        "--feed-url-file",
        help="File with the feed URL on one line. Overrides PIYOLOG_FEED_URL.",
    )
    parser.add_argument(
        "--tz",
        help=f"Timezone for the snapshot filename (default: PIYOLOG_TZ or {piyolog.DEFAULT_TZ}).",
    )
    parser.add_argument(
        "--backend",
        choices=("local", "postgres"),
        default="local",
        help="local writes files only. postgres also upserts into DATABASE_URL when psycopg or psql is available.",
    )
    parser.add_argument(
        "--sql-dir",
        default=os.environ.get("PIYOLOG_SQL_DIR") or str(BASE_DIR / "sql"),
        help="Where to write generated SQL when --backend postgres is set (default: <repo>/sql).",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    piyolog.reject_url_on_argv(args_list)
    args = build_parser().parse_args(args_list)
    tz = piyolog.resolve_tz(args.tz)
    url = piyolog.load_feed_url(feed_url_file=args.feed_url_file, cwd=BASE_DIR)
    result = piyolog.fetch_and_store(
        url,
        Path(args.data_dir),
        tz,
        now=datetime.now(timezone.utc),
        backend=args.backend,
        database_url=os.environ.get("DATABASE_URL") or "",
        sql_dir=Path(args.sql_dir),
    )
    print(
        "snapshot={snapshot} fetched={fetched} inserted={inserted} updated={updated} skipped={skipped}".format(
            **result
        )
    )
    if result.get("schema_warning"):
        print(result["schema_warning"], file=sys.stderr)
    if result.get("postgres"):
        print("postgres=updated")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except piyolog.FeedError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        if "://" in text:
            text = type(exc).__name__
        print(text, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
