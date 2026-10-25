#!/usr/bin/env python3
"""Build upsert SQL for Neon from piyolog snapshot files (no credentials involved).
Usage: python3 to_neon_sql.py [file.json ...]   (default: latest file in data/)
       python3 to_neon_sql.py --all
       python3 to_neon_sql.py --data-dir DIR --sql-dir DIR [file.json ...|--all]

Data directory: --data-dir, else PIYOLOG_DATA_DIR, else /workspace/piyolog/data.
SQL directory:  --sql-dir,  else PIYOLOG_SQL_DIR,  else /workspace/piyolog/sql.
Writes <sql-dir>/upsert.sql and <sql-dir>/fetchlog.sql;
then run them via Neon MCP run_sql_transaction with
sql_statements = ["$file:<sql-dir>/upsert.sql", "$file:<sql-dir>/fetchlog.sql"]
"""
import json, glob, os, sys, hashlib

def _parse_cli(argv):
    data_dir = os.environ.get('PIYOLOG_DATA_DIR') or '/workspace/piyolog/data'
    sql_dir = os.environ.get('PIYOLOG_SQL_DIR') or '/workspace/piyolog/sql'
    positional = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--data-dir', '--sql-dir'):
            if i + 1 >= len(argv):
                sys.exit(f'missing value for {a}')
            if a == '--data-dir':
                data_dir = argv[i + 1]
            else:
                sql_dir = argv[i + 1]
            i += 2
            continue
        positional.append(a)
        i += 1
    return data_dir, sql_dir, positional

D, SQL_DIR, args = _parse_cli(sys.argv[1:])
if args == ['--all']: files = sorted(glob.glob(f'{D}/*.json'))
elif args: files = [a if os.path.isabs(a) else os.path.join(D, a) for a in args]
else: files = sorted(glob.glob(f'{D}/*.json'))[-1:]
recs, logs = {}, []
for f in files:
    d = json.load(open(f)); name = os.path.basename(f)
    rs = d.get('records', [])
    logs.append({'source_file': name, 'generated_at': d.get('generated_at'), 'record_count': len(rs)})
    for r in rs:
        eid = r.get('event_id') or hashlib.md5(f"{r.get('type')}|{r.get('datetime')}".encode()).hexdigest()
        v = r.get('value'); amt = None
        if isinstance(v, dict) and v.get('unit', 'ml') == 'ml': amt = v.get('value')
        elif isinstance(v, (int, float)): amt = v
        det = r.get('details')
        recs[eid] = {'event_id': eid, 'recorded_at': r['datetime'], 'type': r['type'], 'amount_ml': amt,
                     'left_sec': r.get('leftTime'), 'right_sec': r.get('rightTime'), 'memo': r.get('memo'),
                     'details': json.dumps(det, ensure_ascii=False) if isinstance(det, (dict, list)) else det,
                     'raw': r, 'source_file': name}
q = lambda o: json.dumps(o, ensure_ascii=False).replace("'", "''")
up = f"""INSERT INTO public.piyolog_records (event_id, recorded_at, type, amount_ml, left_sec, right_sec, memo, details, raw, source_file)
SELECT x->>'event_id', (x->>'recorded_at')::timestamptz, x->>'type', (x->>'amount_ml')::numeric, round((x->>'left_sec')::numeric)::int, round((x->>'right_sec')::numeric)::int, x->>'memo', x->>'details', x->'raw', x->>'source_file'
FROM jsonb_array_elements('{q(list(recs.values()))}'::jsonb) AS x
ON CONFLICT (event_id) DO UPDATE SET recorded_at=EXCLUDED.recorded_at, type=EXCLUDED.type, amount_ml=EXCLUDED.amount_ml, left_sec=EXCLUDED.left_sec, right_sec=EXCLUDED.right_sec, memo=EXCLUDED.memo, details=EXCLUDED.details, raw=EXCLUDED.raw, source_file=EXCLUDED.source_file, last_seen_at=now()"""
fl = f"""INSERT INTO public.piyolog_fetch_log (source_file, generated_at, record_count)
SELECT x->>'source_file', (x->>'generated_at')::timestamptz, (x->>'record_count')::int FROM jsonb_array_elements('{q(logs)}'::jsonb) AS x
ON CONFLICT (source_file) DO NOTHING"""
os.makedirs(SQL_DIR, exist_ok=True)
open(os.path.join(SQL_DIR, 'upsert.sql'), 'w').write(up)
open(os.path.join(SQL_DIR, 'fetchlog.sql'), 'w').write(fl)
print(f'files={len(files)} unique_records={len(recs)}')
