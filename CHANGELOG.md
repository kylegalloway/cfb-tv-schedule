# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

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
