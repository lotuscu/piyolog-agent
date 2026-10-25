#!/usr/bin/env python3
"""Stdlib tests against the synthetic fixture. No network and no real feed URL."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import piyolog
import fetch
import summarize
import to_postgres_sql

FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_feed.json"
TZ = piyolog.resolve_tz("Asia/Tokyo")


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def normalized_fixture(seen_at: str = "2026-09-09T00:00:00Z") -> list[dict]:
    payload = load_fixture()
    records, skipped = piyolog.records_from_payload(payload, FIXTURE.name, seen_at)
    if skipped:
        raise AssertionError(f"fixture skipped {skipped} records")
    return records


class EventIdTests(unittest.TestCase):
    def test_missing_event_id_is_rejected_instead_of_guessed(self):
        with self.assertRaises(piyolog.FeedError):
            piyolog.event_id_for({"datetime": "2026-09-08T22:00:00Z", "type": "Pee"})

    def test_amount_ignores_celsius_and_accepts_ml(self):
        self.assertIsNone(
            piyolog.amount_ml({"value": {"value": 37.4, "unit": "celsius"}})
        )
        self.assertEqual(piyolog.amount_ml({"value": {"value": 120, "unit": "ml"}}), 120)
        self.assertIsNone(piyolog.amount_ml({"value": True}))


class StoreTests(unittest.TestCase):
    def test_dedup_keeps_first_seen_and_updates_memo(self):
        with self._temp() as tmp:
            root = Path(tmp)
            store = piyolog.Store(root)
            first, _skipped = piyolog.records_from_payload(
                load_fixture(), "one.json", "2026-09-09T00:00:00Z"
            )
            inserted, updated = store.upsert_records(first, "2026-09-09T00:00:00Z")
            self.assertEqual((inserted, updated), (len(first), 0))
            changed = json.loads(json.dumps(load_fixture()))
            changed["records"][1]["memo"] = "updated note"
            second, _skipped = piyolog.records_from_payload(
                changed, "two.json", "2026-09-09T01:00:00Z"
            )
            inserted, updated = store.upsert_records(second, "2026-09-09T01:00:00Z")
            self.assertEqual(inserted, 0)
            self.assertEqual(updated, len(second))
            rows = store.read_jsonl()
            self.assertEqual(len(rows), len(first))
            formula = next(row for row in rows if row["event_id"] == "syn-formula-1")
            self.assertEqual(formula["memo"], "updated note")
            self.assertEqual(formula["first_seen_at"], "2026-09-09T00:00:00Z")
            self.assertEqual(formula["last_seen_at"], "2026-09-09T01:00:00Z")
            csv_text = (root / "records.csv").read_text(encoding="utf-8")
            self.assertEqual(csv_text.count("\n"), len(rows) + 1)
            self.assertIn("updated note", csv_text)
            self.assertFalse((root / "records.sqlite").exists())

    def _temp(self):
        return tempfile.TemporaryDirectory()


class SummaryTests(unittest.TestCase):
    def test_per_day_stats_in_tokyo(self):
        summary = piyolog.summarize(
            normalized_fixture(),
            TZ,
            date(2026, 9, 8),
            date(2026, 9, 9),
        )
        self.assertEqual(summary["timezone"], "Asia/Tokyo")
        by_date = {day["date"]: day for day in summary["days"]}
        day8 = by_date["2026-09-08"]
        day9 = by_date["2026-09-09"]

        self.assertEqual(day8["milk_ml"]["Formula"], 120)
        self.assertEqual(day8["milk_ml"]["BreastFeeding"], 80)
        self.assertEqual(day8["milk_ml"]["ExpressedBreastMilk"], 0)
        self.assertEqual(day8["breastfeeding_minutes"], 9)
        self.assertEqual(day8["sleep"]["total_minutes"], 300)
        self.assertEqual(day8["sleep"]["longest_stretch_minutes"], 360)
        self.assertEqual(day8["diapers"]["pee"], 1)
        self.assertEqual(day8["diapers"]["poop"], 1)
        self.assertEqual(day8["diapers"]["longest_gap_minutes"], 120)
        self.assertIsNone(day8["diapers"]["poop_longest_gap_minutes"])
        self.assertEqual(day8["temperature_max_c"], 37.4)
        foods = {item["food"]: item for item in day8["solids"]}
        self.assertEqual(foods["rice porridge"]["first_seen"], "2026-09-01")
        self.assertEqual(foods["steamed carrot"]["first_seen"], "2026-09-08")

        self.assertEqual(day9["milk_ml"]["ExpressedBreastMilk"], 40)
        self.assertEqual(day9["milk_ml"]["Formula"], 0)
        self.assertEqual(day9["breastfeeding_minutes"], 0)
        self.assertEqual(day9["sleep"]["total_minutes"], 180)
        self.assertEqual(day9["sleep"]["longest_stretch_minutes"], 360)
        self.assertEqual(day9["diapers"]["pee"], 1)
        self.assertEqual(day9["diapers"]["poop"], 0)
        self.assertEqual(day9["diapers"]["longest_gap_minutes"], 840)
        self.assertEqual(day9["solids"], [])

        markdown = piyolog.render_markdown(summary)
        self.assertIn("Feeding:", markdown)
        self.assertIn("Sleep:", markdown)
        self.assertIn("Diaper:", markdown)
        self.assertIn("Not medical advice", markdown)
        rendered = piyolog.render_json(summary)
        self.assertEqual(json.loads(rendered)["days"][0]["date"], "2026-09-08")

    def test_food_casefold_groups_labels(self):
        records = [
            {
                "event_id": "a",
                "recorded_at": "2026-09-01T00:00:00Z",
                "type": "Solid",
                "memo": "Rice Porridge",
                "amount_ml": None,
                "left_sec": None,
                "right_sec": None,
                "details": None,
                "raw": {},
            },
            {
                "event_id": "b",
                "recorded_at": "2026-09-02T00:00:00Z",
                "type": "Solid",
                "memo": "rice porridge",
                "amount_ml": None,
                "left_sec": None,
                "right_sec": None,
                "details": None,
                "raw": {},
            },
        ]
        summary = piyolog.summarize(records, TZ, date(2026, 9, 2), date(2026, 9, 2))
        solids = summary["days"][0]["solids"]
        self.assertEqual(len(solids), 1)
        self.assertEqual(solids[0]["first_seen"], "2026-09-01")
        self.assertEqual(solids[0]["food"], "Rice Porridge")


class FetchTests(unittest.TestCase):
    def test_404_and_401_hide_the_url(self):
        secret = "super-secret-token"
        url = "https://feed.example.test/v1/feed/24h/demo/" + secret
        for status in (404, 401):
            def urlopen(request, timeout=30, status=status):
                raise urllib.error.HTTPError(
                    url,
                    status,
                    "nope",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":{"code":"feed_unavailable","message":"hidden"}}'),
                )

            with self.assertRaises(piyolog.FeedError) as caught:
                piyolog.fetch_and_store(
                    url,
                    Path("/tmp/does-not-matter"),
                    TZ,
                    urlopen=urlopen,
                )
            message = str(caught.exception)
            self.assertNotIn(secret, message)
            self.assertNotIn("feed.example.test", message)
            self.assertIn("90 days", message)
            self.assertIn("was not printed", message)
            self.assertEqual(caught.exception.exit_code, 4)

    def test_fetch_writes_store_without_printing_url(self):
        secret = "another-secret-token"
        url = "https://feed.example.test/private/" + secret
        body = FIXTURE.read_bytes()

        class Response:
            status = 200

            def read(self, size=-1):
                return body[:size] if size >= 0 else body

            def close(self):
                return None

        def urlopen(request, timeout=30):
            self.assertIn(secret, request.full_url)
            return Response()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = piyolog.fetch_and_store(
                url,
                root,
                TZ,
                now=datetime(2026, 9, 9, 0, 30, tzinfo=timezone.utc),
                urlopen=urlopen,
            )
            self.assertEqual(result["fetched"], 13)
            self.assertEqual(result["inserted"], 13)
            self.assertTrue((root / result["snapshot"]).is_file())
            self.assertEqual(len(piyolog.Store(root).read_jsonl()), 13)
            again = piyolog.fetch_and_store(
                url,
                root,
                TZ,
                now=datetime(2026, 9, 9, 0, 31, tzinfo=timezone.utc),
                urlopen=urlopen,
            )
            self.assertEqual(again["inserted"], 0)
            self.assertEqual(again["updated"], 13)
            summary = piyolog.summarize(
                piyolog.load_records(root),
                TZ,
                date(2026, 9, 8),
                date(2026, 9, 8),
            )
            self.assertEqual(summary["days"][0]["milk_ml"]["Formula"], 120)

    def test_cli_refuses_url_argument(self):
        code = piyolog_fetch_main(["https://feed.example.test/secret"])
        self.assertEqual(code, 2)


class SqlTests(unittest.TestCase):
    def test_upsert_is_idempotent_and_escapes_quotes(self):
        payload = {
            "generated_at": "2026-09-09T00:00:00Z",
            "records": [
                {
                    "event_id": "syn-quote",
                    "datetime": "2026-09-08T00:00:00Z",
                    "type": "Memo",
                    "memo": "o'clock",
                }
            ],
        }
        records, log = piyolog.sql_rows_from_payload(payload, "sample.json")
        upsert, fetch_log = piyolog.build_sql(records, [log])
        self.assertIn("ON CONFLICT (event_id) DO UPDATE", upsert)
        self.assertIn("last_seen_at=now()", upsert)
        self.assertIn("o''clock", upsert)
        self.assertIn("ON CONFLICT (source_file) DO NOTHING", fetch_log)
        self.assertTrue(upsert.strip().endswith(";"))

    def test_missing_database_url_does_not_echo_a_secret(self):
        with self.assertRaises(piyolog.FeedError) as caught:
            piyolog.apply_postgres_payload(
                {"records": [], "generated_at": "2026-09-09T00:00:00Z"},
                "sample.json",
                "   ",
                Path("/tmp"),
            )
        self.assertIn("DATABASE_URL", str(caught.exception))
        self.assertNotIn("://", str(caught.exception))
        self.assertEqual(caught.exception.exit_code, 6)


def piyolog_fetch_main(argv):
    stderr = io.StringIO()
    previous = sys.stderr
    sys.stderr = stderr
    try:
        code = fetch.main(argv)
    finally:
        sys.stderr = previous
    message = stderr.getvalue()
    if "://" in message:
        raise AssertionError(message)
    return code


class CliDefaultsTests(unittest.TestCase):
    def test_cli_defaults_are_anchored_to_the_repo_directory(self):
        # An agent may run these scripts from any working directory (for
        # example a scheduled job). Defaults must not depend on the cwd.
        for module in (fetch, summarize, to_postgres_sql):
            args = module.build_parser().parse_args([])
            data_dir = Path(args.data_dir)
            self.assertTrue(data_dir.is_absolute(), module.__name__)
            self.assertEqual(data_dir, Path(module.__file__).resolve().parent / "data")

    def test_markdown_rounds_fractional_minutes(self):
        summary = piyolog.summarize(
            normalized_fixture(), TZ, date(2026, 9, 8), date(2026, 9, 8)
        )
        summary["days"][0]["breastfeeding_minutes"] = 49.71
        markdown = piyolog.render_markdown(summary)
        self.assertIn("breastfeeding time 50 minutes", markdown)
        self.assertNotIn("49.71", markdown)
        # JSON keeps the exact value.
        rendered = json.loads(piyolog.render_json(summary))
        self.assertEqual(rendered["days"][0]["breastfeeding_minutes"], 49.71)


if __name__ == "__main__":
    unittest.main()
