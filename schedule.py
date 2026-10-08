"""Combines every source's scraped schedule into the one payload the
dashboard serves.

Each source scrapes and caches to its own JSON file (so one source's
fallback/"last known good" logic never sees another source's games), and
this module merges those caches at read time.

Adding a source
---------------
A source is anything with:

- `key`           unique id, e.g. "nhl_wild"
- `data_path`     where its cache JSON lives: {"scraped_at", "games", "source", "degraded"}
- `refresh()`     re-scrapes and rewrites data_path; raises on failure

Each cached game is a scraper.Game dict. Set `league` (shown in the League
column/filter), and give its start time either as `start_utc` (ISO 8601,
preferred) or as `date` ("Saturday, October 3") + `time` ("7:00pm") wall
clock in `time_zone`. `_normalize_game()` fills in `start_utc` / `start_date`
from the latter, so the frontend only ever reads those two.

Network names go through stations.local_network() too, so a source can
name a local affiliate ("KSTP-TV 5") and it still shows as the national
network ("ABC") on its St. Paul channel ("5.1"). A new local station only
needs a row in stations.LINEUP.

A source doesn't need to supply logos: a league with a provider in
logos.PROVIDERS gets its teams' logos filled in from there.

Then register it in SOURCES below. A league with numbered weeks (like CFB's
"Week 7") can also set `week_label`; the dashboard shows it next to the
shared Tuesday-Monday broadcast week.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import kstp_scraper
import logos
import scraper
import stations


@dataclass
class ModuleSource:
    """Adapts a scraper module exposing DATA_PATH + scrape_all() (the CFB
    scraper's original interface) to the source shape above. DATA_PATH is
    read at call time so tests can monkeypatch it on the module."""

    key: str
    module: ModuleType

    @property
    def data_path(self) -> Path:
        return self.module.DATA_PATH

    def refresh(self) -> dict:
        return self.module.scrape_all()


SOURCES = [
    ModuleSource("cfb", scraper),
    kstp_scraper.KstpBroadcastArticle(
        key="nhl_wild",
        url="https://kstp.com/minnesota-sports/kstp-45tv-to-broadcast-10-minnesota-wild-games-this-season/",
        team="Minnesota Wild",
        league="NHL",
    ),
]

# Before this project covered more than college football, the CFB cache
# lived at data/games.json. Move it into its per-source home once, so an
# existing deployment's data volume keeps its last-known-good scrape.
LEGACY_CFB_DATA_PATH = Path(__file__).parent / "data" / "games.json"

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
_DATE_RE = re.compile(r",\s*([A-Za-z]+)\.?\s+(\d{1,2})\s*$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*(am|pm)$", re.IGNORECASE)


def _migrate_legacy_cache() -> None:
    if LEGACY_CFB_DATA_PATH.exists() and not scraper.DATA_PATH.exists():
        scraper.DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        LEGACY_CFB_DATA_PATH.rename(scraper.DATA_PATH)


def _normalize_game(game: dict, scraped_at: str | None) -> dict:
    """Fills `league`, `start_utc` and `start_date` for games whose source
    only gave wall-clock `date`/`time` strings (CFB, and caches written
    before these fields existed). The year isn't in the date string, so it
    comes from when the source was scraped, rolling into the next year for
    a date that would otherwise be more than ~6 months in the past (e.g. a
    January bowl game scraped in August)."""
    # Serialized Games carry these keys as null, so test truthiness rather
    # than setdefault().
    game["league"] = game.get("league") or "CFB"
    # dict.fromkeys dedupes while keeping order, e.g. "ABC or KSTP-TV 5".
    game["networks"] = list(dict.fromkeys(stations.local_network(n) for n in game.get("networks") or []))
    zone = ZoneInfo(game.get("time_zone") or scraper.CFB_TIME_ZONE)
    if game.get("start_utc"):
        if not game.get("start_date"):
            game["start_date"] = datetime.fromisoformat(game["start_utc"]).astimezone(zone).date().isoformat()
        return game

    date_match = _DATE_RE.search(game.get("date") or "")
    month = _MONTHS.get(date_match.group(1).lower()) if date_match else None
    if month is None:
        return game

    ref = datetime.fromisoformat(scraped_at) if scraped_at else datetime.now(timezone.utc)
    year = ref.year + 1 if month < ref.month - 6 else ref.year
    day = int(date_match.group(2))
    game["start_date"] = f"{year:04d}-{month:02d}-{day:02d}"

    time_match = _TIME_RE.match((game.get("time") or "").strip())
    if time_match:
        hour = int(time_match.group(1)) % 12 + (12 if time_match.group(3).lower() == "pm" else 0)
        start = datetime(year, month, day, hour, int(time_match.group(2)), tzinfo=zone)
        game["start_utc"] = start.astimezone(timezone.utc).isoformat()
    return game


def load_all() -> dict:
    """Merges every source's cached scrape. A source with no cache yet is
    just absent from `sources` and contributes no games."""
    _migrate_legacy_cache()

    games: list[dict] = []
    sources: dict[str, dict] = {}
    for source in SOURCES:
        if not source.data_path.exists():
            continue
        data = json.loads(source.data_path.read_text())
        sources[source.key] = {
            "scraped_at": data.get("scraped_at"),
            "source": data.get("source"),
            "degraded": bool(data.get("degraded")),
        }
        games.extend(_normalize_game(g, data.get("scraped_at")) for g in data.get("games", []))
    logos.apply(games)

    scraped = [s["scraped_at"] for s in sources.values() if s["scraped_at"]]
    return {
        "scraped_at": max(scraped) if scraped else None,
        "games": games,
        "sources": sources,
        # The dashboard's degraded banner describes the CFB NCAA.com fallback
        # specifically; other sources just keep serving their last good cache.
        "degraded": sources.get("cfb", {}).get("degraded", False),
        # OTA network -> St. Paul digital channel, e.g. {"ABC": "5.1"}.
        "channels": stations.CHANNELS,
    }


def refresh_all() -> dict:
    """Re-scrapes every source. One source failing outright leaves its
    previous cache in place rather than taking the others down with it."""
    _migrate_legacy_cache()
    for source in SOURCES:
        try:
            source.refresh()
        except Exception as exc:  # noqa: BLE001 — keep refreshing the other sources
            print(f"warning: {source.key} refresh failed ({exc}); keeping its last cached data")
    logos.fetch_missing(load_all()["games"])
    return load_all()


def has_cached_data() -> bool:
    _migrate_legacy_cache()
    return any(source.data_path.exists() for source in SOURCES)


if __name__ == "__main__":
    result = refresh_all()
    print(f"merged {len(result['games'])} games from {', '.join(result['sources']) or 'no sources'}")
