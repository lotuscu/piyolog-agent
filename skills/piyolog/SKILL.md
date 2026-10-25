---
name: piyolog
description: Fetch a parent's PiyoLog data feed and summarize feeding, sleep, diapers, and solids for a daily briefing. Use when the user uses PiyoLog and wants an agent to read the feed on a schedule. The feed URL is a secret and must not be printed or committed.
---

# PiyoLog local summary

Read `AGENTS.md` in the repository root and follow it. Python 3.9+ standard library only. The default store is local files. Postgres is optional.

## Safety

The feed URL is a password. Never print it, log it, commit it, or pass it on the command line. Read it from `PIYOLOG_FEED_URL` or `.feed_url`. This tool is not medical advice. The parent and their clinician decide.

## Commands

```bash
python3 fetch.py
python3 summarize.py --days 2 --format both
```

Run the fetch about twice a day. A free feed covers about 24 hours and expires 90 days after creation. Do not poll faster than about once a minute.

If the fetch reports HTTP 401 or 404, ask the parent to create a new feed in the PiyoLog app (Settings, Data Feed). Do not invent a URL.

## Briefing

Use the summary output only. Three lines: Feeding, Sleep, Diaper. Then one to three sentences. Flag concerning logged patterns without setting a medical threshold.

## Do not

- Commit `data/`, snapshots, the local store, `.env`, `.feed_url`, or briefing text.
- Turn breastfeeding minutes into millilitres.
- Treat pumping as a bottle the baby drank unless a feed was also logged.
- Require a database. `summarize.py` reads the local store.
