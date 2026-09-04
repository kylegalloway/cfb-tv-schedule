# cfb-tv-schedule

Scrapes the College Football TV schedule from
[fbschedules.com](https://fbschedules.com/college-football-tv-schedule/) into
a small local dataset, and serves it as a sortable/filterable table (by week,
time, network) with the "Buy Tickets" affiliate links stripped out.

The week selector on the source site is AJAX-driven (WordPress
admin-ajax.php) with opaque, season-specific week IDs — `scraper.py` scrapes
the current week list from the live page first, then fetches each week's
schedule fragment and parses it with BeautifulSoup.

## Local dev

Uses [`uv`](https://docs.astral.sh/uv/) for dependency management — no
manual venv/pip steps.

```bash
# run the scraper standalone (writes data/games.json, prints a summary)
uv run scraper.py

# run the web app — serves the dashboard + /api/games + /api/refresh,
# and starts a background timer that re-scrapes every REFRESH_INTERVAL_HOURS
# (default 72). Defaults to http://localhost:8100
uv run app.py
```

Open `http://localhost:8100`. The page loads instantly from the cached
`data/games.json`; click "Refresh now" to trigger a live re-scrape.

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
- `tests/test_cross_check.py` — parses a game that appears in both sources'
  fixtures and checks the two independently-scraped values agree (after
  normalizing each source's own time/network format).
- `tests/test_live_site.py` (marked `live`) — hits fbschedules.com and
  ncaa.com for real. This is the test suite that actually detects "the site
  changed its markup and scraping is now broken" — the fixture tests can't,
  since fixtures are frozen. Run it periodically, not on every change.

## Docker

```bash
docker build -t cfb-tv-schedule .
docker run -p 8100:8100 -v "$(pwd)/data:/app/data" cfb-tv-schedule
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
