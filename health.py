#!/usr/bin/env python3
"""Health check for the local PiyoLog store.

Reads only local files (never touches the feed). Verifies:
- records.jsonl row count and event_id uniqueness
- records.csv row count matches the JSONL store (both are written
  from the same rows by fetch.py; the store has no SQLite file)
- no calendar day in range is missing records entirely
- the newest snapshot is not stale (a free feed only covers ~24 hours,
  so a gap longer than that can mean permanently lost records)

Prints one summary line, plus WARN lines for each problem.
Exit code 0 when healthy, 2 when any warning fires.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TZ = ZoneInfo("Asia/Tokyo")
STALE_HOURS = 24


def main() -> int:
    warnings: list[str] = []
    jsonl = DATA_DIR / "records.jsonl"
    rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [r.get("event_id") for r in rows]
    if len(ids) != len(set(ids)):
        warnings.append(f"duplicate event_id in jsonl: {len(ids) - len(set(ids))} extra rows")

    csv_count = None
    csv_path = DATA_DIR / "records.csv"
    if csv_path.exists():
        # Parse, don't count lines: quoted memo fields can contain
        # newlines, so one record may span several physical lines.
        with csv_path.open(encoding="utf-8", newline="") as handle:
            csv_rows = list(csv.reader(handle))
        csv_count = max(len(csv_rows) - 1, 0) if csv_rows else 0
        if csv_count != len(rows):
            warnings.append(f"csv count {csv_count} != jsonl count {len(rows)}")
    else:
        warnings.append("records.csv missing")

    days = sorted({r["recorded_at"][:10] for r in rows})
    if days:
        start = datetime.strptime(days[0], "%Y-%m-%d").date()
        end = datetime.strptime(days[-1], "%Y-%m-%d").date()
        have = set(days)
        d = start
        while d <= end:
            if d.isoformat() not in have:
                warnings.append(f"no records at all on {d.isoformat()} (UTC day)")
            d += timedelta(days=1)

    snapshots = sorted(DATA_DIR.glob("*.json"))
    age_text = "none"
    if snapshots:
        newest = snapshots[-1].stem
        snap_dt = datetime.strptime(newest, "%Y%m%d_%H%M%S").replace(tzinfo=TZ)
        age = datetime.now(timezone.utc).astimezone(TZ) - snap_dt
        age_hours = age.total_seconds() / 3600
        age_text = f"{newest} age={age_hours:.1f}h"
        if age_hours > STALE_HOURS:
            warnings.append(
                f"last successful fetch is {age_hours:.1f}h old (>{STALE_HOURS}h); "
                "a free feed only covers ~24h, so records may be lost permanently"
            )
    else:
        warnings.append("no snapshots found")

    rng = f"{days[0]}..{days[-1]}" if days else "empty"
    status = "OK" if not warnings else "WARN"
    print(
        f"health: records={len(rows)} unique={len(set(ids))} csv={csv_count} "
        f"range={rng} last_snapshot={age_text} status={status}"
    )
    for w in warnings:
        print(f"WARN: {w}")
    return 0 if not warnings else 2


if __name__ == "__main__":
    sys.exit(main())
