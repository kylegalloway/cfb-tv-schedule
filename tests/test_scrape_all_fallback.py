"""Tests scraper.scrape_all()'s fallback wiring — no network access.

Both _scrape_fbschedules and ncaa_scraper.scrape are monkeypatched so this
only exercises the fallback decision logic (and the resulting data["source"]
/ data["degraded"] flags), not either site's actual parsing.
"""

import json

import scraper
from scraper import Game


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


def test_scrape_all_falls_back_to_ncaa_when_fbschedules_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA_PATH", tmp_path / "games.json")

    def _boom():
        raise RuntimeError("fbschedules.com is down")

    monkeypatch.setattr(scraper, "_scrape_fbschedules", _boom)

    import ncaa_scraper

    monkeypatch.setattr(ncaa_scraper, "scrape", lambda: [_fake_game("ncaa")])

    data = scraper.scrape_all()

    assert data["source"] == "ncaa_fallback"
    assert data["degraded"] is True
    assert len(data["games"]) == 1
    assert data["games"][0]["source"] == "ncaa"


def test_scrape_all_falls_back_when_fbschedules_returns_zero_games(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA_PATH", tmp_path / "games.json")
    monkeypatch.setattr(scraper, "fetch_week_options", lambda session: ([("Week 1", "week-1")], {}))
    monkeypatch.setattr(scraper, "fetch_week", lambda *a, **k: [])

    import ncaa_scraper

    monkeypatch.setattr(ncaa_scraper, "scrape", lambda: [_fake_game("ncaa")])

    data = scraper.scrape_all()

    assert data["source"] == "ncaa_fallback"
    assert data["degraded"] is True
