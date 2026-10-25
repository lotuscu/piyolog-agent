# Optional Postgres

`fetch.py` stores everything in local files. You do not need a database, and `summarize.py` never reads one.

To also keep a copy in your own Postgres (for example Neon), put that project's connection string in `DATABASE_URL`. Do not commit the string, a project id, or a branch id.

```bash
python3 fetch.py --backend postgres
```

That still writes the local snapshot, JSONL, CSV, and SQLite files first. It then writes `sql/upsert.sql` and `sql/fetchlog.sql` and applies `schema.sql` plus those files (all idempotent, safe to re-run):

- Records use `ON CONFLICT (event_id) DO UPDATE`. `last_seen_at` moves forward; `first_seen_at` stays.
- The fetch log uses `ON CONFLICT (source_file) DO NOTHING`.
- When the feed omits `event_id`, the key is `md5(type|datetime)`.

A driver must already be present for `--backend postgres`: the tool tries `psycopg`, then `psycopg2`, then the `psql` client. If none is available, the local files are still saved and the command exits with an error. Pure-Python `pg8000` is **not** supported by that path.

**On Muse, do not use `--backend postgres` at all.** Muse's egress goes through an HTTP proxy with synthetic DNS, so a direct Postgres connection to port 5432 never reaches Neon — psycopg fails with "invalid response to SSL negotiation" no matter how correct the connection string is (verified October 2026). Use the HTTPS sync script instead; it talks to Neon's SQL-over-HTTPS endpoint on port 443, needs no driver, and reads `DATABASE_URL` from the environment or from a gitignored `.env` next to the script:

```bash
cd ~/workspace/piyolog-briefing
python3 fetch.py                 # local store first, as always
python3 neon_https_sync.py       # then push the newest snapshot to Neon
```

Two more things that bite on Muse and with least-privilege roles:

- A role that can only read and write the tables (the recommended setup) has no CREATE privilege on schema `public`, so applying `schema.sql` fails with `permission denied for schema public` (SQLSTATE 42501). The tables must be created once by the database owner. `neon_https_sync.py` detects this, skips the schema step with a warning, and syncs the data.
- Do not `source`/`.` the `.env` file in a shell: the connection string contains `&`, which splits the line and silently truncates the value. Keep the value quoted in `.env` and let the scripts parse the file themselves.

`python3 to_neon_sql.py` only builds the SQL files from snapshots; it does not connect. Apply them yourself with:

```bash
python3 to_neon_sql.py --data-dir data --sql-dir sql   # or --all for every snapshot
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/upsert.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/fetchlog.sql
```
