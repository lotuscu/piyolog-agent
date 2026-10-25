# Optional Postgres

`fetch.py` stores everything in local files. You do not need a database.

If you also want Postgres (for example Neon serverless Postgres, or any other Postgres you run), create your own project and copy the connection string from that project's console into `DATABASE_URL`. Do not commit the string, the project id, or the branch id.

Apply the schema once, or let `fetch.py` apply it for you. `schema.sql` uses `CREATE TABLE IF NOT EXISTS` and is safe to re-run.

```bash
psql "$DATABASE_URL" -f schema.sql
python3 fetch.py --backend postgres
```

`--backend postgres` still writes the local snapshot, JSONL, CSV, and SQLite files. It then writes `sql/upsert.sql` and `sql/fetchlog.sql` and applies them.

- Records use `ON CONFLICT (event_id) DO UPDATE`. `last_seen_at` moves forward. `first_seen_at` stays.
- The fetch log uses `ON CONFLICT (source_file) DO NOTHING`.
- When the feed omits `event_id`, the key is `md5(type|datetime)`.

The tool uses the `psycopg` package if it is already installed, then `psycopg2`, then the `psql` client. None of those are required for the default local store. If you ask for Postgres and none of them is available, the local files are still saved and the command exits with an error.

`python3 to_neon_sql.py` only builds the SQL files from snapshots. It does not connect.

```bash
python3 to_neon_sql.py --data-dir data --sql-dir sql
python3 to_neon_sql.py --all
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/upsert.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/fetchlog.sql
```

`summarize.py` reads the local store, not Postgres.
