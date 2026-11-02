#!/usr/bin/env python3
"""Sync PiyoLog snapshots to Neon over its HTTPS SQL endpoint.

Use this instead of `fetch.py --backend postgres` wherever a direct
Postgres connection (TCP port 5432) cannot leave the machine — for
example on Muse, whose egress goes through an HTTP proxy, so psycopg
and psql both fail there. This script needs only HTTPS (port 443).

It reads DATABASE_URL from the environment, or from a gitignored .env
file next to the script (never printed — do not source that file in a
shell; the URL contains & and must stay quoted there). It builds the
same idempotent upsert as to_postgres_sql.py from snapshot files, and posts
one statement at a time to https://<host>/sql with the connection string
in the Neon-Connection-String header. Standard library only. It does
not rely on piyolog.split_sql / piyolog.redact (not every piyolog.py
revision ships them); the small helpers it needs live in this file.

The schema is applied first, but a role that can only read and write the
tables (no CREATE on schema public) gets a permission error there; that
step is then skipped with a warning, because such a role is the normal
setup — the tables must be created once by the database owner.

Examples:
  python3 neon_https_sync.py            # sync the newest snapshot
  python3 neon_https_sync.py --all      # sync every snapshot (full backfill)
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import piyolog

BASE_DIR = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync PiyoLog snapshots to Neon over HTTPS (no direct Postgres connection)."
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PIYOLOG_DATA_DIR") or str(BASE_DIR / "data"),
        help="Directory of snapshot JSON files (default: <repo>/data, or PIYOLOG_DATA_DIR).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync every snapshot in the data directory instead of only the newest.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Snapshot filenames. Relative names are resolved inside the data directory.",
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


def load_database_url() -> str:
    direct = (os.environ.get("DATABASE_URL") or "").strip()
    if direct:
        return direct
    env_file = BASE_DIR / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("DATABASE_URL="):
                continue
            value = stripped.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            return value
    return ""


def split_schema(text: str) -> list[str]:
    # schema.sql is hand-maintained DDL with no semicolons inside string
    # literals or comments, so a plain split is safe here. Record-bearing
    # statements are never split (see main); a ";" inside a record memo
    # would corrupt them.
    return [chunk.strip() for chunk in text.split(";") if chunk.strip()]


def redact(text: str, secret: str) -> str:
    return text.replace(secret, "[redacted]") if secret else text


def post_sql(host: str, database_url: str, statement: str):
    body = json.dumps({"query": statement, "params": []}).encode("utf-8")
    request = urllib.request.Request(
        f"https://{host}/sql", data=body, method="POST"
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Neon-Connection-String", database_url)
    last_error = None
    for _attempt, delay in ((1, 3), (2, 10), (3, 0)):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise piyolog.FeedError(
                f"Neon HTTPS sync failed (HTTP {exc.code}): {detail[:300]}",
                exit_code=6,
            ) from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.HTTPException,
        ) as exc:
            # HTTPException covers IncompleteRead (a truncated response).
            # Retrying is safe: every statement this script posts is an
            # idempotent upsert or an insert-on-conflict-do-nothing.
            last_error = exc
            if delay:
                time.sleep(delay)
    raise piyolog.FeedError(
        f"Neon HTTPS sync could not connect after retries: {type(last_error).__name__}",
        exit_code=6,
    )


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    piyolog.reject_url_on_argv(args_list)
    args = build_parser().parse_args(args_list)
    if args.all and args.files:
        print("Pass either --all or file names, not both.", file=sys.stderr)
        return 2
    database_url = load_database_url()
    if not database_url:
        print(
            "DATABASE_URL is empty. Set it, or put it in .env next to this script "
            "(that file is gitignored), or run without this script; the local store "
            "is the default and needs no database.",
            file=sys.stderr,
        )
        return 2
    host = urllib.parse.urlparse(database_url).hostname or ""
    paths = snapshot_paths(args.data_dir, args.all, args.files)
    if not paths:
        print("No snapshot files found. Run fetch.py first.", file=sys.stderr)
        return 2
    records, logs = piyolog.collect_snapshot_files(paths)
    upsert, fetch_log = piyolog.build_sql(records, logs)
    schema = piyolog.SCHEMA_PATH.read_text(encoding="utf-8")
    try:
        for statement in split_schema(schema):
            post_sql(host, database_url, statement)
    except piyolog.FeedError as exc:
        if "42501" in str(exc) or "permission denied" in str(exc):
            print(
                "schema step skipped: this role cannot create tables. "
                "The tables must already exist (created by the owner).",
                file=sys.stderr,
            )
        else:
            raise
    try:
        # Post the upsert and fetch-log statements whole: they embed record
        # text as a JSON literal, and a ";" inside free text (a memo) would
        # corrupt naive statement splitting. Each string is one statement.
        for statement in (upsert, fetch_log):
            post_sql(host, database_url, statement.rstrip().rstrip(";"))
    except piyolog.FeedError as exc:
        print(redact(str(exc), database_url), file=sys.stderr)
        return exc.exit_code
    print(f"synced files={len(paths)} unique_records={len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
