#!/usr/bin/env python3
"""Back up the local PiyoLog store, once per day, with rotation.

Copies records.jsonl / records.csv (the whole store; fetch.py writes
both atomically from the same rows and keeps no SQLite file) into
~/workspace/piyolog-backups/YYYY-MM-DD/ and keeps the newest 30 daily
folders. Local files only; no network.
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_ROOT = BASE_DIR.parent / "piyolog-backups"
TZ = ZoneInfo("Asia/Tokyo")
KEEP = 30


def main() -> int:
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    dest = BACKUP_ROOT / today
    dest.mkdir(parents=True, exist_ok=True)

    count = "?"
    for name in ("records.jsonl", "records.csv"):
        src = DATA_DIR / name
        if src.exists():
            shutil.copy2(src, dest / name)
            if name == "records.jsonl":
                count = sum(1 for line in src.read_text(encoding="utf-8").splitlines() if line.strip())

    (dest / "manifest.txt").write_text(
        f"date={today}\nrecords={count}\ncreated_at={datetime.now(TZ).isoformat()}\n",
        encoding="utf-8",
    )

    dated = sorted(
        p
        for p in BACKUP_ROOT.iterdir()
        if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)
    )
    for old in dated[:-KEEP]:
        shutil.rmtree(old)

    print(f"backup: dest={dest} records={count} kept={min(len(dated), KEEP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
