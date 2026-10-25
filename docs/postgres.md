# Optional Postgres

`fetch.py` stores everything in local files. Only enable this integration when the user explicitly requests database-backed long-term storage. Local files already retain history and do not require a database. Other database backends are not implemented. You do not need a database, and `summarize.py` never reads one.

To also keep a copy in your own Postgres (for example Neon), put that project's connection string in `DATABASE_URL`. Do not commit the string, a project id, or a branch id.

```bash
python3 fetch.py --backend postgres
```

That still writes the local snapshot, JSONL and CSV files first. It then writes `sql/upsert.sql` and `sql/fetchlog.sql` and applies `schema.sql` plus those files (all idempotent, safe to re-run):

- Records use `ON CONFLICT (event_id) DO UPDATE`. `last_seen_at` moves forward; `first_seen_at` stays.
- The fetch log uses `ON CONFLICT (source_file) DO NOTHING`.
- When the feed omits `event_id`, the key is `md5(type|datetime)`.

A driver must already be present: the tool tries `psycopg`, then `psycopg2`, then the `psql` client. If none is available, the local files are still saved and the command exits with an error.

**On Muse** none of those is preinstalled. This works (verified October 2026, psycopg 3.3.6):

```bash
cd ~/workspace/piyolog-briefing
python3 -m venv .venv
.venv/bin/pip install 'psycopg[binary]'
DATABASE_URL='...' .venv/bin/python fetch.py --backend postgres
```

Use the venv inside the repository (`.venv/` is gitignored): installs in system or temporary locations do not survive a machine reset. Pure-Python `pg8000` is **not** supported by this tool.

`python3 to_neon_sql.py` only builds the SQL files from snapshots; it does not connect. Apply them yourself with:

```bash
python3 to_neon_sql.py --data-dir data --sql-dir sql   # or --all for every snapshot
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/upsert.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/fetchlog.sql
```
