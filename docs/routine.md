# Twice-daily briefing

Generic routine for any assistant. Not a personal schedule; contains no sample briefing text.

Run at about 06:00 and 17:00 in the parent's timezone — any two times about half a day apart work. A free PiyoLog feed covers only the last ~24 hours, so skipping more than a day can leave a gap the feed will never send again.

1. Run `python3 fetch.py` (paths are anchored to the repository; any working directory works). The URL stays in `PIYOLOG_FEED_URL` or `.feed_url`. Never print it or commit it.
2. Only if fetch exits with status 0, run `python3 summarize.py --days 2 --format both`. On any failure (network, rate limit, server error, storage error, or unavailable feed), stop the normal briefing and report the problem. Never present old local data as current.
3. Write a short briefing from that output only. Include coverage and freshness warnings and missing milk amounts. Partial/current days are not complete daily totals; missing or unknown data is not zero:
   - one line for Feeding
   - one line for Sleep
   - one line for Diaper
   - then one to three sentences
4. Add an explicit flag only when logged milk or sleep looks clearly low for what the parent already knows about their child, or when the summary shows temperature, vomiting, rash, cough, injury, medicine, or a hospital visit. Do not invent a medical threshold, and say this is not medical advice — the parent and their clinician decide.
5. Optional local extras, both gitignored: rotate a caution topic and record used ones in `topics.log`; if `schedule.md` exists, mention items in the next 7 days.
6. If `fetch.py` says the feed is unavailable, stop and ask the parent to create a new feed in the PiyoLog app. Do not guess a URL.

Postgres is optional; write the briefing from the local summary even when a database is also updated. Keep briefing text under `briefings/` if you save it. That directory is gitignored.
