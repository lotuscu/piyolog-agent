# Twice-daily briefing routine

Runs at 06:00 and 17:00 Asia/Tokyo.

This file describes the flow only. Do not store briefing text, topic logs, schedule notes, or snapshot data in the repository.

1. Fetch the piyolog 24-hour JSON feed. Keep the URL in `PIYOLOG_FEED_URL` or in a local `.feed_url` file. Never commit the URL. Save the body to `data/YYYYMMDD_HHMM.json`.
2. Run `python3 to_neon_sql.py` on the newest snapshot (or pass file names, or `--all`). The script writes `sql/upsert.sql` and `sql/fetchlog.sql`.
3. Execute both statements in one transaction on the Neon Postgres database, using Neon MCP `run_sql_transaction` or `psql` with `DATABASE_URL`. The record upsert and the fetch-log insert are idempotent.
4. Compare the new rows with recent days and write a short briefing for the parent. Use three fragment lines labeled Feeding, Sleep, and Diaper, then one to three sentences. Include one age-appropriate caution, rotate the topic, and record the topic name in a local `topics.log`. Add an explicit flag only when milk intake or sleep is clearly insufficient, or when there are signs of fever or illness. Keep the briefing under `briefings/` (local only).
5. Check a local `schedule.md` for vaccines or checkups within the next 7 days.
6. Send a one-line note to the coordinating assistant.
7. If the feed fetch fails (feeds expire after about 90 days), ask the user to recreate the feed.

`topics.log`, `schedule.md`, and `briefings/` are gitignored. Do not commit them.
