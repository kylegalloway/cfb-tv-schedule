"""Scrapes over-the-air game lists from KSTP (Hubbard Broadcasting) TV
partnership announcement articles — e.g. the Minnesota Wild's 2026-27 slate
on KSTP-TV 5 / KSTC-TV 45.

Unlike fbschedules.com, these are plain WordPress articles with no bot
challenge, and KSTP writes them in a consistent shape: one `<li>` per game,

    <li><em>Saturday, Oct. 3</em> vs. Boston Bruins at 7 p.m. on <strong>KSTC-TV 45</strong></li>

so one parser covers any team's article. Times are the team's local
wall clock, and the article only gives month + day, so the year is inferred
from the "2026-27 season" phrase in the body (months from the season's
start month onward -> first year, earlier months -> second year). A
single-year season ("2026 season") is also accepted.

To add another team, add a KstpBroadcastArticle to schedule.SOURCES.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from scraper import USER_AGENT, Game

DATA_DIR = Path(__file__).parent / "data"

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_SEASON_RE = re.compile(r"\b(20\d{2})(?:-(\d{2}))?\s+season\b", re.IGNORECASE)

# "Saturday, Jan. 16 at St. Louis Blues at 6 p.m. on KSTC-TV 45" — the
# opponent is matched lazily so a road game's leading "at" isn't confused
# with the " at <time>" that follows the opponent's name.
_GAME_RE = re.compile(
    r"^(?P<weekday>[A-Za-z]+),\s+(?P<month>[A-Za-z]+)\.?\s+(?P<day>\d{1,2})\s+"
    r"(?P<sep>vs\.?|at)\s+(?P<opponent>.+?)\s+at\s+"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>[ap])\.?\s*m\.?\s+"
    r"on\s+(?P<network>.+?)\s*$",
    re.IGNORECASE,
)


def parse_season(text: str) -> tuple[int, bool]:
    """Returns (start_year, spans_two_years) from e.g. "2026-27 season"."""
    match = _SEASON_RE.search(text)
    if match is None:
        raise RuntimeError("could not find a 'YYYY(-YY) season' phrase in the KSTP article — markup or wording may have changed")
    return int(match.group(1)), match.group(2) is not None


def parse_article(
    html: str,
    team: str,
    league: str,
    zone: ZoneInfo,
    season_start_month: int = 8,
    source: str = "kstp",
) -> list[Game]:
    """Parses an announcement article's HTML into Games from `team`'s point
    of view ("vs." = home, "at" = road). Pure function — no network access —
    so it can be unit tested against a saved fixture."""
    soup = BeautifulSoup(html, "html.parser")
    season_start, spans_two_years = parse_season(soup.get_text(" ", strip=True))

    games: list[Game] = []
    for li in soup.find_all("li"):
        match = _GAME_RE.match(li.get_text(" ", strip=True))
        if match is None:
            continue
        month = _MONTHS.get(match["month"][:3].lower())
        if month is None:
            continue

        year = season_start + 1 if spans_two_years and month < season_start_month else season_start
        hour = int(match["hour"]) % 12 + (12 if match["ampm"].lower() == "p" else 0)
        minute = int(match["minute"] or 0)
        start = datetime(year, month, int(match["day"]), hour, minute, tzinfo=zone)

        opponent = match["opponent"].strip()
        is_home = match["sep"].lower().startswith("vs")
        games.append(
            Game(
                week_label="",
                week_value="",
                date=f"{start:%A, %B} {start.day}",
                time=f"{start.hour % 12 or 12}:{start:%M}{'am' if start.hour < 12 else 'pm'}",
                away_team=opponent if is_home else team,
                away_rank=None,
                home_team=team if is_home else opponent,
                home_rank=None,
                separator="at",
                network=match["network"].strip(),
                source=source,
                league=league,
                start_utc=start.astimezone(timezone.utc).isoformat(),
                time_zone=zone.key,
            )
        )

    return games


@dataclass
class KstpBroadcastArticle:
    """One team's KSTP OTA-broadcast announcement, as a schedule source."""

    key: str
    url: str
    team: str
    league: str
    zone: str = "America/Chicago"
    # Month the season starts in; dates before it belong to the season's
    # second calendar year (only matters for "YYYY-YY season" articles).
    season_start_month: int = 8

    @property
    def data_path(self) -> Path:
        return DATA_DIR / f"{self.key}_games.json"

    def parse(self, html: str) -> list[Game]:
        return parse_article(html, self.team, self.league, ZoneInfo(self.zone), self.season_start_month)

    def fetch(self) -> str:
        resp = requests.get(self.url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        return resp.text

    def refresh(self) -> dict:
        """Fetches + parses the article and caches it to data_path. Raises
        if the page yields no games, so the caller keeps the last good
        cache instead of overwriting it with nothing."""
        games = self.parse(self.fetch())
        if not games:
            raise RuntimeError(f"KSTP article for {self.team} yielded zero games — markup may have changed")

        for i, g in enumerate(games):
            g.order_index = i

        data = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "games": [asdict(g) for g in games],
            "source": "kstp",
            "degraded": False,
        }
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_path.write_text(json.dumps(data, indent=2))
        return data
