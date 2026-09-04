"""Tests scraper.scrape_all()'s fallback wiring — no network access.

_scrape_fbschedules, _scrape_via_stealth_fetcher and ncaa_scraper.scrape are
all monkeypatched so this only exercises the fallback decision logic (and
the resulting data["source"] / data["degraded"] flags), not either site's
actual parsing or stealth-fetcher's subprocess call.
"""

import json

import scraper
from scraper import Game


def _boom_stealth_fetcher():
    raise RuntimeError("stealth-fetcher not available in tests")


def _fake_game(source="fbschedules"):
    return Game(
        week_label="Week 1",
        week_value="week-1",
        date="Thursday, September 3",
        time="6:00pm",
        away_team="Team A",
        away_rank=None,
        home_team="Team B",
        home_rank=None,
        separator="at",
        network="ESPN",
        source=source,
    )


def test_scrape_all_uses_primary_source_when_fbschedules_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA_PATH", tmp_path / "games.json")
    monkeypatch.setattr(scraper, "_scrape_fbschedules", lambda: [_fake_game("fbschedules")])

    data = scraper.scrape_all()

    assert data["source"] == "fbschedules"
    assert data["degraded"] is False
    assert len(data["games"]) == 1
    assert json.loads(scraper.DATA_PATH.read_text())["source"] == "fbschedules"


def test_scrape_all_uses_stealth_fetcher_when_fbschedules_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA_PATH", tmp_path / "games.json")

    def _boom():
        raise RuntimeError("fbschedules.com is down")

    monkeypatch.setattr(scraper, "_scrape_fbschedules", _boom)
    monkeypatch.setattr(scraper, "_scrape_via_stealth_fetcher", lambda: [_fake_game("fbschedules")])

    import ncaa_scraper

    def _fail_ncaa():
        raise AssertionError("should not fall back to ncaa.com when stealth-fetcher succeeds")

    monkeypatch.setattr(ncaa_scraper, "scrape", _fail_ncaa)

    data = scraper.scrape_all()

    assert data["source"] == "fbschedules_stealth"
    assert data["degraded"] is False
    assert len(data["games"]) == 1


def test_scrape_all_falls_back_to_ncaa_when_fbschedules_and_stealth_fetcher_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA_PATH", tmp_path / "games.json")

    def _boom():
        raise RuntimeError("fbschedules.com is down")

    monkeypatch.setattr(scraper, "_scrape_fbschedules", _boom)
    monkeypatch.setattr(scraper, "_scrape_via_stealth_fetcher", _boom_stealth_fetcher)

    import ncaa_scraper

    monkeypatch.setattr(ncaa_scraper, "scrape", lambda: [_fake_game("ncaa")])

    data = scraper.scrape_all()

    assert data["source"] == "ncaa_fallback"
    assert data["degraded"] is True
    assert len(data["games"]) == 1
    assert data["games"][0]["source"] == "ncaa"


def test_scrape_all_reuses_cached_data_when_fbschedules_raises(tmp_path, monkeypatch):
    data_path = tmp_path / "games.json"
    monkeypatch.setattr(scraper, "DATA_PATH", data_path)

    cached = {
        "scraped_at": "2026-08-30T12:00:00+00:00",
        "weeks": ["Week 1"],
        "games": [
            {
                "week_label": "Week 1",
                "week_value": "week-1",
                "date": "Thursday, September 3",
                "time": "6:00pm",
                "away_team": "Team A",
                "away_rank": None,
                "home_team": "Team B",
                "home_rank": None,
                "separator": "at",
                "network": "ESPN",
                "order_index": 0,
                "source": "fbschedules",
                "neutral_site": None,
                "networks": ["ESPN"],
                "away_logo": "https://example.com/a.png",
                "home_logo": "https://example.com/b.png",
            }
        ],
        "source": "fbschedules",
        "degraded": False,
    }
    data_path.write_text(json.dumps(cached))

    def _boom():
        raise RuntimeError("fbschedules.com is down")

    monkeypatch.setattr(scraper, "_scrape_fbschedules", _boom)
    monkeypatch.setattr(scraper, "_scrape_via_stealth_fetcher", _boom_stealth_fetcher)

    import ncaa_scraper

    def _fail_ncaa():
        raise AssertionError("should not fall back to ncaa.com when cached data exists")

    monkeypatch.setattr(ncaa_scraper, "scrape", _fail_ncaa)

    data = scraper.scrape_all()

    assert data["source"] == "fbschedules"
    assert data["degraded"] is True
    assert data["scraped_at"] == "2026-08-30T12:00:00+00:00"
    assert data["games"][0]["away_logo"] == "https://example.com/a.png"
    assert json.loads(data_path.read_text())["degraded"] is True


def test_scrape_all_falls_back_when_fbschedules_returns_zero_games(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA_PATH", tmp_path / "games.json")
    monkeypatch.setattr(scraper, "fetch_week_options", lambda session: ([("Week 1", "week-1")], {}))
    monkeypatch.setattr(scraper, "fetch_week", lambda *a, **k: [])
    monkeypatch.setattr(scraper, "_scrape_via_stealth_fetcher", _boom_stealth_fetcher)

    import ncaa_scraper

    monkeypatch.setattr(ncaa_scraper, "scrape", lambda: [_fake_game("ncaa")])

    data = scraper.scrape_all()

    assert data["source"] == "ncaa_fallback"
    assert data["degraded"] is True
