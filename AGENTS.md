# Instructions for an AI agent

Read this file before doing anything with a parent's PiyoLog records.

This repository is an unofficial local tool. It is not affiliated with PiyoLog. It lets a parent point any assistant (Grok Bot, Muse, Dot, Claude, ChatGPT, Cursor, or another agent) at their own data feed and get a repeatable summary. Python 3.9+ standard library only. No database is required.

## Safety

- The feed URL is a password. Anyone who has it can read the records without logging in.
- Never print the URL, log it, put it in a commit, paste it into a chat reply, or send it to another service.
- Read it only from `PIYOLOG_FEED_URL` or from a local file (`.feed_url` by default). Never accept it as a command-line argument.
- Do not commit `data/`, snapshots, `records.jsonl`, `records.csv`, `records.sqlite`, `.env`, `.feed_url`, `briefings/`, `topics.log`, or `schedule.md`.
- Do not invent records, millilitres, or sleep times. Quote `summarize.py` output.
- This is not medical advice. The parent and their clinician decide. You may flag a concerning pattern. You do not diagnose, prescribe, or set a medical cutoff.
- Notes in the feed can contain names or other personal details. Treat the summary as private.

## Setup

1. Confirm `python3` is 3.9 or newer.
2. Ask the parent to create a feed in the PiyoLog iOS app: Settings, Data Feed, Create New Feed. They copy the URL from the app. The official guide is linked from `README.md`. There is no separate API key. The URL is the credential.
3. Ask them to save it themselves, either:
   - `export PIYOLOG_FEED_URL='...'` in a shell you do not echo, or
   - one line in `.feed_url` in this directory.
4. Do not ask them to paste the URL into the chat if you can avoid it. If they already pasted it, tell them it is now in the transcript, suggest they revoke that feed and create a new one, and do not repeat the URL.
5. Optional: `PIYOLOG_TZ` (default `Asia/Tokyo`). Feed timestamps are UTC. Day boundaries use this timezone.

## Scheduled fetch

Run twice a day, for example 06:00 and 17:00 in the parent's timezone:

```bash
python3 fetch.py
```

A free feed returns roughly the last 24 hours and expires 90 days after it is created. Twice a day overlaps, and the store deduplicates on `event_id`, so local history survives the rolling window. If more than about 24 hours pass between fetches, records that aged out of the feed are gone.

Do not poll in a loop. The official guide asks callers to stay near once a minute or slower. Twice a day is the right pace.

The command prints counts and a snapshot filename. It must not print the URL.

## Summarize

```bash
python3 summarize.py --days 2 --format both
```

Useful variants:

```bash
python3 summarize.py --from 2026-09-08 --to 2026-09-09 --format json
python3 summarize.py --days 7 --tz America/Los_Angeles
```

`--source auto` reads `data/records.jsonl` when it has rows. Use `--source snapshots` to rebuild a view from raw JSON files only.

The Markdown and JSON include, per local day:

- milk millilitres by type (formula, expressed breast milk, breastfeeding amount entered in the app, pumping)
- breastfeeding minutes (left seconds plus right seconds)
- sleep total on that date, and the longest full Sleep-to-WakeUp stretch that overlaps the date
- pee count, poop count, longest diaper gap, longest poop gap
- solid foods from the memo, with the first local date that food appears in the loaded history
- max temperature in Celsius, when logged
- counts for vomiting, rash, cough, medicine, hospital, and injury, when logged

Pumping is reported separately. Do not add it to bottles the baby drank unless the parent also logged a feed. Do not convert breastfeeding minutes into millilitres. The feed does not estimate that.

Sleep is not a duration in the feed. `Sleep` and `WakeUp` are separate records. This tool pairs each `Sleep` with the next later `WakeUp`. A new `Sleep` before a `WakeUp` leaves the earlier one unpaired. Unpaired records are not counted. Sleep that crosses midnight is split across the two local dates for the total, and the longest stretch is the full pair.

A deleted record disappears from later feed responses but stays in the local store. Say so if the parent asks why something old is still present.

## Briefing

Follow `docs/routine.md`. Shape:

- Feeding
- Sleep
- Diaper
- one to three sentences

Save the briefing under `briefings/` if you save it at all. Do not commit it.

## When the fetch fails

HTTP 404 (`feed_unavailable`) means the feed is expired, revoked, paused, the URL is wrong, or the child was deleted. HTTP 401 is treated the same. Tell the parent to open Settings, Data Feed, and create a new feed, then replace the local URL. A brand-new feed can also 404 for about a minute; one retry is enough before replacing it.

HTTP 413 means the range is too large. HTTP 429 means slow down. HTTP 5xx means try later. Never replace a failure with invented numbers.

Free feeds expire 90 days after creation. Premium can last 90 days, 365 days, or have no expiration while Premium is active. Settings cannot be edited in place. Revoke and create a new feed.

## Optional Postgres

Local files are the default and the source for summaries. Postgres is opt-in. Read `docs/postgres.md`. Do not create a database unless the parent asks. Never write a connection string, project id, or branch id into the repo.

```bash
python3 fetch.py --backend postgres
```

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

`tests/fixtures/synthetic_feed.json` is fictional. Do not replace it with real records.
