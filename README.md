# PiyoLog briefing

Unofficial local tools that let a parent point an AI agent at their own [PiyoLog](https://www.piyolog.com/app/piyolog/data_feed/en/index.html) data feed and get a repeatable daily summary.

**This project is not affiliated with, endorsed by, or maintained by the makers of PiyoLog.** PiyoLog is their product. This repository only fetches the feed the parent creates and summarizes it on their machine.

An agent that will run this project should read [AGENTS.md](AGENTS.md) once and then follow it. Humans can start below.

The feed URL is a password. Do not commit it, paste it into a public issue, or leave it in a screenshot.

## Quick start

You need Python 3.9 or newer. There is nothing to install.

**1. Create a feed in the PiyoLog app and copy the URL.**

On iOS: Settings, Data Feed, Create New Feed. Pick the child, a time range, and an expiration, then copy the URL from the feed details screen. There is no separate API key. The URL is the credential.

**2. Save that URL locally, not in git.**

```bash
git clone https://github.com/lotuscu/piyolog-briefing.git
cd piyolog-briefing
printf '%s\n' 'PASTE-YOUR-FEED-URL-HERE' > .feed_url
```

Or export `PIYOLOG_FEED_URL` in the shell. `.feed_url` and `.env` are gitignored. Names are listed in `.env.example`.

**3. Fetch the feed and print today's summary.**

```bash
python3 fetch.py
python3 summarize.py --days 1
```

A free feed expires 90 days after you create it. When it does, `fetch.py` tells you to make a new one. It does not print the URL.

`fetch.py` writes a timestamped snapshot plus a deduplicated store under `data/`:

- `records.jsonl` is the canonical store (one record per line, keyed by `event_id`)
- `records.csv` is a flat view
- `records.sqlite` is a SQLite file (stdlib) with the same rows

Run `fetch.py` about twice a day. A free feed only returns the last 24 hours, so a longer gap can drop records that will not appear again. The store keeps what you have already fetched and updates a row when the same `event_id` shows up again.

Day boundaries use `PIYOLOG_TZ`, or `Asia/Tokyo` when that is unset. Feed timestamps are UTC.

## Example prompt

Paste this into Grok Bot, Muse, Dot, Claude, ChatGPT, Cursor, or another agent after the URL is in the environment or in `.feed_url`:

```
You have the piyolog-briefing repository. Read AGENTS.md and follow it.

My PiyoLog feed URL is already in PIYOLOG_FEED_URL or in .feed_url. Treat that URL as a password: never print it, log it, commit it, or send it anywhere.

1. Run: python3 fetch.py
2. Run: python3 summarize.py --days 2 --format both
3. Write a short briefing with one line for Feeding, one line for Sleep, one line for Diaper, then one to three sentences.
4. Use only numbers from the summary. Do not invent records.
5. This is not medical advice. You may point out when logged milk or sleep looks low, or when temperature, vomiting, rash, cough, injury, medicine, or a hospital visit is present. I will decide what to do, with my child's clinician if needed.
6. If fetch.py says the feed is unavailable, stop and tell me to create a new data feed in the PiyoLog app. Do not guess a URL.
```

The same routine is written out in [docs/routine.md](docs/routine.md). A skill file for agents that load skills is [skills/piyolog/SKILL.md](skills/piyolog/SKILL.md).

## How to get the feed URL

Checked against the official guide in October 2026. These pages loaded:

- [Data Feed: user guide and data specification (English)](https://www.piyolog.com/app/piyolog/data_feed/en/index.html)
- [Official guide (Japanese)](https://www.piyolog.com/app/piyolog/data_feed/ja/index.html)
- [Developer announcement, 15 September 2026, PiyoLog v9.4.0](https://note.com/y_sakaki/n/nb47c50c0f490)

What that guide says, in short:

- The feature is a read-only HTTPS GET. You create the URL in the iOS app under Settings, Data Feed. Creating a feed needs an administrator on the account.
- You choose one child, a time range, and an expiration. Those cannot be edited later. Revoke the feed and create a new one to change them.
- A free account can have one feed, covering 24 hours, expiring 90 days after creation.
- Premium can have up to five feeds, with a range of 24 hours, 3 days, 7 days, or 28 days, and an expiration of 90 days, 365 days, or none. A feed with no expiration still needs an active Premium entitlement.
- The URL itself is the secret. Do not post it. If it leaks, revoke it. Revoking does not delete copies another tool already saved.
- Timestamps are ISO 8601 UTC. The guide's record types are fixed English strings (`Formula`, `BreastFeeding`, `Sleep`, `WakeUp`, `Pee`, `Poop`, `Solid`, and others). The full field list is on the official page.
- `Sleep` and `WakeUp` are separate records. The feed does not include a sleep duration.
- Solid food is not a structured menu. The text is in `memo`.
- The feed does not include the child's name, birth date, sex, photos, diary, or vaccine names.
- HTTP 404 with error code `feed_unavailable` covers an expired feed, a revoked feed, a paused Premium feed, a wrong URL, and a deleted child. A new feed can also return 404 for a short time right after creation.
- A 24-hour feed is cached for about a minute. The guide asks you not to hit the same URL more than about once a minute. Twice a day is enough.

`fetch.py` treats HTTP 401 the same as HTTP 404 and tells you to create a new feed. The published guide documents 404 for an unavailable feed, not 401.

## What the summary means

`summarize.py` prints Markdown, JSON, or both (`--format md|json|both`). `--from` and `--to` are inclusive local dates. `--days 2` is yesterday and today in the selected timezone.

Per day it reports:

| Section | Rule |
| --- | --- |
| Milk | Millilitres for `Formula`, `ExpressedBreastMilk`, `BreastFeeding`, and `Pumping`, only when the feed sends a positive `ml` value. Duration is not turned into millilitres. Pumping is not counted as a bottle the baby drank. |
| Breastfeeding | `leftTime` plus `rightTime`, in minutes. The feed sends seconds. |
| Sleep | Each `Sleep` is paired with the next later `WakeUp`. The daily total is the part of those stretches that falls on that local date. The longest stretch is the full pair, even when it crosses midnight. An unpaired start or wake is omitted. |
| Diapers | Pee count, poop count, the longest gap that ends at a pee or poop that day, and the longest poop-to-poop gap that ends that day. |
| Solids | Labels split from the `Solid` memo on commas, semicolons, and new lines. `first_seen` is the earliest local date that label appears in the loaded history, which can be before the requested range. |
| Temperature and other counts | Max Celsius when a `Temperature` record has a value, plus counts of vomiting, rash, cough, medicine, hospital, and injury. |

The JSON repeats those rules in a `notes` array and includes a disclaimer. Missing numbers are omitted values from the feed, not zeros you should invent. A day with no logged milk shows zeros because nothing in that category was present.

## Commands

```bash
python3 fetch.py
python3 fetch.py --tz Asia/Tokyo --data-dir data
python3 summarize.py --days 2 --format both
python3 summarize.py --from 2026-09-08 --to 2026-09-09 --format json
python3 -m unittest discover -s tests -t . -v
```

`tests/fixtures/synthetic_feed.json` is fictional and is the only JSON file intended to be committed. Do not replace it with real records.

If `event_id` is missing, the store key is `md5(type|datetime)` using the timestamp string from the feed. The current feed spec says `event_id` is always present. The fallback is there so an older or partial file still deduplicates.

## Optional Postgres

The default backend is local files. Postgres is not required and is not used by `summarize.py`.

If you want a copy in your own Postgres database, including Neon, set `DATABASE_URL` from that project's console and run:

```bash
python3 fetch.py --backend postgres
```

That still writes the local store, then applies `schema.sql` plus an idempotent upsert when `psycopg`, `psycopg2`, or `psql` is available. Details are in [docs/postgres.md](docs/postgres.md). `to_neon_sql.py` only generates `sql/upsert.sql` and `sql/fetchlog.sql` from snapshots. It does not connect.

Do not commit the connection string.

## Layout

| Path | Purpose |
| --- | --- |
| `fetch.py` | Download the feed, save a snapshot, update the local store |
| `summarize.py` | Per-day Markdown and JSON |
| `piyolog.py` | Shared library (stdlib only) |
| `to_neon_sql.py` | Optional SQL generator |
| `schema.sql` | Optional Postgres tables |
| `AGENTS.md` | Instructions for an assistant |
| `docs/routine.md` | Generic twice-daily briefing |
| `docs/postgres.md` | Optional database |
| `skills/piyolog/SKILL.md` | Short skill for agents that load skills |
| `tests/fixtures/synthetic_feed.json` | Fake records for tests |
| `.env.example` | Variable names only |

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

## License

[MIT](LICENSE).
