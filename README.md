# piyolog-briefing

A small personal pipeline that pulls a piyolog 24-hour JSON feed twice a day, upserts the records into Neon serverless Postgres, and leaves a short parent briefing for a local assistant to write.

## What it does

1. Save the feed response as a JSON snapshot.
2. Turn that snapshot into idempotent SQL.
3. Upsert rows into Neon.
4. Draft a short briefing from the stored rows (Feeding, Sleep, and Diaper lines, plus a few sentences). The briefing itself stays on the machine that runs the assistant. This repository does not contain briefing text, topic logs, or schedule notes.

## Architecture

```
piyolog 24h feed
    -> JSON snapshot (data/YYYYMMDD_HHMM.json)
    -> SQL generator (to_neon_sql.py)
    -> Neon serverless Postgres
    -> short parent briefing (local, not committed)
```

`to_neon_sql.py` does not connect to the network and does not read credentials. It only reads snapshot files and writes SQL.

## Database

The database is Neon serverless Postgres in Singapore, region `aws-ap-southeast-1`.

Tables:

- `public.piyolog_records` stores one row per event. `event_id` is the primary key. When the feed omits `event_id`, the generator uses `md5(type|datetime)`. `amount_ml` is the millilitre amount for formula or expressed breast milk. `left_sec` and `right_sec` are rounded breast-feeding seconds. `memo` holds free text (for example solid food). `details` holds extra text such as stool notes. `raw` keeps the original JSON object. `first_seen_at` and `last_seen_at` default to `now()`. A repeat of the same `event_id` updates the row and sets `last_seen_at` to `now()`, and leaves `first_seen_at` unchanged.
- `public.piyolog_fetch_log` stores one row per snapshot file. `id` is an identity column. `fetched_at` defaults to `now()`. `source_file` is unique. Loading the same file again does nothing.

Index: `(type, recorded_at)` on `public.piyolog_records`.

`schema.sql` creates both tables with `CREATE TABLE IF NOT EXISTS` and is safe to re-run.

## Connect

Use your own Neon project. Do not commit the connection string, project id, branch id, or feed URL.

1. Create a Neon project in the Neon console (Singapore, `aws-ap-southeast-1`, if you want the same region).
2. Copy the connection string from the Neon console.
3. Export it as `DATABASE_URL` (see `.env.example` for the variable name). Put secrets in `.env` or your shell, not in git.
4. Apply the schema:

```bash
psql "$DATABASE_URL" -f schema.sql
```

Or send the statements in `schema.sql` through Neon MCP `run_sql_transaction` on your project.

After the generator runs, apply `sql/upsert.sql` and `sql/fetchlog.sql` in one transaction the same way (`psql`, or Neon MCP `run_sql_transaction` with those two statements).

## Run the script

Default paths match the previous layout:

- snapshots: `/workspace/piyolog/data`
- generated SQL: `/workspace/piyolog/sql/upsert.sql` and `fetchlog.sql`

Override them with `--data-dir` / `--sql-dir`, or with `PIYOLOG_DATA_DIR` / `PIYOLOG_SQL_DIR`. For a checkout of this repo:

```bash
mkdir -p data sql
# Save the feed yourself to data/YYYYMMDD_HHMM.json.
# Keep the URL in PIYOLOG_FEED_URL or in an untracked .feed_url file.

python3 to_neon_sql.py --data-dir data --sql-dir sql
python3 to_neon_sql.py --data-dir data --sql-dir sql --all
python3 to_neon_sql.py --data-dir data --sql-dir sql 20260101_0600.json
```

With no file arguments the script uses the newest `*.json` in the data directory. `--all` reads every JSON file in that directory. Later files win when the same `event_id` appears more than once.

The script prints `files=<n> unique_records=<n>`.

## Briefing flow

See `docs/routine.md`. Twice a day (06:00 and 17:00 Asia/Tokyo) the assistant loads the new rows, compares them with recent days, and writes a short briefing:

- three fragment lines: Feeding, Sleep, and Diaper
- one to three sentences, including one age-appropriate caution on a rotating topic
- an explicit flag only when milk intake or sleep is clearly insufficient, or when there are signs of fever or illness

Topic names, vaccine or checkup dates, and the briefing text belong in local files (`topics.log`, `schedule.md`, `briefings/`). Those paths are gitignored.

## Files

| Path | Role |
| --- | --- |
| `to_neon_sql.py` | Build upsert SQL from snapshots |
| `schema.sql` | Tables and index |
| `docs/routine.md` | Twice-daily flow |
| `.env.example` | Variable names only |
| `.gitignore` | Snapshots, generated SQL, secrets, daily summaries |

## Security

This repository holds placeholders only. Ignored paths include `data/`, `sql/*.sql`, `*.json`, `.feed_url`, `.env`, `topics.log`, `schedule.md`, `briefings/`, `summaries/`, and `daily/`.
