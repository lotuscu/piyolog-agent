#!/usr/bin/env python3
"""Local store and summaries for a PiyoLog data feed. Python standard library only.

The feed URL is a secret. Functions in this module never include it in errors.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

USER_AGENT = "piyolog-briefing/0.1 (personal local summary)"
DEFAULT_TZ = "Asia/Tokyo"
MILK_TYPES = ("Formula", "ExpressedBreastMilk", "BreastFeeding", "Pumping")
DIAPER_TYPES = ("Pee", "Poop")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DISCLAIMER = (
    "Not medical advice. These are logged numbers, not a diagnosis. "
    "The parent and their clinician decide."
)
UNAVAILABLE_STATUS = {401, 404}
REDIRECT_STATUS = {301, 302, 303, 307, 308}

CSV_COLUMNS = (
    "event_id",
    "recorded_at",
    "type",
    "amount_ml",
    "left_sec",
    "right_sec",
    "memo",
    "details",
    "source_file",
    "first_seen_at",
    "last_seen_at",
)


class FeedError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def redact(text: str, secrets: list[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def resolve_tz(name: str | None) -> ZoneInfo:
    label = (name or os.environ.get("PIYOLOG_TZ") or DEFAULT_TZ).strip() or DEFAULT_TZ
    try:
        return ZoneInfo(label)
    except ZoneInfoNotFoundError as exc:
        raise FeedError(f"Unknown timezone: {label}", exit_code=2) from exc


def parse_dt(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now_iso(moment: datetime | None = None) -> str:
    current = moment or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_id_for(record: dict) -> str:
    event_id = record.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        return event_id
    return hashlib.md5(
        f"{record.get('type')}|{record.get('datetime')}".encode()
    ).hexdigest()


def amount_ml(record: dict):
    value = record.get("value")
    if isinstance(value, dict) and value.get("unit", "ml") == "ml":
        number = value.get("value")
        if isinstance(number, (int, float)) and not isinstance(number, bool):
            return number
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def details_text(record: dict):
    details = record.get("details")
    if isinstance(details, (dict, list)):
        return json.dumps(details, ensure_ascii=False)
    return details


def normalize_record(raw: dict, source_file: str, seen_at: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    if not isinstance(raw.get("datetime"), str) or not isinstance(raw.get("type"), str):
        return None
    try:
        parse_dt(raw["datetime"])
    except ValueError:
        return None
    return {
        "event_id": event_id_for(raw),
        "recorded_at": raw["datetime"],
        "type": raw["type"],
        "amount_ml": amount_ml(raw),
        "left_sec": raw.get("leftTime"),
        "right_sec": raw.get("rightTime"),
        "memo": raw.get("memo"),
        "details": details_text(raw),
        "raw": raw,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
        "source_file": source_file,
    }


def load_feed_url(
    env: dict | None = None,
    feed_url_file: str | None = None,
    cwd: str | Path | None = None,
) -> str:
    environment = os.environ if env is None else env
    root = Path(cwd or os.getcwd())
    if feed_url_file:
        return _url_from_file(Path(feed_url_file))
    direct = (environment.get("PIYOLOG_FEED_URL") or "").strip()
    if direct:
        return validate_feed_url(direct)
    file_from_env = (environment.get("PIYOLOG_FEED_URL_FILE") or "").strip()
    if file_from_env:
        return _url_from_file(Path(file_from_env))
    default_file = root / ".feed_url"
    if default_file.is_file():
        return _url_from_file(default_file)
    raise FeedError(
        "No feed URL found. Set PIYOLOG_FEED_URL or put the URL on one line in "
        ".feed_url (that file is gitignored). Do not commit the URL.",
        exit_code=2,
    )


def _url_from_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FeedError(
            f"Could not read the feed URL file ({path.name}). The contents were not printed.",
            exit_code=2,
        ) from exc
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return validate_feed_url(stripped)
    raise FeedError(
        f"{path.name} has no feed URL. Put the URL on one line. The file was not printed.",
        exit_code=2,
    )


def validate_feed_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path:
        raise FeedError(
            "The feed URL must be an https URL copied from the PiyoLog app. The value was not printed.",
            exit_code=2,
        )
    return url.strip()


def unavailable_message(status: int) -> str:
    return (
        f"The feed is unavailable (HTTP {status}). "
        "PiyoLog documents HTTP 404 with error code feed_unavailable for an expired feed, "
        "a revoked feed, a paused Premium feed, a deleted child, or a wrong URL. "
        "This tool treats HTTP 401 the same way. "
        "In the PiyoLog app, open Settings, then Data Feed. "
        "If the feed is expired or revoked, create a new feed and replace the local URL "
        "in PIYOLOG_FEED_URL or .feed_url. "
        "A feed can also return 404 for a short time right after you create it; "
        "wait about a minute and run fetch.py again before replacing it. "
        "A free feed expires 90 days after it is created. "
        "The URL was not printed."
    )


def _error_code(body: bytes) -> str | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    return None


def http_get(url: str, urlopen=None, timeout: int = 30) -> tuple[int, bytes]:
    opener = urlopen or _default_open
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    try:
        response = opener(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = b""
        if exc.fp is not None:
            try:
                body = exc.read()
            except Exception:
                body = b""
        return exc.code, body
    except urllib.error.URLError as exc:
        raise FeedError(
            "Network error while contacting the feed. The URL was not printed.",
            exit_code=5,
        ) from exc
    try:
        status = getattr(response, "status", None) or getattr(response, "code", 200)
        body = response.read()
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
    if len(body) > 20 * 1024 * 1024:
        raise FeedError(
            "The feed response was larger than 20 MB and was not saved. "
            "Create a feed with a shorter time range.",
            exit_code=5,
        )
    return status, body


def _default_open(request, timeout=30):
    opener = urllib.request.build_opener(_NoRedirect())
    return opener.open(request, timeout=timeout)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def interpret_response(status: int, body: bytes) -> dict:
    if status in REDIRECT_STATUS:
        raise FeedError(
            "The feed URL returned a redirect. Use the URL copied from the app, unchanged. "
            "The URL was not printed.",
            exit_code=4,
        )
    if status in UNAVAILABLE_STATUS:
        code = _error_code(body)
        message = unavailable_message(status)
        if code:
            message = f"{message} Server error code: {code}."
        raise FeedError(message, exit_code=4)
    if status == 413:
        raise FeedError(
            "The feed response is too large (HTTP 413). "
            "In the PiyoLog app, revoke this feed and create one with a shorter time range. "
            "The URL was not printed.",
            exit_code=5,
        )
    if status == 429:
        raise FeedError(
            "The feed asked us to slow down (HTTP 429). "
            "Wait several minutes before trying again. Twice a day is enough for a 24-hour feed. "
            "The URL was not printed.",
            exit_code=5,
        )
    if status != 200:
        raise FeedError(
            f"The feed request failed (HTTP {status}). The URL was not printed. "
            "If this keeps happening, wait and try again.",
            exit_code=5,
        )
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeedError(
            "The feed did not return JSON. The body was not printed.",
            exit_code=5,
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise FeedError(
            "The feed JSON did not contain a records array. Nothing was merged.",
            exit_code=5,
        )
    return payload


def snapshot_stamp(moment: datetime, tz: ZoneInfo) -> str:
    return moment.astimezone(tz).strftime("%Y%m%d_%H%M%S")


def unique_snapshot_path(data_dir: Path, stamp: str) -> Path:
    candidate = data_dir / f"{stamp}.json"
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = data_dir / f"{stamp}_{index}.json"
        if not candidate.exists():
            return candidate
    raise FeedError("Could not choose a snapshot filename.", exit_code=1)


class Store:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @property
    def jsonl_path(self) -> Path:
        return self.root / "records.jsonl"

    @property
    def csv_path(self) -> Path:
        return self.root / "records.csv"

    @property
    def sqlite_path(self) -> Path:
        return self.root / "records.sqlite"

    def read_jsonl(self) -> list[dict]:
        if not self.jsonl_path.is_file():
            return []
        rows = []
        for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
        return rows

    def upsert_records(self, incoming: list[dict], seen_at: str) -> tuple[int, int, int]:
        self.root.mkdir(parents=True, exist_ok=True)
        lock = open(self.root / ".store.lock", "a", encoding="utf-8")
        try:
            _lock_file(lock)
            existing = {row["event_id"]: row for row in self.read_jsonl()}
            inserted = 0
            updated = 0
            skipped = 0
            for record in incoming:
                if record is None:
                    skipped += 1
                    continue
                current = existing.get(record["event_id"])
                if current is None:
                    record["first_seen_at"] = seen_at
                    record["last_seen_at"] = seen_at
                    existing[record["event_id"]] = record
                    inserted += 1
                else:
                    record["first_seen_at"] = current.get("first_seen_at") or seen_at
                    record["last_seen_at"] = seen_at
                    existing[record["event_id"]] = record
                    updated += 1
            ordered = sorted(
                existing.values(),
                key=lambda row: (row.get("recorded_at") or "", row.get("event_id") or ""),
            )
            _atomic_write(self.jsonl_path, _render_jsonl(ordered))
            _atomic_write(self.csv_path, _render_csv(ordered))
            _write_sqlite(self.sqlite_path, ordered)
            return inserted, updated, skipped
        finally:
            _unlock_file(lock)
            lock.close()


def _lock_file(handle) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except ImportError:
        return


def _unlock_file(handle) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except ImportError:
        return


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        handle.write(text)
        handle.close()
        os.replace(handle.name, path)
    except Exception:
        handle.close()
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def _render_jsonl(rows: list[dict]) -> str:
    if not rows:
        return ""
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)


def _csv_safe(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _render_csv(rows: list[dict]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _csv_safe(row.get(column)) for column in CSV_COLUMNS})
    return buffer.getvalue()


def _write_sqlite(path: Path, rows: list[dict]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                event_id TEXT PRIMARY KEY,
                recorded_at TEXT NOT NULL,
                type TEXT NOT NULL,
                amount_ml REAL,
                left_sec REAL,
                right_sec REAL,
                memo TEXT,
                details TEXT,
                raw TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                source_file TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS records_type_recorded_at_idx
            ON records (type, recorded_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                source_file TEXT NOT NULL UNIQUE,
                generated_at TEXT,
                record_count INTEGER
            )
            """
        )
        connection.execute("DELETE FROM records")
        connection.executemany(
            """
            INSERT INTO records (
                event_id, recorded_at, type, amount_ml, left_sec, right_sec,
                memo, details, raw, first_seen_at, last_seen_at, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["event_id"],
                    row["recorded_at"],
                    row["type"],
                    row.get("amount_ml"),
                    row.get("left_sec"),
                    row.get("right_sec"),
                    row.get("memo"),
                    row.get("details"),
                    json.dumps(row.get("raw"), ensure_ascii=False),
                    row.get("first_seen_at") or "",
                    row.get("last_seen_at") or "",
                    row.get("source_file"),
                )
                for row in rows
            ],
        )
        connection.commit()
    finally:
        connection.close()


def log_fetch(path: Path, source_file: str, generated_at, record_count: int, fetched_at: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                source_file TEXT NOT NULL UNIQUE,
                generated_at TEXT,
                record_count INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO fetch_log (fetched_at, source_file, generated_at, record_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (source_file) DO NOTHING
            """,
            (fetched_at, source_file, generated_at, record_count),
        )
        connection.commit()
    finally:
        connection.close()


def records_from_payload(payload: dict, source_file: str, seen_at: str) -> tuple[list[dict], int]:
    incoming = []
    skipped = 0
    for raw in payload.get("records") or []:
        normalized = normalize_record(raw, source_file, seen_at)
        if normalized is None:
            skipped += 1
        else:
            incoming.append(normalized)
    return incoming, skipped


def load_snapshots(data_dir: Path) -> list[dict]:
    merged: dict[str, dict] = {}
    seen_at = utc_now_iso()
    for path in sorted(data_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            continue
        incoming, _skipped = records_from_payload(payload, path.name, seen_at)
        for record in incoming:
            merged[record["event_id"]] = record
    return list(merged.values())


def load_records(data_dir: Path, source: str = "auto") -> list[dict]:
    store = Store(data_dir)
    if source == "snapshots":
        return load_snapshots(data_dir)
    rows = store.read_jsonl()
    if source == "store":
        return rows
    if rows:
        return rows
    return load_snapshots(data_dir)


def fetch_and_store(
    url: str,
    data_dir: Path,
    tz: ZoneInfo,
    now: datetime | None = None,
    urlopen=None,
    backend: str = "local",
    database_url: str | None = None,
    sql_dir: Path | None = None,
) -> dict:
    moment = now or datetime.now(timezone.utc)
    status, body = http_get(url, urlopen=urlopen)
    payload = interpret_response(status, body)
    version = payload.get("schema_version")
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot = unique_snapshot_path(data_dir, snapshot_stamp(moment, tz))
    _atomic_write(
        snapshot,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    seen_at = utc_now_iso(moment)
    incoming, skipped = records_from_payload(payload, snapshot.name, seen_at)
    inserted, updated, upsert_skipped = Store(data_dir).upsert_records(incoming, seen_at)
    log_fetch(
        Store(data_dir).sqlite_path,
        snapshot.name,
        payload.get("generated_at"),
        len(payload.get("records") or []),
        seen_at,
    )
    result = {
        "snapshot": snapshot.name,
        "fetched": len(payload.get("records") or []),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped + upsert_skipped,
        "schema_version": version,
        "postgres": None,
    }
    if version not in (None, 1):
        result["schema_warning"] = (
            f"schema_version is {version}; this tool was written for version 1."
        )
    if backend == "postgres":
        apply_postgres_payload(
            payload,
            snapshot.name,
            database_url or os.environ.get("DATABASE_URL") or "",
            sql_dir or Path("sql"),
        )
        result["postgres"] = "updated"
    elif backend != "local":
        raise FeedError("Unknown backend. Use local or postgres.", exit_code=2)
    return result


def food_labels(memo) -> list[str]:
    if not isinstance(memo, str):
        return []
    labels = []
    for part in _split_foods(memo):
        text = " ".join(part.split())
        if text:
            labels.append(text)
    return labels


def _split_foods(memo: str) -> list[str]:
    import re

    return re.split(r"[,;\n]+", memo)


def _positive_seconds(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return 0.0


def _measurement(record: dict, unit: str):
    raw = record.get("raw")
    if not isinstance(raw, dict):
        return None
    value = raw.get("value")
    if not isinstance(value, dict) or value.get("unit") != unit:
        return None
    number = value.get("value")
    if isinstance(number, (int, float)) and not isinstance(number, bool):
        return float(number)
    return None


def sleep_stretches(records: list[dict]) -> list[tuple[datetime, datetime]]:
    pending = None
    stretches = []
    ordered = sorted(records, key=lambda row: (parse_dt(row["recorded_at"]), row.get("event_id") or ""))
    for record in ordered:
        moment = parse_dt(record["recorded_at"])
        kind = record.get("type")
        if kind == "Sleep":
            pending = moment
        elif kind == "WakeUp" and pending is not None and moment > pending:
            stretches.append((pending, moment))
            pending = None
    return stretches


def _day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start, start + timedelta(days=1)


def _overlap_minutes(start: datetime, end: datetime, day: date, tz: ZoneInfo) -> float:
    day_start, day_end = _day_bounds(day, tz)
    left = max(start, day_start)
    right = min(end, day_end)
    if right <= left:
        return 0.0
    return (right - left).total_seconds() / 60.0


def _as_number(value: float):
    if abs(value - round(value)) < 1e-9:
        return int(round(value))
    return round(value, 2)


def _local_date(record: dict, tz: ZoneInfo) -> date:
    return parse_dt(record["recorded_at"]).astimezone(tz).date()


def summarize(records: list[dict], tz: ZoneInfo, start: date, end: date) -> dict:
    if end < start:
        raise FeedError("--from is after --to.", exit_code=2)
    stretches = sleep_stretches(records)
    first_food: dict[str, tuple[date, str]] = {}
    for record in records:
        if record.get("type") != "Solid":
            continue
        seen = _local_date(record, tz)
        for label in food_labels(record.get("memo")):
            key = label.casefold()
            current = first_food.get(key)
            if current is None or seen < current[0]:
                first_food[key] = (seen, label)

    diaper_times = sorted(
        parse_dt(row["recorded_at"])
        for row in records
        if row.get("type") in DIAPER_TYPES
    )
    poop_times = sorted(
        parse_dt(row["recorded_at"]) for row in records if row.get("type") == "Poop"
    )

    days = []
    cursor = start
    while cursor <= end:
        in_day = [row for row in records if _local_date(row, tz) == cursor]
        milk = {kind: 0.0 for kind in MILK_TYPES}
        breast_seconds = 0.0
        temperatures = []
        other = {
            "Vomiting": 0,
            "Rash": 0,
            "Cough": 0,
            "Medicine": 0,
            "Hospital": 0,
            "Injury": 0,
        }
        solids: dict[str, dict] = {}
        for record in in_day:
            kind = record.get("type")
            if kind in milk and record.get("amount_ml") is not None:
                milk[kind] += float(record["amount_ml"])
            if kind == "BreastFeeding":
                breast_seconds += _positive_seconds(record.get("left_sec"))
                breast_seconds += _positive_seconds(record.get("right_sec"))
            if kind == "Temperature":
                reading = _measurement(record, "celsius")
                if reading is not None:
                    temperatures.append(reading)
            if kind in other:
                other[kind] += 1
            if kind == "Solid":
                for label in food_labels(record.get("memo")):
                    key = label.casefold()
                    slot = solids.get(key)
                    if slot is None:
                        seen, display = first_food.get(key, (cursor, label))
                        slot = {"food": display, "first_seen": seen.isoformat(), "count": 0}
                        solids[key] = slot
                    slot["count"] += 1
        overlapping = [
            (stretch_start, stretch_end)
            for stretch_start, stretch_end in stretches
            if _overlap_minutes(stretch_start, stretch_end, cursor, tz) > 0
        ]
        total_sleep = sum(_overlap_minutes(a, b, cursor, tz) for a, b in overlapping)
        longest = 0.0
        if overlapping:
            longest = max((b - a).total_seconds() / 60.0 for a, b in overlapping)
        days.append(
            {
                "date": cursor.isoformat(),
                "record_count": len(in_day),
                "milk_ml": {kind: _as_number(amount) for kind, amount in milk.items()},
                "breastfeeding_minutes": _as_number(breast_seconds / 60.0),
                "sleep": {
                    "total_minutes": _as_number(total_sleep),
                    "longest_stretch_minutes": _as_number(longest),
                    "stretch_count": len(overlapping),
                },
                "diapers": {
                    "pee": sum(1 for row in in_day if row.get("type") == "Pee"),
                    "poop": sum(1 for row in in_day if row.get("type") == "Poop"),
                    "longest_gap_minutes": _gap_ending_on(diaper_times, cursor, tz),
                    "poop_longest_gap_minutes": _gap_ending_on(poop_times, cursor, tz),
                },
                "solids": sorted(solids.values(), key=lambda item: item["food"].casefold()),
                "temperature_max_c": _as_number(max(temperatures)) if temperatures else None,
                "other_counts": other,
            }
        )
        cursor += timedelta(days=1)
    return {
        "timezone": getattr(tz, "key", str(tz)),
        "from": start.isoformat(),
        "to": end.isoformat(),
        "record_count": len(records),
        "days": days,
        "disclaimer": DISCLAIMER,
        "notes": [
            "Feed timestamps are UTC and are grouped by the timezone above.",
            "Milk millilitres are summed only when the feed sends a positive ml value. Breastfeeding duration is not converted into millilitres.",
            "Sleep total is the portion of each Sleep-to-WakeUp stretch that falls on that local day. Longest stretch is the full stretch, including time on neighboring days. An unpaired Sleep or WakeUp is not counted.",
            "Diaper gap is the longest interval that ends at a pee or poop logged on that day. Poop gap uses poop records only.",
            "Solid foods come from the memo text. first_seen is the earliest local date that food appears in the loaded records, which may be before this range.",
        ],
    }


def _gap_ending_on(moments: list[datetime], day: date, tz: ZoneInfo):
    best = None
    for previous, current in zip(moments, moments[1:]):
        if current.astimezone(tz).date() != day:
            continue
        minutes = (current - previous).total_seconds() / 60.0
        if best is None or minutes > best:
            best = minutes
    if best is None:
        return None
    return _as_number(best)


def render_json(summary: dict) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_markdown(summary: dict) -> str:
    lines = [
        f"# PiyoLog summary ({summary['timezone']})",
        "",
        f"{summary['from']} to {summary['to']}. {summary['disclaimer']}",
        "",
    ]
    for day in summary["days"]:
        milk = day["milk_ml"]
        diapers = day["diapers"]
        sleep = day["sleep"]
        lines.append(f"## {day['date']}")
        lines.append("")
        lines.append(
            "- Feeding: formula {formula} ml, expressed breast milk {expressed} ml, "
            "breastfeeding recorded {breast} ml, pumping {pumping} ml, "
            "breastfeeding time {minutes} minutes.".format(
                formula=milk["Formula"],
                expressed=milk["ExpressedBreastMilk"],
                breast=milk["BreastFeeding"],
                pumping=milk["Pumping"],
                minutes=day["breastfeeding_minutes"],
            )
        )
        lines.append(
            "- Sleep: total {total} minutes on this date, longest stretch {longest} minutes "
            "({count} paired stretches overlapping this date).".format(
                total=sleep["total_minutes"],
                longest=sleep["longest_stretch_minutes"],
                count=sleep["stretch_count"],
            )
        )
        gap = "n/a" if diapers["longest_gap_minutes"] is None else f"{diapers['longest_gap_minutes']} minutes"
        poop_gap = (
            "n/a"
            if diapers["poop_longest_gap_minutes"] is None
            else f"{diapers['poop_longest_gap_minutes']} minutes"
        )
        lines.append(
            f"- Diaper: pee {diapers['pee']}, poop {diapers['poop']}, "
            f"longest diaper gap ending today {gap}, longest poop gap ending today {poop_gap}."
        )
        if day["solids"]:
            foods = ", ".join(
                f"{item['food']} (first seen {item['first_seen']}, count {item['count']})"
                for item in day["solids"]
            )
            lines.append(f"- Solids: {foods}.")
        else:
            lines.append("- Solids: none logged.")
        if day["temperature_max_c"] is None:
            lines.append("- Temperature: none logged.")
        else:
            lines.append(f"- Temperature max: {day['temperature_max_c']} C.")
        flags = [f"{name} {count}" for name, count in day["other_counts"].items() if count]
        if flags:
            lines.append("- Other logged counts: " + ", ".join(flags) + ".")
        lines.append("")
    lines.append(summary["disclaimer"])
    lines.append("")
    return "\n".join(lines)


def sql_json(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("'", "''")


def build_sql(records: dict[str, dict], logs: list[dict]) -> tuple[str, str]:
    rows = list(records.values())
    upsert = f"""INSERT INTO public.piyolog_records (event_id, recorded_at, type, amount_ml, left_sec, right_sec, memo, details, raw, source_file)
SELECT x->>'event_id', (x->>'recorded_at')::timestamptz, x->>'type', (x->>'amount_ml')::numeric, round((x->>'left_sec')::numeric)::int, round((x->>'right_sec')::numeric)::int, x->>'memo', x->>'details', x->'raw', x->>'source_file'
FROM jsonb_array_elements('{sql_json(rows)}'::jsonb) AS x
ON CONFLICT (event_id) DO UPDATE SET recorded_at=EXCLUDED.recorded_at, type=EXCLUDED.type, amount_ml=EXCLUDED.amount_ml, left_sec=EXCLUDED.left_sec, right_sec=EXCLUDED.right_sec, memo=EXCLUDED.memo, details=EXCLUDED.details, raw=EXCLUDED.raw, source_file=EXCLUDED.source_file, last_seen_at=now();
"""
    fetch_log = f"""INSERT INTO public.piyolog_fetch_log (source_file, generated_at, record_count)
SELECT x->>'source_file', (x->>'generated_at')::timestamptz, (x->>'record_count')::int FROM jsonb_array_elements('{sql_json(logs)}'::jsonb) AS x
ON CONFLICT (source_file) DO NOTHING;
"""
    return upsert, fetch_log


def sql_rows_from_payload(payload: dict, source_file: str) -> tuple[dict, dict]:
    records = {}
    raw_records = payload.get("records") or []
    for raw in raw_records:
        normalized = normalize_record(raw, source_file, "")
        if normalized is None:
            continue
        records[normalized["event_id"]] = {
            "event_id": normalized["event_id"],
            "recorded_at": normalized["recorded_at"],
            "type": normalized["type"],
            "amount_ml": normalized["amount_ml"],
            "left_sec": normalized["left_sec"],
            "right_sec": normalized["right_sec"],
            "memo": normalized["memo"],
            "details": normalized["details"],
            "raw": raw,
            "source_file": source_file,
        }
    log = {
        "source_file": source_file,
        "generated_at": payload.get("generated_at"),
        "record_count": len(raw_records) if isinstance(raw_records, list) else 0,
    }
    return records, log


def collect_snapshot_files(paths: list[Path]) -> tuple[dict, list]:
    records: dict[str, dict] = {}
    logs = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FeedError(f"{path.name} is not valid JSON.", exit_code=2) from exc
        if not isinstance(payload, dict):
            payload = {"records": []}
        rows, log = sql_rows_from_payload(payload, path.name)
        logs.append(log)
        records.update(rows)
    return records, logs


def write_sql_files(sql_dir: Path, upsert: str, fetch_log: str) -> None:
    sql_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(sql_dir / "upsert.sql", upsert)
    _atomic_write(sql_dir / "fetchlog.sql", fetch_log)


def split_sql(text: str) -> list[str]:
    return [chunk.strip() for chunk in text.split(";") if chunk.strip()]


def apply_postgres_payload(payload: dict, source_file: str, database_url: str, sql_dir: Path) -> None:
    if not database_url.strip():
        raise FeedError(
            "Postgres was requested but DATABASE_URL is empty. Local files were saved. "
            "Set DATABASE_URL or run without --backend postgres.",
            exit_code=6,
        )
    records, log = sql_rows_from_payload(payload, source_file)
    upsert, fetch_log = build_sql(records, [log])
    write_sql_files(sql_dir, upsert, fetch_log)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = split_sql(schema) + split_sql(upsert) + split_sql(fetch_log)
    apply_sql(database_url.strip(), statements)


def apply_sql(database_url: str, statements: list[str]) -> str:
    try:
        driver = _apply_with_python_driver(database_url, statements)
    except FeedError:
        raise
    except Exception as exc:
        raise FeedError(
            "Postgres update failed. Local files were saved. "
            + redact(f"{type(exc).__name__}", [database_url]),
            exit_code=6,
        ) from exc
    if driver:
        return driver
    if shutil.which("psql"):
        _apply_with_psql(database_url, statements)
        return "psql"
    raise FeedError(
        "Postgres was requested, and local files were saved, but neither psycopg nor psql is installed. "
        "Install one of them, or run without --backend postgres.",
        exit_code=6,
    )


def _apply_with_python_driver(database_url: str, statements: list[str]) -> str | None:
    try:
        import psycopg
    except ImportError:
        psycopg = None
    if psycopg is not None:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()
        return "psycopg"
    try:
        import psycopg2
    except ImportError:
        psycopg2 = None
    if psycopg2 is None:
        return None
    connection = psycopg2.connect(database_url)
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()
    return "psycopg2"


def _apply_with_psql(database_url: str, statements: list[str]) -> None:
    script = ";\n".join(statements) + ";\n"
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sql", delete=False)
    path = handle.name
    try:
        handle.write(script)
        handle.close()
        completed = subprocess.run(
            ["psql", database_url, "-v", "ON_ERROR_STOP=1", "-f", path],
            capture_output=True,
            text=True,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if completed.returncode != 0:
        detail = redact((completed.stderr or completed.stdout or "").strip(), [database_url])
        raise FeedError(
            "psql failed. Local files were saved. " + (detail or "No details."),
            exit_code=6,
        )


def window_from_days(days: int, tz: ZoneInfo, now: datetime | None = None) -> tuple[date, date]:
    if days < 1:
        raise FeedError("--days must be at least 1.", exit_code=2)
    moment = now or datetime.now(timezone.utc)
    today = moment.astimezone(tz).date()
    return today - timedelta(days=days - 1), today


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FeedError(f"Dates must look like YYYY-MM-DD, not {value!r}.", exit_code=2) from exc


def reject_url_on_argv(argv: list[str]) -> None:
    for arg in argv:
        if "://" in arg:
            raise FeedError(
                "Refusing to run: do not pass the feed URL on the command line. "
                "Use PIYOLOG_FEED_URL or .feed_url.",
                exit_code=2,
            )
