#!/usr/bin/env python3
"""Print per-day PiyoLog stats as Markdown and/or JSON."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import piyolog

BASE_DIR = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize the local PiyoLog store by day.")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PIYOLOG_DATA_DIR") or str(BASE_DIR / "data"),
        help="Store directory (default: <repo>/data, or PIYOLOG_DATA_DIR).",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "store", "snapshots"),
        default="auto",
        help="auto uses records.jsonl when it has rows, otherwise JSON snapshots.",
    )
    parser.add_argument("--from", dest="start", help="First local date, YYYY-MM-DD, inclusive.")
    parser.add_argument("--to", dest="end", help="Last local date, YYYY-MM-DD, inclusive.")
    parser.add_argument(
        "--days",
        type=int,
        help="Number of local days ending today. Ignored when --from and --to are set. Default: 1.",
    )
    parser.add_argument(
        "--tz",
        help=f"Timezone for day boundaries (default: PIYOLOG_TZ or {piyolog.DEFAULT_TZ}).",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json", "both"),
        default="md",
        help="md (default), json, or both.",
    )
    parser.add_argument(
        "--output",
        help="Write the summary to this path. With --format both, write .md and .json next to this stem.",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    piyolog.reject_url_on_argv(args_list)
    args = build_parser().parse_args(args_list)
    tz = piyolog.resolve_tz(args.tz)
    if args.start or args.end:
        if not args.start or not args.end:
            raise piyolog.FeedError("Pass both --from and --to, or use --days.", exit_code=2)
        start = piyolog.parse_day(args.start)
        end = piyolog.parse_day(args.end)
    else:
        start, end = piyolog.window_from_days(args.days or 1, tz, datetime.now(timezone.utc))
    records = piyolog.load_records(Path(args.data_dir), source=args.source)
    summary = piyolog.summarize(records, tz, start, end)
    markdown = piyolog.render_markdown(summary)
    rendered_json = piyolog.render_json(summary)
    if args.output:
        _write_output(Path(args.output), args.format, markdown, rendered_json)
        return 0
    if args.format == "md":
        sys.stdout.write(markdown)
    elif args.format == "json":
        sys.stdout.write(rendered_json)
    else:
        sys.stdout.write(markdown)
        if not markdown.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.write(rendered_json)
    return 0


def _write_output(path: Path, fmt: str, markdown: str, rendered_json: str) -> None:
    if fmt == "md":
        path.write_text(markdown, encoding="utf-8")
        return
    if fmt == "json":
        path.write_text(rendered_json, encoding="utf-8")
        return
    stem = path.with_suffix("") if path.suffix else path
    stem.with_suffix(".md").write_text(markdown, encoding="utf-8")
    stem.with_suffix(".json").write_text(rendered_json, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except piyolog.FeedError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
