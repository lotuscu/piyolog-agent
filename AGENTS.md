# Instructions for an AI agent

Read this file before doing anything with a parent's PiyoLog records.

Unofficial local tool, not affiliated with PiyoLog. It lets a parent point any assistant at their own data feed and get a repeatable summary. Python 3.9+ standard library only. No database is required.

## Safety

- The feed URL is a password. Anyone who has it can read the records without logging in.
- Never print it, log it, commit it, paste it into a reply, or pass it as a command-line argument. Read it only from `PIYOLOG_FEED_URL` or `.feed_url`.
- Never commit `data/`, snapshots, the local store, `.env`, `.feed_url`, `sql/`, `briefings/`, `topics.log`, or `schedule.md`.
- Quote `summarize.py` output. Do not invent records, millilitres, or sleep times.
- Not medical advice. You may flag a concerning logged pattern; you do not diagnose, prescribe, or set a medical cutoff. The parent and their clinician decide.
- Feed notes can contain names and personal details. Treat summaries as private.

## If you are Muse: complete setup

Do these steps in order. The parent talks to you only through chat; they cannot run shell commands or edit files on your machine themselves, so do the file work yourself.

1. **Get the code** into `~/workspace/piyolog-briefing/` (persistent; never `/tmp`).
   - First try: `git clone https://github.com/lotuscu/piyolog-briefing.git ~/workspace/piyolog-briefing`
   - If git fails for lack of credentials (common when the repository is private for this user, or git has no login on your machine): use your GitHub connector instead. With `get_file_contents` on `lotuscu/piyolog-briefing`, list the root at the target ref, recurse into `docs/`, `skills/piyolog/`, `tests/`, and `tests/fixtures/`, and download every file to the same relative path. Verify each file's size matches the listing before continuing. Do not conclude the repository is unreachable from a failed `git clone` alone.
2. **Install the skill**: copy `skills/piyolog/SKILL.md` to `~/workspace/custom-skills/piyolog/SKILL.md`. That directory is where Muse loads custom skills from; leaving the file inside the repository is not an installation.
3. **Receive the secret**: ask the parent to create a feed in the PiyoLog app (Settings → Data Feed → Create New Feed) and send you the URL in chat — in Muse that is the only channel they have. Then:
   - Write it, exactly one line, to `~/workspace/piyolog-briefing/.feed_url` with a file write that does not echo it anywhere, and set permissions `chmod 600 .feed_url`.
   - Never run a command whose arguments contain the URL (command lines get logged). `fetch.py` refuses URLs in argv anyway.
   - Tell the parent once: the URL has passed through chat, a feed can be revoked and recreated in the app at any time, and a free feed expires 90 days after creation anyway. Do not repeat the warning on every run.
4. **Verify** before telling the parent it works:
   - `python3 -m unittest discover -s tests -t .` from the repo directory — all tests must pass.
   - `python3 fetch.py` — expect `fetched=N inserted=N` with no URL in the output. Run it a second time: expect `inserted=0 updated=N` (deduplication works).
   - `python3 summarize.py --days 2 --format both` — show the parent the resulting briefing (see `docs/routine.md`).
   - Paths are anchored to the repository directory, so the scripts work from any working directory. Still use absolute paths in scheduled jobs.
5. **Schedule it**: create two scheduled jobs (Muse crons) at about 06:00 and 17:00 in the parent's timezone. Each job's instructions must say: run `python3 ~/workspace/piyolog-briefing/fetch.py`, then `python3 ~/workspace/piyolog-briefing/summarize.py --days 2 --format both`, then send the parent a briefing shaped like `docs/routine.md`. If fetch reports HTTP 401/404, tell the parent to create a new feed instead of sending a briefing. A free feed covers only ~24 hours, so the twice-daily overlap is what keeps the local history complete.
6. **Postgres only if the parent asks** (for example Neon). See `docs/postgres.md`. On Muse your machine has no `psql` and no `psycopg` preinstalled; the doc gives the exact venv install that works. Never invent a connection string, and never write one into the repo.

## Setup on other agents

1. Confirm `python3` is 3.9 or newer.
2. The parent creates a feed in the PiyoLog app (Settings → Data Feed → Create New Feed) and saves the URL in `.feed_url` in the repository root, or exports `PIYOLOG_FEED_URL`. Do not ask them to paste it into a shared or public channel; if they already did, note it once (see the Muse step 3 warning) and move on.
3. Optional: `PIYOLOG_TZ` (default `Asia/Tokyo`). Feed timestamps are UTC; day boundaries use this timezone.

## Run

```bash
python3 fetch.py                                  # twice a day, e.g. 06:00 and 17:00
python3 summarize.py --days 2 --format both
python3 summarize.py --from 2026-09-08 --to 2026-09-09 --format json
python3 summarize.py --days 7 --tz America/Los_Angeles
```

`--source auto` reads `data/records.jsonl` when it has rows; `--source snapshots` rebuilds from raw snapshots only. If more than ~24 hours pass between fetches, records that aged out of a free feed are gone. Do not poll in a loop; the official guide asks callers to stay near once a minute or slower.

What the numbers mean (full rules in `README.md`):

- Pumping is reported separately; do not add it to what the baby drank unless a feed was also logged. Never convert breastfeeding minutes into millilitres.
- Sleep is paired `Sleep` → next `WakeUp` records. A `Sleep` with no later `WakeUp` is not counted. Stretches crossing midnight are split across both dates for the total; the longest stretch is the full pair.
- A record deleted in the app disappears from later feeds but stays in the local store. Say so if the parent asks why something old is still present.

## Briefing

Follow `docs/routine.md`: Feeding / Sleep / Diaper lines, then one to three sentences, from `summarize.py` output only. Save briefings under `briefings/` if at all; never commit them.

## When the fetch fails

- HTTP 404 (`feed_unavailable`) or 401: feed expired, revoked, paused, wrong URL, or child deleted. Tell the parent to create a new feed in the app and replace the local URL. A brand-new feed can 404 for about a minute; one retry is enough before replacing it.
- HTTP 413: range too large. HTTP 429: slow down. HTTP 5xx: try later.
- Never replace a failure with invented numbers.
- Free feeds expire 90 days after creation. Premium can last 90 days, 365 days, or indefinitely while Premium is active. Settings cannot be edited in place; revoke and recreate.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

`tests/fixtures/synthetic_feed.json` is fictional. Never replace it with real records.
