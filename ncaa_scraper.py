"""Fallback data source: the NCAA.com TV schedule preview article.

Used only when fbschedules.com (the primary source, see scraper.py) is
unreachable or its markup has drifted enough that parsing yields nothing.
This source is a static article (no AJAX), but it's a *preview*, not a full
schedule: it typically only covers the season-opening weeks plus bowl
season, not every regular-season week. Treat any data from here as partial.

Article layout:
    <p><strong>Thursday, Sept. 3</strong></p>
    <p>
      <a href="...">UMass at Rutgers | 6 p.m. | Big Ten Network</a><br>
      <a href="...">No. 25 Missouri at ... | 8 p.m. | SEC Network</a><br>
      ...
    </p>
    <p><strong>Friday, Sept. 4</strong></p>
    ...
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scraper import Game, USER_AGENT

NCAA_URL = "https://www.ncaa.com/news/football/article/college-football-tv-schedule-game-times-preview"

GAME_LINE_RE = re.compile(
    r"^(?:No\.\s*(?P<away_rank>\d+)\s+)?(?P<away>.+?)\s+(?P<sep>at|vs\.)\s+"
    r"(?:No\.\s*(?P<home_rank>\d+)\s+)?(?P<home>.+?)(?:\s*\([^)]*\))?\s*\|\s*"
    r"(?P<time>.+?)\s*\|\s*(?P<network>.+)$"
)


def fetch_page(session: requests.Session) -> str:
    resp = session.get(NCAA_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_schedule(html: str) -> list[Game]:
    """Pure function of the article HTML — no network access — so it can be
    unit tested against a saved fixture."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".article-body")
    if body is None:
        return []

    games: list[Game] = []
    current_date = ""
    for p in body.find_all("p"):
        strong = p.find("strong")
        if strong is not None and not p.find("a"):
            current_date = strong.get_text(strip=True)
            continue

        for a in p.find_all("a", href=True):
            if "/game/" not in a["href"]:
                continue
            text = a.get_text(strip=True)
            match = GAME_LINE_RE.match(text)
            if not match:
                continue
            gd = match.groupdict()
            games.append(
                Game(
                    week_label="",
                    week_value="",
                    date=current_date,
                    time=gd["time"],
                    away_team=gd["away"].strip(),
                    away_rank=gd["away_rank"],
                    home_team=gd["home"].strip(),
                    home_rank=gd["home_rank"],
                    separator="vs" if gd["sep"].startswith("vs") else "at",
                    network=gd["network"].strip(),
                    source="ncaa",
                )
            )

    return games


def scrape() -> list[Game]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return parse_schedule(fetch_page(session))


if __name__ == "__main__":
    result = scrape()
    print(f"scraped {len(result)} games from ncaa.com (fallback/partial source)")
