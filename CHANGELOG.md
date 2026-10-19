# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed

- Renamed the project from `cfb-tv-schedule` to `ota-sports-schedule`:
  it now covers over-the-air sports schedules in general, not just college
  football. Dashboard title, package name, Docker image name in the docs,
  and `localStorage` preference keys changed (old keys are still read, so
  saved theme/time zone choices carry over).
- Sources are now pluggable (`schedule.py`): each source scrapes into its
  own cache (`data/<key>_games.json`) and the dashboard serves a merge of
  all of them. A failing source keeps its last cache without affecting the
  others. The CFB cache moved from `data/games.json` to
  `data/cfb_games.json`; an existing file is migrated automatically on
  first load.
- Game start times are normalized server-side to `start_utc` /
  `start_date` for every source (CFB's Eastern wall-clock strings
  included), so the frontend no longer assumes one source's format. As a
  side effect, January CFB games scraped in the fall now get the correct
  (next) year.
- `/api/games` now returns the merged payload with per-source status
  (`sources`) and the St. Paul OTA channel lineup (`channels`).
- The week picker now uses shared Tuesday–Monday broadcast weeks across
  all leagues, labeled with any league's own week number (e.g. "Oct 6 –
  Oct 12 · CFB Week 6"). The table's "Week" column is now "League", and the
  Date column sorts chronologically.
- The Dockerfile builds the bundled stealth-fetcher (camoufox/Firefox,
  apt-get) before the app's own files, so a code or frontend change no
  longer rebuilds it. A CSS-only rebuild went from 10+ minutes to seconds.

### Added

- Minnesota Wild OTA games (KSTP-TV 5 / KSTC-TV 45) from KSTP's 2026-27
  broadcast announcement, via a reusable KSTP article parser
  (`kstp_scraper.py`) that other teams' KSTP announcements can reuse.
- League filter on the dashboard.
- Team logos for leagues whose source has none (`logos.py`). NHL logos
  come from the NHL's public API and are cached in `data/logos/nhl/`. A
  new league only needs a logo provider.
  NHL logos render larger than CFB's (`.team-logo--nhl`) and crop their
  wide SVGs' empty margins, which otherwise shrink them to a sliver.
- St. Paul OTA channel lineup (`stations.py`). Local affiliates show as
  their national network (KSTP-TV 5 is "ABC", FOX9 is "FOX"), so they
  share one filter entry and guide row. Every OTA network is labeled with
  its digital channel ("5.1 ABC", "5.2 45TV") and sorted in channel
  order. Anything with a channel counts as OTA for the "OTA only" preset
  (the default).
- `tzdata` dependency, so time zone conversion works in slim containers.
- Final scores for leagues whose source has none, from a per-league
  score provider (`scores.py`). NHL results come from the NHL's public
  API and are cached in `data/scores/nhl.json`. A refresh looks up only
  days with a finished game that has no result yet.
- Finished games show their score and result ("Final", "Final/OT",
  "Canceled") in the list and TV guide, with the winner's score in bold.
  Scores update on each refresh, so in-progress games show none.
- Footer with links to every source of schedule and score data.

### Fixed

- Finished CFB games no longer show the winner as the away team. Once a
  game is final, fbschedules.com rewrites its row as "Winner 55, Loser
  34" with no "at", and the parser read that as "Winner at Loser". The
  away/home order now comes from the page's mobile layout, which keeps
  it.
- Auto-selected "current week" now advances once a week's games have
  actually wrapped up, instead of sitting on that week indefinitely.
  Previously `computeCurrentWeek()` in `static/app.js` only looked at each
  week's *earliest* kickoff, so a trailing Monday-nighter (or just loading
  the page days after the last Saturday game) kept the prior week selected
  until the next week's first game began — a Tuesday-morning visitor after
  a Monday night game would still see last week's schedule. It now tracks
  each week's earliest *and* latest kickoff, treats a week as "over" once
  its last game plus a 4-hour buffer has passed, and picks the earliest
  week that isn't over yet.

### Security

- `urllib3` 2.7.0 → 2.8.0 in `uv.lock`, fixing CVE-2026-97687 and
  CVE-2026-97689 (both HIGH) found by the homelab's Trivy scan.

### Added

- Time zone picker for the schedule table: auto-detect (default) plus
  Eastern/Central/Mountain/Pacific, next to the existing dark mode toggle.
  Choice is remembered in `localStorage` and game times re-render in the
  selected zone locally, without a refetch.
- Team logos are now downloaded and served locally (`fetch_logos.py`,
  `_localize_logos()` in `scraper.py`, `/logos/<file>` route in `app.py`)
  instead of linking directly to fbschedules.com's CDN — Cloudflare 403s
  hotlinked/non-browser image requests the same as it blocks scraping, so
  the raw URLs never actually loaded in a browser. Logos are fetched once
  per team (cached to `data/logos/`) through the same stealth-fetcher
  browser session used for the HTML fallback.
- Multi-tier fallback for fbschedules.com scrapes: when plain HTTP requests
  get blocked by Cloudflare's bot challenge (as they now do), retries via
  the sibling `stealth-fetcher` project, which drives a real browser engine
  (camoufox/patchright) that can pass it. If that also fails, reuses the
  last successfully cached scrape instead of degrading straight to the
  partial NCAA.com source, so stale-but-complete data beats fresh-but-partial
  data.
- `scraper.py manual` / `scrape_all_from_manual()` — imports a season's worth
  of manually- or `stealth-fetcher`-saved `admin-ajax.php` fragments from
  `data/manual/` instead of scraping over the network.
- `fetch_fbschedules.py` — the site-specific fetch definition (`stealth-fetcher`
  run script) for pulling fbschedules.com's week list and AJAX schedule
  fragments through a browser session that can pass its Cloudflare challenge.
- Persistent team logo cache (`data/team_logos.json`): a team's logo doesn't
  change during a season, so once seen it's kept and used to backfill any
  scrape (including the NCAA.com fallback, which never has logos of its own).
- "Still refreshing…" notice on the dashboard's refresh button after 8
  seconds, since a Cloudflare-blocked refresh now falls back to a slower
  browser-driven fetch that can take a couple of minutes.
- Background auto-refresh interval default lowered from 6 hours to 72
  (`REFRESH_INTERVAL_HOURS`), since the schedule doesn't change that often
  and each refresh is now more expensive when the primary source is blocked.
- Dark mode toggle for the dashboard, with the choice remembered in
  `localStorage`.
- Network filter presets ("National only", "OTA only") so you don't have
  to hand-pick 40 regional sports networks just to find the ABC games.
  OTA is now the default filter on page load.
- Initial scraper for fbschedules.com and NCAA.com college football TV
  schedules, with cross-checking between the two sources and a fallback
  path when one source is degraded.
- Flask dashboard app (`app.py`) serving the cached schedule, a manual
  refresh endpoint, and a background APScheduler auto-refresh job.
- Static sortable/filterable table UI (`static/`).
- Test suite covering parsing fixtures, fallback logic, cross-checking,
  and an opt-in live canary suite against the real sites.
- Dockerfile for containerized deployment.
- Apache License 2.0.
