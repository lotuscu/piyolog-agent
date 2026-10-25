"""Regression checks use synthetic data only; no network or database required."""
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
import piyolog as p


class RegressionTests(unittest.TestCase):
    def test_missing_amount_is_not_zero_or_complete_total(self):
        rows, _ = p.records_from_payload({'records': [
            {'event_id': 'a', 'datetime': '2026-10-24T03:00:00Z', 'type': 'Formula'},
            {'event_id': 'b', 'datetime': '2026-10-24T04:00:00Z', 'type': 'Formula',
             'value': {'value': 100, 'unit': 'ml'}},
        ]}, 'test.json', '2026-10-24T05:00:00Z')
        summary = p.summarize(rows, p.resolve_tz('Asia/Tokyo'), date(2026,10,24), date(2026,10,24))
        day = summary['days'][0]
        self.assertIsNone(day['milk_ml']['Formula'])
        self.assertEqual(day['milk_known_ml']['Formula'], 100)
        self.assertEqual(day['milk_missing_amount_count']['Formula'], 1)
        self.assertIn('unknown total', p.render_markdown(summary))

    def test_coverage_uses_ranges_including_empty_successful_feeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, start, end in [
                ('a', '2026-10-23T15:00:00Z', '2026-10-24T03:00:00Z'),
                ('b', '2026-10-24T02:00:00Z', '2026-10-24T15:00:00Z'),
            ]:
                (root / (name+'.json')).write_text(json.dumps({
                    'generated_at': end, 'range': {'from':start,'to':end}, 'records':[]}))
            coverage = p.load_coverage(root, datetime(2026,10,26,tzinfo=timezone.utc))
            tz = p.resolve_tz('Asia/Tokyo')
            self.assertEqual(p.day_coverage(date(2026,10,24),tz,coverage),'complete')
            self.assertEqual(p.day_coverage(date(2026,10,25),tz,coverage),'missing')
            self.assertEqual(coverage['freshness'],'stale')
            coverage['intervals'].pop()
            self.assertEqual(p.day_coverage(date(2026,10,24),tz,coverage),'partial')
            self.assertEqual(p.day_coverage(date(2026,10,24),tz,None),'unknown')

    def test_empty_summary_warns_in_markdown_and_json(self):
        summary = p.summarize([],p.resolve_tz('UTC'),date(2026,10,24),date(2026,10,24))
        self.assertIsNone(summary['days'][0]['milk_ml']['Formula'])
        self.assertEqual(summary['days'][0]['coverage'],'unknown')
        self.assertIn('No records available',p.render_markdown(summary))

    def test_restored_snapshots_survive_next_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = {'records':[{'event_id':'a','type':'Pee','datetime':'2026-10-23T00:00:00Z'}]}
            new = {'records':[{'event_id':'b','type':'Poop','datetime':'2026-10-24T00:00:00Z'}]}
            (root/'20261023.json').write_text(json.dumps(old))
            with patch.object(p,'http_get',return_value=(200,json.dumps(new).encode())):
                result = p.fetch_and_store('https://example.invalid/feed',root,p.resolve_tz('UTC'))
            self.assertEqual(result['inserted'],1)
            self.assertEqual({row['event_id'] for row in p.load_records(root)}, {'a','b'})
            self.assertFalse((root/'records.sqlite').exists())

    def test_postgres_receives_intact_semicolon_and_quote_memo(self):
        payload = {'records':[{'event_id':'a','type':'Memo','datetime':'2026-10-24T00:00:00Z',
                              'memo':"milk; o'clock; slept"}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(p,'apply_sql') as apply:
            p.apply_postgres_payload(payload,'test.json','postgresql://example.invalid/test',Path(tmp))
        statements = apply.call_args.args[1]
        upserts = [statement for statement in statements if statement.startswith('INSERT INTO public.piyolog_records')]
        self.assertEqual(len(upserts),1)
        self.assertIn("milk; o''clock; slept",upserts[0])
        self.assertIn('ON CONFLICT',upserts[0])

    def test_dst_days_use_elapsed_time(self):
        tz = p.resolve_tz('America/Los_Angeles')
        for day, start, end, expected in [
            (date(2026,3,8),'2026-03-07T20:00:00Z','2026-03-09T12:00:00Z',1380),
            (date(2026,11,1),'2026-10-31T20:00:00Z','2026-11-02T12:00:00Z',1500),
        ]:
            self.assertEqual(p._overlap_minutes(p.parse_dt(start),p.parse_dt(end),day,tz),expected)


if __name__ == '__main__':
    unittest.main()
