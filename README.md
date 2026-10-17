# ota-sports-schedule

Scrapes over-the-air (OTA) sports TV schedules into a small local dataset,
and serves them as one sortable/filterable table and TV-guide grid (by
week, league, team, network, time zone). It started as a college football
schedule (`cfb-tv-schedule`) and grows one source at a time.

## Sources

| Key        | League | Source                                                                                                   | Module            |
|------------|--------|----------------------------------------------------------------------------------------------------------|-------------------|
| `cfb`      | CFB    | [fbschedules.com](https://fbschedules.com/college-football-tv-schedule/), NCAA.com fallback              | `scraper.py`      |
| `nhl_wild` | NHL    | [KSTP Wild OTA announcement](https://kstp.com/minnesota-sports/kstp-45tv-to-broadcast-10-minnesota-wild-games-this-season/) (KSTP-TV 5 / KSTC-TV 45) | `kstp_scraper.py` |

Each source caches to its own file (`data/<key>_games.json`), and
`schedule.py` merges them for the dashboard. One source failing keeps its
last cache and does not affect the others.

**CFB:** the week selector on fbschedules.com is AJAX-driven (WordPress
admin-ajax.php) with opaque, season-specific week IDs. `scraper.py`
scrapes the current week list from the live page first, then fetches each
week's schedule fragment and parses it with BeautifulSoup. The "Buy
Tickets" affiliate links are dropped.

**KSTP:** KSTP's OTA partnership articles list one game per `<li>` in a
fixed format. `kstp_scraper.KstpBroadcastArticle` parses any team's article.

### Add a source

1. Write a source with `key`, `data_path` and `refresh()`.
   See the docstring at the top of `schedule.py` for the full contract.
2. For another KSTP team article, add a `KstpBroadcastArticle` instead.
3. Register the source in `schedule.SOURCES`.
4. Add a trimmed HTML fixture and a parsing test under `tests/`.
5. Add a `live` canary test to `tests/test_live_site.py`.
6. If the source names a local station that is not in `stations.LINEUP`,
   add the station with its digital channel.
7. If the source has no team logos and its league is not in
   `logos.PROVIDERS`, add a logo provider for the league.
8. If the source has no scores and its league is not in
   `scores.PROVIDERS`, add a score provider for the league.

**Scores:** finished CFB games get their score and result from the
fbschedules.com scrape. For a finished game, the site lists the winner
first, so the scraper takes the away/home order from the page's mobile
layout. Other leagues get results from a provider in `scores.py` (the
NHL's public API for NHL), cached in `data/scores/<league>.json`. Scores
update only on a refresh, so in-progress games show no score.

**Logos:** CFB logos come with the fbschedules.com scrape. Other leagues
get logos from a provider in `logos.py` (the NHL's public API for NHL).
A refresh downloads missing logos to `data/logos/<league>/`.

**Channels:** `stations.py` holds the St. Paul OTA lineup. Each local
affiliate shows as its national network ("KSTP-TV 5" is "ABC"), labeled
and sorted by digital channel ("5.1 ABC").

Weeks in the dashboard are shared Tuesday–Monday broadcast weeks (US
Eastern). A league with numbered weeks sets `week_label` on its games, and
the week picker shows it (for example "Oct 6 – Oct 12 · CFB Week 6").

## Local dev

Uses [`uv`](https://docs.astral.sh/uv/) for dependency management — no
manual venv/pip steps.

```bash
# refresh every source (writes data/<key>_games.json, prints a summary)
uv run schedule.py

# run only the CFB scraper (writes data/cfb_games.json)
uv run scraper.py

# run the web app — serves the dashboard + /api/games + /api/refresh,
# and starts a background timer that re-scrapes every REFRESH_INTERVAL_HOURS
# (default 72). Defaults to http://localhost:8100
uv run app.py
```

Open `http://localhost:8100`. The page loads instantly from the cached
per-source caches in `data/`; click "Refresh now" to re-scrape every source.

## Testing

```bash
# offline tests (parsing logic against saved fixtures, fallback wiring) —
# fast, no network, this is what runs in CI
uv run pytest

# live canary tests — hit the real sites to catch upstream markup changes.
# Not run by default (see pyproject.toml's `-m "not live"`); run explicitly:
uv run pytest -m live
```

- `tests/test_scraper_parsing.py` / `tests/test_ncaa_parsing.py` — parse
  saved HTML fixtures (`tests/fixtures/`, real snapshots trimmed down) and
  assert the extracted games are correct. These catch parsing bugs without
  touching the network.
- `tests/test_scrape_all_fallback.py` — exercises `scraper.scrape_all()`'s
  fallback decision logic with the network mocked out.
- `tests/test_kstp_parsing.py` — parses a saved KSTP Wild article and
  checks home/road, Central time and the season's year rollover.
- `tests/test_schedule_merge.py` — the multi-source merge, per-source
  failure isolation, time normalization and the legacy cache migration.
- `tests/test_stations.py` and `tests/test_logos.py` — the St. Paul
  channel lineup and the per-league logo lookup.
- `tests/test_cross_check.py` — parses a game that appears in both sources'
  fixtures and checks the two independently-scraped values agree (after
  normalizing each source's own time/network format).
- `tests/test_live_site.py` (marked `live`) — hits fbschedules.com,
  ncaa.com and kstp.com for real. This is the test suite that actually detects "the site
  changed its markup and scraping is now broken" — the fixture tests can't,
  since fixtures are frozen. Run it periodically, not on every change.

## Docker

```bash
docker build -t ota-sports-schedule .
docker run -p 8100:8100 -v "$(pwd)/data:/app/data" ota-sports-schedule
```

## Config

| Env var                  | Default | Purpose                                   |
|---------------------------|---------|--------------------------------------------|
| `PORT`                    | `8100`  | Port the Flask app listens on              |
| `REFRESH_INTERVAL_HOURS`  | `72`    | Background auto-refresh interval           |

## Deployment

This repo intentionally has no `docker-compose.yml` — it's meant to run
alongside an existing homelab media stack. See the homelab repo's
`docs/media/provisioning.md` for the compose service block and
`.taskfiles/media.yaml` for the deploy task.
