"""Scrapes the College Football TV schedule from fbschedules.com.

The week selector on https://fbschedules.com/college-football-tv-schedule/
is AJAX-driven (WordPress admin-ajax.php), not static pages, and the week
option values are opaque post IDs that change every season. This module
first scrapes the current list of week options from the live page, then
fetches each week's schedule HTML fragment and parses out games, dropping
the "Buy Tickets" affiliate links entirely.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from networks import split_networks

SCHEDULE_URL = "https://fbschedules.com/college-football-tv-schedule/"
AJAX_URL = "https://fbschedules.com/wp-admin/admin-ajax.php"
DATA_PATH = Path(__file__).parent / "data" / "games.json"
MANUAL_DIR = Path(__file__).parent / "data" / "manual"

# Sibling local project that drives a real browser engine (camoufox/patchright)
# to pass fbschedules.com's Cloudflare challenge when plain HTTP requests get
# blocked. See ../stealth-fetcher/README.md and ./fetch_fbschedules.py (the
# site-specific fetch definition stealth-fetcher runs).
STEALTH_FETCHER_DIR = Path(os.environ.get("STEALTH_FETCHER_DIR", Path(__file__).parent.parent / "stealth-fetcher"))
FETCH_SCRIPT_PATH = Path(__file__).parent / "fetch_fbschedules.py"
STEALTH_FETCHER_TIMEOUT_SECONDS = 300

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 cfb-tv-schedule-bot"
)

# Base form fields observed on the hidden `fbschedule-frm` form on the
# schedule page — most are blank filters (team/conference/etc.) that must
# still be present for the AJAX endpoint to return the full week.
BASE_FORM_FIELDS = {
    "action": "load_fbschedules_ajax",
    "type": "NCAA",
    "display": "current",
    "team": "",
    "view": "weekly",
    "conference": "",
    "conference-division": "",
    "ncaa-subdivision": "",
    "ispreseason": "",
    "current-page-type": "",
    "is_spring_week_only": "",
}

REQUEST_DELAY_SECONDS = 1.0


@dataclass
class Game:
    week_label: str
    week_value: str
    date: str
    time: str
    away_team: str
    away_rank: str | None
    home_team: str
    home_rank: str | None
    separator: str
    network: str
    order_index: int = 0
    source: str = "fbschedules"
    neutral_site: str | None = None
    networks: list[str] = field(default_factory=list)
    away_logo: str | None = None
    home_logo: str | None = None

    def __post_init__(self):
        if not self.networks:
            self.networks = split_networks(self.network)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch_main_page(session: requests.Session) -> str:
    resp = session.get(SCHEDULE_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_week_options(html: str) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Returns ([(week_label, week_value), ...], base_form_fields) for AJAX weeks.

    Excludes the "Bowl Games" option, which links to a separate static page
    rather than an AJAX week value. Pure function of the main page's HTML —
    no network access — so it can be unit tested against a saved fixture.
    """
    soup = BeautifulSoup(html, "html.parser")

    select = soup.select_one("select[name='select-week-menu']")
    if select is None:
        raise RuntimeError("could not find week selector on schedule page — site markup may have changed")

    weeks = []
    for option in select.find_all("option"):
        value = option.get("value", "")
        label = option.get_text(strip=True)
        if value.startswith("week-"):
            weeks.append((label, value))

    form = soup.select_one("form[name='fbschedule-frm']")
    form_fields = dict(BASE_FORM_FIELDS)
    if form is not None:
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name and name not in ("action",):
                form_fields[name] = inp.get("value", "")

    return weeks, form_fields


def fetch_week_options(session: requests.Session) -> tuple[list[tuple[str, str]], dict[str, str]]:
    return parse_week_options(fetch_main_page(session))


def fetch_week_ajax(session: requests.Session, week_value: str, form_fields: dict[str, str]) -> str:
    params = dict(form_fields)
    params["schedule-week"] = week_value
    params["is_playoff"] = "false"

    resp = session.get(AJAX_URL, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("html", "")


def parse_week_response(html: str, week_label: str, week_value: str) -> list[Game]:
    """Parses one week's AJAX response fragment into Games. Pure function —
    no network access — so it can be unit tested against a saved fixture."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    wrapper = soup.select_one(".current-season-week-scroe-wrapper")
    if wrapper is None:
        return []

    logo_map = _parse_logo_map(soup)

    games: list[Game] = []
    current_date = ""
    for child in wrapper.children:
        name = getattr(child, "name", None)
        if name is None:
            continue
        classes = child.get("class") or []
        if "bowl-year-bg" in classes:
            current_date = child.get_text(strip=True)
        elif name == "table" and "spring" in classes:
            games.extend(_parse_table(child, week_label, week_value, current_date, logo_map))

    return games


def _parse_logo_map(soup: BeautifulSoup) -> dict[str, str]:
    """The AJAX response also includes a `.mobile-alt-schedule` fragment —
    a separate card-layout rendering of the same week for narrow screens —
    whose `<img alt="Team Name" src="...">` tags happen to give us a clean
    team-name -> logo-URL mapping for free, without any extra requests."""
    mobile = soup.select_one(".mobile-alt-schedule")
    if mobile is None:
        return {}
    return {img["alt"]: img["src"] for img in mobile.find_all("img", alt=True, src=True)}


def fetch_week(session: requests.Session, week_label: str, week_value: str, form_fields: dict[str, str]) -> list[Game]:
    html = fetch_week_ajax(session, week_value, form_fields)
    return parse_week_response(html, week_label, week_value)


def _parse_table(table, week_label: str, week_value: str, date: str, logo_map: dict[str, str] | None = None) -> list[Game]:
    logo_map = logo_map or {}
    games = []
    for row in table.select("tbody tr"):
        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        matchup = tds[0].select_one(".row-schedule-content")
        if matchup is None:
            continue

        top_level_spans = matchup.find_all("span", recursive=False)
        away_team = away_rank = home_team = home_rank = separator = ""
        neutral_site = None
        # Layout: [team-span] [separator-span (" at "/" vs ")] [team-span]
        # [optional neutral-site-address-span, e.g. "(in Chicago, IL)"]
        team_spans = []
        for span in top_level_spans:
            classes = span.get("class") or []
            if "school-name-content" in classes:
                team_spans.append(span)
            elif "neutral-site-game-address" in classes:
                neutral_site = span.get_text(strip=True) or None
            elif not separator:
                text = span.get_text(strip=True)
                if text:
                    separator = text

        def _split_team(span):
            rank_span = span.select_one(".team-rank")
            rank = rank_span.get_text(strip=True) if rank_span else None
            # The team name is whatever text remains after removing rank text.
            name_span = span.select_one("span.school-name-content")
            if name_span is not None and rank_span is not None:
                name = name_span.get_text(strip=True)
            else:
                name = span.get_text(strip=True)
                if rank:
                    name = name.replace(rank, "", 1).strip()
            return name, rank

        if len(team_spans) >= 2:
            away_team, away_rank = _split_team(team_spans[0])
            home_team, home_rank = _split_team(team_spans[1])

        if not away_team or not home_team:
            continue

        time_text = tds[1].get_text(strip=True)
        network_text = tds[2].get_text(strip=True)

        games.append(
            Game(
                week_label=week_label,
                week_value=week_value,
                date=date,
                time=time_text,
                away_team=away_team,
                away_rank=away_rank,
                home_team=home_team,
                home_rank=home_rank,
                separator=separator.strip() or "at",
                network=network_text,
                neutral_site=neutral_site,
                away_logo=logo_map.get(away_team),
                home_logo=logo_map.get(home_team),
            )
        )
    return games


def _scrape_fbschedules() -> list[Game]:
    session = _session()
    weeks, form_fields = fetch_week_options(session)
    if not weeks:
        raise RuntimeError("fbschedules.com returned no week options")

    all_games: list[Game] = []
    for i, (label, value) in enumerate(weeks):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        try:
            all_games.extend(fetch_week(session, label, value, form_fields))
        except Exception as exc:  # noqa: BLE001 — keep scraping the rest of the weeks
            print(f"warning: failed to fetch {label} ({value}): {exc}")

    if not all_games:
        raise RuntimeError("fbschedules.com returned zero games across all weeks")

    return all_games


def _scrape_via_stealth_fetcher() -> list[Game]:
    """Falls back to a real browser (via the sibling stealth-fetcher project)
    when fbschedules.com blocks plain HTTP requests with a Cloudflare
    challenge. Runs fetch_fbschedules.py's `run()` in stealth-fetcher's own
    environment, writing week fragments to a temp dir, then parses them the
    same way a manual download would be."""
    if not STEALTH_FETCHER_DIR.exists():
        raise RuntimeError(f"stealth-fetcher not found at {STEALTH_FETCHER_DIR}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="fbschedules_stealth_"))
    try:
        result = subprocess.run(
            ["uv", "run", "stealth-fetcher", "run", str(FETCH_SCRIPT_PATH), "--", "-o", str(tmp_dir)],
            cwd=STEALTH_FETCHER_DIR,
            capture_output=True,
            text=True,
            timeout=STEALTH_FETCHER_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise RuntimeError(f"stealth-fetcher exited {result.returncode}: {result.stderr.strip()[-500:]}")
        return scrape_from_manual_dir(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _week_number_from_filename(path: Path) -> int:
    return int("".join(c for c in path.stem if c.isdigit()))


def scrape_from_manual_dir(manual_dir: Path = MANUAL_DIR) -> list[Game]:
    """Parses `admin-ajax.php` JSON responses saved by hand (e.g. via a
    browser that can pass fbschedules.com's Cloudflare challenge) instead of
    fetching them over the network. Expects one file per week, named
    `week<N>.php`, each containing the same `{"html": "..."}` payload the
    live AJAX endpoint returns."""
    files = sorted(manual_dir.glob("week*.php"), key=_week_number_from_filename)
    if not files:
        raise RuntimeError(f"no week files found in {manual_dir}")

    all_games: list[Game] = []
    for f in files:
        n = _week_number_from_filename(f)
        week_label = f"Week {n}"
        week_value = f"week-{n}"
        payload = json.loads(f.read_text())
        all_games.extend(parse_week_response(payload.get("html", ""), week_label, week_value))
    return all_games


def scrape_all_from_manual(manual_dir: Path = MANUAL_DIR) -> dict:
    """Same output shape as scrape_all(), but sourced from manually saved
    week fragments rather than the network. Not degraded — this is full,
    real fbschedules.com data, just fetched by hand."""
    all_games = scrape_from_manual_dir(manual_dir)
    for i, g in enumerate(all_games):
        g.order_index = i

    weeks = list(dict.fromkeys(g.week_label for g in all_games if g.week_label))
    data = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "games": [asdict(g) for g in all_games],
        "source": "fbschedules_manual",
        "degraded": False,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, indent=2))
    return data


def _load_last_known_good() -> dict | None:
    """Returns the last cached scrape result, if any exist and it has games."""
    if not DATA_PATH.exists():
        return None
    data = json.loads(DATA_PATH.read_text())
    if not data.get("games"):
        return None
    return data


def scrape_all() -> dict:
    """Scrapes fbschedules.com (primary, full-season) over plain HTTP. If
    that's blocked (e.g. by a Cloudflare bot-challenge), retries through
    stealth-fetcher, which drives a real browser engine that can pass it. If
    both fail (site down, or its markup has changed enough that parsing
    yields nothing), reuses the last successfully cached scrape (if one
    exists) rather than serving anything new, so stale-but-complete data
    beats fresh-but-partial data. Only when no cached data exists at all does
    it fall back to the NCAA.com TV schedule preview article (partial —
    mainly opening weeks + bowl season). Either fallback marks the result as
    degraded so the UI can say so."""
    all_games = None
    source = None
    for attempt_source, fetch in (
        ("fbschedules", _scrape_fbschedules),
        ("fbschedules_stealth", _scrape_via_stealth_fetcher),
    ):
        try:
            all_games = fetch()
            source = attempt_source
            break
        except Exception as exc:  # noqa: BLE001
            print(f"warning: {attempt_source} scrape failed ({exc})")

    if all_games is not None:
        degraded = False
    else:
        cached = _load_last_known_good()
        if cached is not None:
            print(f"reusing last known good data from {cached.get('scraped_at')} (source={cached.get('source')})")
            cached["degraded"] = True
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            DATA_PATH.write_text(json.dumps(cached, indent=2))
            return cached

        print("no cached data available, falling back to ncaa.com")
        import ncaa_scraper

        all_games = ncaa_scraper.scrape()
        degraded = True
        source = "ncaa_fallback"

    for i, g in enumerate(all_games):
        g.order_index = i

    weeks = list(dict.fromkeys(g.week_label for g in all_games if g.week_label))

    data = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "games": [asdict(g) for g in all_games],
        "source": source,
        "degraded": degraded,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "manual":
        result = scrape_all_from_manual()
    else:
        result = scrape_all()
    print(f"scraped {len(result['games'])} games across {len(result['weeks'])} weeks")
    print(f"wrote {DATA_PATH}")
