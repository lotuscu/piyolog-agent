---
name: piyolog
description: Fetch a parent's PiyoLog data feed and summarize feeding, sleep, diapers, and solids for a daily briefing. Use when the user uses PiyoLog and wants an agent to read the feed on a schedule. The feed URL is a secret and must not be printed or committed.
---

# PiyoLog local summary

The code lives in the `piyolog-briefing` repository. On Muse it is installed at `~/workspace/piyolog-briefing/`; if that directory is missing, follow the Muse setup in the repository's `AGENTS.md` first (clone or connector download, then copy this skill to `~/workspace/custom-skills/piyolog/SKILL.md`).

Read `AGENTS.md` in the repository root and follow it. Python 3.9+ standard library only. The default store is local files under the repository's `data/`; paths are anchored to the repository, so the scripts work from any working directory. Postgres is optional.

## Safety

The feed URL is a password. Never print it, log it, commit it, or pass it on the command line. It lives only in `PIYOLOG_FEED_URL` or in `<repo>/.feed_url` (chmod 600). This tool is not medical advice; the parent and their clinician decide.

## Commands

```bash
python3 ~/workspace/piyolog-briefing/fetch.py
python3 ~/workspace/piyolog-briefing/summarize.py --days 2 --format both
```

Run the fetch about twice a day (for example 06:00 and 17:00 in the parent's timezone). A free feed covers about 24 hours and expires 90 days after creation. Do not poll faster than about once a minute.

If the fetch reports HTTP 401 or 404, ask the parent to create a new feed in the PiyoLog app (Settings → Data Feed). Do not invent a URL or numbers.

## Briefing

Use the summary output only. Three lines: Feeding, Sleep, Diaper. Then one to three sentences. Flag concerning logged patterns without setting a medical threshold.

## Do not

- Commit `data/`, snapshots, the local store, `.env`, `.feed_url`, or briefing text.
- Turn breastfeeding minutes into millilitres.
- Treat pumping as a bottle the baby drank unless a feed was also logged.
- Require a database. `summarize.py` reads the local store.
