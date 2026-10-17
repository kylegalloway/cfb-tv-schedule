"""Tests scores.py's per-league result lookup — no network access."""

from datetime import datetime, timezone

import pytest

import scores

NOW = datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self, by_date):
        self.by_date = by_date
        self.calls = []

    def results(self, date):
        self.calls.append(date)
        return self.by_date.get(date, [])


@pytest.fixture
def provider(tmp_path, monkeypatch):
    fake = FakeProvider({
        "2026-10-03": [{
            "away_team": "Bruins", "home_team": "Wild", "away_score": 1, "home_score": 4,
            "status": "Final", "start_utc": "2026-10-04T00:00:00Z",
        }],
        "2026-10-10": [{
            "away_team": "Canadiens", "home_team": "Wild", "away_score": 3, "home_score": 2,
            "status": "Final/SO", "start_utc": "2026-10-11T00:00:00Z",
        }],
    })
    monkeypatch.setattr(scores, "SCORES_DIR", tmp_path)
    monkeypatch.setattr(scores, "PROVIDERS", {"NHL": fake})
    return fake


def _game(away, home, start_utc, start_date, league="NHL", **extra):
    return {"league": league, "away_team": away, "home_team": home,
            "start_utc": start_utc, "start_date": start_date, **extra}


def test_fetches_and_applies_final_scores(provider):
    games = [
        _game("Boston Bruins", "Minnesota Wild", "2026-10-04T00:00:00+00:00", "2026-10-03"),
        _game("Montréal Canadiens", "Minnesota Wild", "2026-10-11T00:00:00+00:00", "2026-10-10"),
    ]

    scores.fetch_missing(games, now=NOW)
    scores.apply(games)

    assert (games[0]["away_score"], games[0]["home_score"], games[0]["status"]) == (1, 4, "Final")
    assert games[1]["status"] == "Final/SO"


def test_skips_games_not_over_yet_and_other_leagues(provider):
    upcoming = _game("San Jose Sharks", "Minnesota Wild", "2026-11-07T01:00:00+00:00", "2026-11-06")
    cfb = _game("Iowa", "Washington", "2026-10-10T01:00:00+00:00", "2026-10-09", league="CFB")

    scores.fetch_missing([upcoming, cfb], now=NOW)
    scores.apply([upcoming, cfb])

    assert provider.calls == []
    assert "status" not in upcoming and "status" not in cfb


def test_cached_results_are_not_looked_up_again(provider):
    game = _game("Boston Bruins", "Minnesota Wild", "2026-10-04T00:00:00+00:00", "2026-10-03")

    scores.fetch_missing([dict(game)], now=NOW)
    scores.fetch_missing([dict(game)], now=NOW)

    assert provider.calls == ["2026-10-03"]


def test_does_not_match_a_different_matchup_on_the_same_day(provider):
    game = _game("Boston Bruins", "Dallas Stars", "2026-10-04T00:00:00+00:00", "2026-10-03")

    scores.fetch_missing([game], now=NOW)
    scores.apply([game])

    assert "status" not in game


def test_failed_lookup_keeps_earlier_results(provider, monkeypatch):
    bruins = _game("Boston Bruins", "Minnesota Wild", "2026-10-04T00:00:00+00:00", "2026-10-03")
    scores.fetch_missing([dict(bruins)], now=NOW)

    def _boom(date):
        raise RuntimeError("api down")

    monkeypatch.setattr(provider, "results", _boom)
    habs = _game("Montréal Canadiens", "Minnesota Wild", "2026-10-11T00:00:00+00:00", "2026-10-10")
    scores.fetch_missing([dict(bruins), habs], now=NOW)
    scores.apply([bruins, habs])

    assert bruins["status"] == "Final"
    assert "status" not in habs


def test_source_supplied_result_is_kept(provider):
    game = _game("Boston Bruins", "Minnesota Wild", "2026-10-04T00:00:00+00:00", "2026-10-03",
                 status="Canceled", away_score=None, home_score=None)

    scores.fetch_missing([game], now=NOW)
    scores.apply([game])

    assert game["status"] == "Canceled"
    assert provider.calls == []
