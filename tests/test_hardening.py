"""Boundary and failure-path regressions; all records and credentials are synthetic."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import piyolog as p
import summarize


class HardeningTests(unittest.TestCase):
    def records(self, raw):
        return p.records_from_payload({'records': raw}, 'synthetic.json', '2026-10-25T00:00:00Z')[0]

    def test_long_sleep_excluded_and_visible_in_both_formats(self):
        rows = self.records([
            {'event_id':'s', 'type':'Sleep', 'datetime':'2026-10-23T22:00:00Z'},
            {'event_id':'w', 'type':'WakeUp', 'datetime':'2026-10-25T06:00:00Z'},
        ])
        summary = p.summarize(rows,p.resolve_tz('UTC'),date(2026,10,24),date(2026,10,24))
        self.assertEqual(summary['days'][0]['sleep']['total_minutes'],0)
        self.assertEqual(summary['days'][0]['sleep']['excluded_long_pairs'],1)
        self.assertIn('Totals are incomplete',p.render_markdown(summary))
        self.assertIn('excluded_long_pairs',p.render_json(summary))
        allowed = p.summarize(rows,p.resolve_tz('UTC'),date(2026,10,24),date(2026,10,24),max_sleep_hours=36)
        self.assertEqual(allowed['days'][0]['sleep']['total_minutes'],1440)

    def test_normal_overnight_sleep_is_kept(self):
        rows = self.records([
            {'event_id':'s','type':'Sleep','datetime':'2026-10-24T22:00:00Z'},
            {'event_id':'w','type':'WakeUp','datetime':'2026-10-25T06:00:00Z'},
        ])
        summary=p.summarize(rows,p.resolve_tz('UTC'),date(2026,10,24),date(2026,10,25))
        self.assertEqual([d['sleep']['total_minutes'] for d in summary['days']], [120,360])

    def test_invalid_cli_values_fail(self):
        for argv in [['--days','0'],['--days','-1'],['--max-sleep-hours','0'],['--max-sleep-hours','nan'],['--max-sleep-hours','inf']]:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(summarize.main(argv),2)

    def test_missing_ids_never_merge_or_replace_existing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=self.records([{'event_id':'kept','type':'Pee','datetime':'2026-10-24T00:00:00Z'}])
            p.Store(root).upsert_records(original,'2026-10-25T00:00:00Z')
            before=(root/'records.jsonl').read_bytes()
            raw={'type':'Pee','datetime':'2026-10-25T00:00:00Z'}
            payload={'records':[raw,raw]}
            with patch.object(p,'http_get',return_value=(200,json.dumps(payload).encode())):
                with self.assertRaises(p.FeedError):
                    p.fetch_and_store('https://example.invalid/feed',root,p.resolve_tz('UTC'))
            self.assertEqual((root/'records.jsonl').read_bytes(),before)
            snapshots=list(root.glob('*.json'))
            self.assertEqual(len(snapshots),1)
            self.assertEqual(len(json.loads(snapshots[0].read_text())['records']),2)

    def test_response_is_bounded_and_closed(self):
        response=MagicMock()
        response.status=200
        response.read.return_value=b'x'*17
        with patch.object(p,'MAX_RESPONSE_BYTES',16):
            with self.assertRaises(p.FeedError):
                p.http_get('https://example.invalid/feed',urlopen=lambda *a,**k:response)
        response.read.assert_called_once_with(17)
        response.close.assert_called_once()

    def test_error_body_is_bounded_and_closed(self):
        body=io.BytesIO(b'x'*100000)
        error=urllib.error.HTTPError('https://example.invalid/feed',500,'synthetic',{},body)
        with patch.object(p,'_default_open',side_effect=error):
            status,data=p.http_get('https://example.invalid/feed')
        self.assertEqual(status,500)
        self.assertEqual(len(data),65536)
        self.assertTrue(body.closed)

    def test_corrupt_store_recovers_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            a={'event_id':'a','type':'Pee','datetime':'2026-10-24T00:00:00Z','memo':'older'}
            b={'event_id':'b','type':'Poop','datetime':'2026-10-24T01:00:00Z'}
            (root/'snapshot.json').write_text(json.dumps({'records':[a,b]}))
            a['memo']='newer canonical'
            valid=self.records([a])[0]
            original=json.dumps(valid).encode()+b'\n{broken\n\xff\n'
            (root/'records.jsonl').write_bytes(original)
            with self.assertWarns(RuntimeWarning):
                rows=p.load_records(root)
            self.assertEqual({r['event_id'] for r in rows},{'a','b'})
            self.assertEqual(next(r for r in rows if r['event_id']=='a')['memo'],'newer canonical')
            backups=list(root.glob('records.corrupt.*.bak'))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_bytes(),original)
            self.assertEqual(backups[0].stat().st_mode & 0o777,0o600)
            p.Store(root).upsert_records(self.records([{'event_id':'c','type':'Pee','datetime':'2026-10-25T00:00:00Z'}]),'2026-10-25T01:00:00Z')
            self.assertEqual(len(p.load_records(root)),3)
            self.assertEqual(len(list(root.glob('records.corrupt.*.bak'))),1)
            coverage=p.load_coverage(root)
            self.assertTrue(coverage['store_repair_warning'])
            summary=p.summarize(p.load_records(root),p.resolve_tz('UTC'),date(2026,10,24),date(2026,10,24),coverage=coverage)
            self.assertIn('Store recovery warning',p.render_markdown(summary))

    def test_corrupt_store_without_snapshots_retains_valid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            row=self.records([{'event_id':'a','type':'Pee','datetime':'2026-10-24T00:00:00Z'}])[0]
            (root/'records.jsonl').write_text(json.dumps(row)+'\n[]\n{"event_id": "bad"}\n')
            with self.assertWarns(RuntimeWarning):
                self.assertEqual(p.load_records(root),[row])

    def test_breast_and_pumping_optional_volume_does_not_mask_bottle_warning(self):
        rows=self.records([
            {'event_id':kind,'type':kind,'datetime':'2026-10-24T00:00:00Z','leftTime':300}
            for kind in ['BreastFeeding','Pumping','Formula','ExpressedBreastMilk']
        ])
        summary=p.summarize(rows,p.resolve_tz('UTC'),date(2026,10,24),date(2026,10,24))
        md=p.render_markdown(summary)
        self.assertEqual(md.count('unknown total'),2)
        self.assertIn('optional amount not recorded',md)
        self.assertIn('not baby intake',md)
        self.assertEqual(summary['days'][0]['breastfeeding_minutes'],5)

    def test_psql_secret_not_in_argv_or_diagnostics(self):
        secret='postgresql://synthetic:synthetic-password@localhost/test'
        with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
            p._apply_with_psql(secret,['SELECT 1;'])
        args=run.call_args.args[0]
        self.assertNotIn(secret,' '.join(args))
        self.assertEqual(run.call_args.kwargs['env']['PGDATABASE'],secret)
        self.assertEqual(run.call_args.kwargs['input'],'SELECT 1;')
        self.assertIn('--single-transaction',args)
        with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stderr=secret)):
            with self.assertRaises(p.FeedError) as caught:
                p._apply_with_psql(secret,['SELECT 1;'])
        self.assertNotIn('synthetic-password',str(caught.exception))

    def test_psycopg_receives_whole_schema_and_uses_transaction_context(self):
        driver=MagicMock()
        connection=driver.connect.return_value.__enter__.return_value
        cursor=connection.cursor.return_value.__enter__.return_value
        statements=[p.SCHEMA_PATH.read_text(),"SELECT 'a;b';"]
        with patch.object(p,'psycopg',driver):
            self.assertIsNone(p.apply_sql('synthetic',statements))
        self.assertEqual([call.args[0] for call in cursor.execute.call_args_list],statements)
        driver.connect.return_value.__exit__.assert_called_once()
