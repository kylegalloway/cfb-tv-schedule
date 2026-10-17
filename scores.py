"""Final scores for leagues whose schedule source doesn't carry them.

CFB scores come with the fbschedules.com scrape itself (scraper.py). Other
sources, like KSTP's articles, are announcements written before the season,
so each league can register a ScoreProvider that looks up a day's results.
Results are cached in data/scores/<league>.json as {"YYYY-MM-DD": [result,
...]}, so a failed lookup keeps the results already on disk.

- fetch_missing(games) runs after a refresh: looks up each day that has a
  game which should be over but has no result yet.
- apply(games) runs on every load: fills a game's empty status / scores
  from the cache. No network access.

Adding a league
---------------
Write a provider with a `results(date)` method returning that day's
finished games as dicts with `away_team`, `home_team`, `away_score`,
`home_score`, `status` and `start_utc`, and register it in PROVIDERS under
the league's `league` value. Team names match loosely, and a provider may
give just the nickname ("Bruins" finds "Boston Bruins").
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import requests

from logos import team_slug
from scraper import USER_AGENT

SCORES_DIR = Path(__file__).parent / "data" / "scores"

# Games don't carry an end time; only look for a result once a game has
# had this long to finish.
GAME_DURATION = timedelta(hours=4)

# A source's start time and the provider's can disagree (a rescheduled
# puck drop, a rounded article time); still the same game within this.
START_TOLERANCE = timedelta(hours=12)


class ScoreProvider(Protocol):
    def results(self, date: str) -> list[dict]: ...


class NhlScores:
    """Results from the NHL's public web API: every game on one date."""

    SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
    FINAL_STATES = {"FINAL", "OFF"}

    def results(self, date: str) -> list[dict]:
        resp = requests.get(self.SCORE_URL.format(date=date), headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        results = []
        for g in resp.json().get("games", []):
            if g.get("gameState") not in self.FINAL_STATES:
                continue
            # "REG", "OT" or "SO"
            period = (g.get("gameOutcome") or {}).get("lastPeriodType")
            results.append({
                "away_team": g["awayTeam"]["name"]["default"],
                "home_team": g["homeTeam"]["name"]["default"],
                "away_score": g["awayTeam"].get("score"),
                "home_score": g["homeTeam"].get("score"),
                "status": f"Final/{period}" if period in ("OT", "SO") else "Final",
                "start_utc": g["startTimeUTC"],
            })
        return results


PROVIDERS: dict[str, ScoreProvider] = {
    "NHL": NhlScores(),
}


def _cache_path(league: str) -> Path:
    return SCORES_DIR / f"{team_slug(league)}.json"


def _load_cache(league: str) -> dict[str, list[dict]]:
    path = _cache_path(league)
    return json.loads(path.read_text()) if path.exists() else {}


def _same_team(name: str, provider_name: str) -> bool:
    """"Boston Bruins" matches "Boston Bruins" or just "Bruins"."""
    full, short = team_slug(name), team_slug(provider_name)
    return bool(short) and (full == short or full.endswith(f"-{short}"))


def _find_result(game: dict, results: list[dict]) -> dict | None:
    start = datetime.fromisoformat(game["start_utc"])
    for r in results:
        if (
            _same_team(game.get("away_team") or "", r["away_team"])
            and _same_team(game.get("home_team") or "", r["home_team"])
            and abs(datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) - start) <= START_TOLERANCE
        ):
            return r
    return None


def _pending(games: list[dict], league: str, now: datetime) -> list[dict]:
    """Games in `league` that should be over but have no result."""
    return [
        g for g in games
        if (g.get("league") or "") == league
        and not g.get("status")
        and g.get("start_utc") and g.get("start_date")
        and datetime.fromisoformat(g["start_utc"]) + GAME_DURATION <= now
    ]


def fetch_missing(games: list[dict], now: datetime | None = None) -> None:
    """Looks up results for finished games that have none, for leagues
    with a provider. A failed lookup is logged and skipped — the game just
    shows no score until a later refresh finds it."""
    now = now or datetime.now(timezone.utc)
    for league, provider in PROVIDERS.items():
        cache = _load_cache(league)
        dates = sorted({
            g["start_date"] for g in _pending(games, league, now)
            if _find_result(g, cache.get(g["start_date"], [])) is None
        })
        changed = False
        for date in dates:
            try:
                cache[date] = provider.results(date)
                changed = True
            except Exception as exc:  # noqa: BLE001 — scores are optional
                print(f"warning: {league} score lookup for {date} failed ({exc})")
        if changed:
            SCORES_DIR.mkdir(parents=True, exist_ok=True)
            _cache_path(league).write_text(json.dumps(cache, indent=2, sort_keys=True))


def apply(games: list[dict]) -> None:
    """Fills each game's empty status / scores from the cached results."""
    caches: dict[str, dict[str, list[dict]]] = {}
    for g in games:
        league = g.get("league") or ""
        if league not in PROVIDERS or g.get("status") or not g.get("start_utc"):
            continue
        if league not in caches:
            caches[league] = _load_cache(league)
        result = _find_result(g, caches[league].get(g.get("start_date") or "", []))
        if result is not None:
            g["status"] = result["status"]
            g["away_score"] = result["away_score"]
            g["home_score"] = result["home_score"]
