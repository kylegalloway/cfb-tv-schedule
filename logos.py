"""Team logos for leagues whose schedule source doesn't carry them.

CFB logos come with the fbschedules.com scrape itself (scraper.py's
_localize_logos()). Other sources, like KSTP's articles, only name the
teams — so each league can register a LogoProvider that maps team names to
logo URLs, and this module downloads those logos into
data/logos/<league>/<team-slug><ext> (served by app.py's /logos/ route).

- fetch_missing(games) runs after a refresh: downloads any logo a game's
  team doesn't have locally yet. Logos rarely change, so once a file is
  on disk it's kept; delete it to re-fetch.
- apply(games) runs on every load: fills a game's empty away_logo /
  home_logo from the files on disk. No network access.

Adding a league
---------------
Write a provider with a `logo_urls()` method returning {team name: URL}
and register it in PROVIDERS under the league's `league` value. Team names
are matched loosely (case, accents and punctuation ignored), so "Montreal
Canadiens" finds "Montréal Canadiens".
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Protocol

import requests

from scraper import LOGO_IMAGE_DIR, USER_AGENT


class LogoProvider(Protocol):
    def logo_urls(self) -> dict[str, str]: ...


class NhlLogos:
    """Official logos from the NHL's public web API. Its standings list
    every current team with its full name ("Minnesota Wild") and logo."""

    STANDINGS_URL = "https://api-web.nhle.com/v1/standings/now"

    def logo_urls(self) -> dict[str, str]:
        resp = requests.get(self.STANDINGS_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        return {t["teamName"]["default"]: t["teamLogo"] for t in resp.json()["standings"]}


PROVIDERS: dict[str, LogoProvider] = {
    "NHL": NhlLogos(),
}


def team_slug(name: str) -> str:
    """"Montréal Canadiens" -> "montreal-canadiens", "St. Louis Blues" ->
    "st-louis-blues"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def _league_dir(league: str) -> Path:
    return LOGO_IMAGE_DIR / team_slug(league)


def _local_logos(league: str) -> dict[str, Path]:
    """team slug -> logo file already on disk for `league`."""
    league_dir = _league_dir(league)
    if not league_dir.is_dir():
        return {}
    return {p.stem: p for p in league_dir.iterdir() if p.is_file()}


def _download(url: str) -> bytes:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.content


def _teams_by_league(games: list[dict]) -> dict[str, set[str]]:
    teams: dict[str, set[str]] = {}
    for g in games:
        for team, logo in ((g.get("away_team"), g.get("away_logo")), (g.get("home_team"), g.get("home_logo"))):
            if team and not logo:
                teams.setdefault(g.get("league") or "", set()).add(team)
    return teams


def fetch_missing(games: list[dict]) -> None:
    """Downloads logos for teams that have none, for leagues with a
    provider. A provider or download failing is logged and skipped — a
    missing logo just isn't shown."""
    for league, teams in _teams_by_league(games).items():
        provider = PROVIDERS.get(league)
        if provider is None:
            continue
        on_disk = _local_logos(league)
        missing = {team_slug(t): t for t in teams if team_slug(t) not in on_disk}
        if not missing:
            continue

        try:
            urls = {team_slug(name): url for name, url in provider.logo_urls().items()}
        except Exception as exc:  # noqa: BLE001 — logos are optional
            print(f"warning: {league} logo lookup failed ({exc})")
            continue

        league_dir = _league_dir(league)
        league_dir.mkdir(parents=True, exist_ok=True)
        for slug, team in missing.items():
            url = urls.get(slug)
            if url is None:
                print(f"warning: no {league} logo found for {team!r}")
                continue
            ext = Path(url.split("?", 1)[0]).suffix or ".png"
            try:
                (league_dir / f"{slug}{ext}").write_bytes(_download(url))
            except Exception as exc:  # noqa: BLE001 — keep fetching the rest
                print(f"warning: failed to fetch {league} logo for {team!r} ({url}): {exc}")


def apply(games: list[dict]) -> None:
    """Points each game's empty away_logo / home_logo at its team's logo
    on disk, if there is one."""
    local: dict[str, dict[str, Path]] = {}
    for g in games:
        league = g.get("league") or ""
        if league not in PROVIDERS:
            continue
        if league not in local:
            local[league] = _local_logos(league)
        for team_key, logo_key in (("away_team", "away_logo"), ("home_team", "home_logo")):
            path = local[league].get(team_slug(g.get(team_key) or ""))
            if path is not None and not g.get(logo_key):
                g[logo_key] = f"/logos/{path.relative_to(LOGO_IMAGE_DIR).as_posix()}"
