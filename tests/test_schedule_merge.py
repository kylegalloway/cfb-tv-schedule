"""Tests schedule.py's multi-source merge — no network access."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import schedule
import scraper


@dataclass
class FakeSource:
    key: str
    data_path: Path
    games: list[dict] = field(default_factory=list)
    fail: bool = False

    def refresh(self):
        if self.fail:
            raise RuntimeError(f"{self.key} is down")
        data = {"scraped_at": "2026-10-07T12:00:00+00:00", "games": self.games, "source": self.key, "degraded": False}
        self.data_path.write_text(json.dumps(data))
        return data


def _cfb_game(**overrides):
    game = {
        "week_label": "Week 7", "date": "Saturday, October 10", "time": "11:00am",
        "away_team": "A", "home_team": "B", "separator": "at", "network": "FOX",
        "networks": ["FOX"], "order_index": 0,
    }
    game.update(overrides)
    return game


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA_PATH", tmp_path / "cfb_games.json")
    monkeypatch.setattr(schedule, "LEGACY_CFB_DATA_PATH", tmp_path / "games.json")


def test_merges_sources_and_serves_the_channel_lineup(tmp_path, monkeypatch):
    a = FakeSource("a", tmp_path / "a.json", [_cfb_game(league="CFB")])
    b = FakeSource("b", tmp_path / "b.json",
                   [{"league": "NHL", "start_utc": "2026-10-04T00:00:00+00:00", "away_team": "X", "home_team": "Y"}])
    monkeypatch.setattr(schedule, "SOURCES", [a, b])

    data = schedule.refresh_all()

    assert set(data["sources"]) == {"a", "b"}
    assert [g["league"] for g in data["games"]] == ["CFB", "NHL"]
    assert data["channels"]["ABC"] == "5.1"


def test_local_affiliate_networks_merge_into_their_national_network():
    game = schedule._normalize_game(_cfb_game(networks=["ABC", "KSTP-TV 5", "ESPN"]), None)
    wild = schedule._normalize_game(_cfb_game(networks=["KSTC-TV 45"]), None)

    assert game["networks"] == ["ABC", "ESPN"]
    assert wild["networks"] == ["45TV"]


def test_one_failing_source_keeps_its_cache_and_does_not_block_others(tmp_path, monkeypatch):
    ok = FakeSource("ok", tmp_path / "ok.json", games=[_cfb_game()])
    broken = FakeSource("broken", tmp_path / "broken.json", fail=True)
    broken.data_path.write_text(json.dumps({"scraped_at": "2026-10-01T00:00:00+00:00", "games": [_cfb_game(home_team="Cached")]}))
    monkeypatch.setattr(schedule, "SOURCES", [ok, broken])

    data = schedule.refresh_all()

    assert {g["home_team"] for g in data["games"]} == {"B", "Cached"}


def test_normalizes_cfb_wall_clock_to_start_utc():
    game = schedule._normalize_game(_cfb_game(), "2026-10-07T12:00:00+00:00")

    assert game["league"] == "CFB"
    assert game["start_date"] == "2026-10-10"
    assert game["start_utc"] == "2026-10-10T15:00:00+00:00"  # 11am EDT


def test_start_date_follows_the_games_own_time_zone_even_when_serialized_as_null():
    # 10pm Pacific on Oct 3 is already Oct 4 in Eastern.
    game = schedule._normalize_game(
        {"start_utc": "2026-10-04T05:00:00+00:00", "start_date": None, "league": None,
         "time_zone": "America/Los_Angeles"},
        None,
    )

    assert game["start_date"] == "2026-10-03"
    assert game["league"] == "CFB"


def test_normalizes_tbd_time_to_date_only():
    game = schedule._normalize_game(_cfb_game(time="TBD"), "2026-10-07T12:00:00+00:00")

    assert game["start_date"] == "2026-10-10"
    assert "start_utc" not in game


def test_january_game_scraped_in_august_rolls_into_next_year():
    game = schedule._normalize_game(_cfb_game(date="Monday, January 18", time="7:30pm"), "2026-08-20T12:00:00+00:00")

    assert game["start_date"] == "2027-01-18"


def test_migrates_legacy_games_json_into_cfb_cache(tmp_path, monkeypatch):
    schedule.LEGACY_CFB_DATA_PATH.write_text(json.dumps({"scraped_at": None, "games": [_cfb_game()], "degraded": True}))
    monkeypatch.setattr(schedule, "SOURCES", [schedule.ModuleSource("cfb", scraper)])

    data = schedule.load_all()

    assert not schedule.LEGACY_CFB_DATA_PATH.exists()
    assert scraper.DATA_PATH.exists()
    assert len(data["games"]) == 1
    assert data["degraded"] is True
