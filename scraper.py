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


def scrape_all() -> dict:
    """Scrapes fbschedules.com (primary, full-season). If it fails entirely
    (site down, or its markup has changed enough that parsing yields nothing),
    falls back to the NCAA.com TV schedule preview article (partial — mainly
    opening weeks + bowl season), and marks the result as degraded so the UI
    can say so."""
    degraded = False
    source = "fbschedules"
    try:
        all_games = _scrape_fbschedules()
    except Exception as exc:  # noqa: BLE001
        print(f"warning: fbschedules.com scrape failed ({exc}), falling back to ncaa.com")
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
    result = scrape_all()
    print(f"scraped {len(result['games'])} games across {len(result['weeks'])} weeks")
    print(f"wrote {DATA_PATH}")
