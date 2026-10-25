# Twice-daily briefing

This is a generic routine for any assistant. It is not a personal schedule and it does not contain sample briefing text.

Suggested times are 06:00 and 17:00 in the parent's timezone. Any two times about half a day apart work. A free PiyoLog feed only covers the last 24 hours, so skipping more than a day can leave a gap that the feed will never send again.

1. Run `python3 fetch.py`. The URL stays in `PIYOLOG_FEED_URL` or `.feed_url`. Never print it or commit it.
2. Run `python3 summarize.py --days 2 --format both`.
3. Write a short briefing for the parent from that output only:
   - one line for Feeding
   - one line for Sleep
   - one line for Diaper
   - then one to three sentences
4. You may add one age-appropriate caution and rotate the topic. If you keep a list of topics already used, put it in a local `topics.log`. That file is gitignored.
5. Add an explicit flag only when logged milk or sleep looks clearly low for what the parent already knows about their child, or when the summary shows temperature, vomiting, rash, cough, injury, medicine, or a hospital visit. Do not invent a medical threshold.
6. This is not medical advice. The parent and their clinician decide. Say that in the briefing.
7. A parent may keep vaccines or checkups in a local `schedule.md`. If that file exists, mention items in the next 7 days. Do not commit it.
8. If `fetch.py` says the feed is unavailable, stop and ask the parent to create a new feed in the PiyoLog app. Do not guess a URL.

Postgres is optional. The briefing should be written from the local summary even when a database is also updated.

Keep briefing text under `briefings/` if you save it. That directory is gitignored.
