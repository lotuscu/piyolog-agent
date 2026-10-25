# Optional Postgres

`fetch.py` stores everything in local files. Only enable this integration when the user explicitly requests database-backed long-term storage. Local files already retain history and do not require a database. Other database backends are not implemented. You do not need a database, and `summarize.py` never reads one.

To also keep a copy in your own Postgres (for example Neon), put that project's connection string in `DATABASE_URL`. Do not commit the string, a project id, or a branch id.

```bash
python3 fetch.py --backend postgres
```

That still writes the local snapshot, JSONL and CSV files first. It then writes `sql/upsert.sql` and `sql/fetchlog.sql` and applies `schema.sql` plus those files (all idempotent, safe to re-run):

- Records use `ON CONFLICT (event_id) DO UPDATE`. `last_seen_at` moves forward; `first_seen_at` stays.
- The fetch log uses `ON CONFLICT (source_file) DO NOTHING`.
- Records must have the official `event_id`. Missing IDs cause an explicit error instead of guessed identities or silently merged events.

The legacy psycopg2 branch is no longer supported. A driver must already be present: the tool tries `psycopg` (version 3), then the `psql` client. If none is available, the local files are still saved and the command exits with an error.

**On Muse** none of those is preinstalled. This works (verified October 2026, psycopg 3.3.6):

```bash
cd ~/workspace/piyolog-agent
python3 -m venv .venv
.venv/bin/pip install 'psycopg[binary]'
DATABASE_URL='...' .venv/bin/python fetch.py --backend postgres
```

Use the venv inside the repository (`.venv/` is gitignored): installs in system or temporary locations do not survive a machine reset. Pure-Python `pg8000` is **not** supported by this tool.

`to_postgres_sql.py` replaces the former `to_neon_sql.py` command; update any existing jobs that call the old name. It works with Postgres generally, not only Neon.

`python3 to_postgres_sql.py` only builds the SQL files from snapshots; it does not connect. Apply them yourself with:

```bash
python3 to_postgres_sql.py --data-dir data --sql-dir sql   # or --all for every snapshot
PGDATABASE="$DATABASE_URL" psql -X -w -v ON_ERROR_STOP=1 --single-transaction -f schema.sql -f sql/upsert.sql -f sql/fetchlog.sql
```

The offline exporter is retained for historical backfills: `--all` reads every retained snapshot without contacting the feed or requiring database credentials. `fetch.py --backend postgres` only synchronizes the current response and cannot replace that operation.

The psql fallback passes the connection through the child process environment (`PGDATABASE`), not command-line arguments; SQL is sent through standard input. Environment variables are still secrets and must not be logged. Both backends apply schema and data in one transaction.
