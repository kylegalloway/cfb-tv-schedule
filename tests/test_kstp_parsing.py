"""Offline parsing tests for kstp_scraper.py — no network access.

Fixture is a trimmed real snapshot (captured 2026-10-07) of KSTP's
"KSTP, 45TV to broadcast 10 Minnesota Wild games this season" article.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kstp_scraper import parse_article, parse_season

FIXTURES = Path(__file__).parent / "fixtures"
CENTRAL = ZoneInfo("America/Chicago")


@pytest.fixture
def games():
    html = (FIXTURES / "kstp_wild_article.html").read_text()
    return parse_article(html, team="Minnesota Wild", league="NHL", zone=CENTRAL)


def test_parses_all_ten_games_and_ignores_unrelated_list_items(games):
    assert len(games) == 10
    assert all(g.league == "NHL" and g.source == "kstp" for g in games)
    assert {g.network for g in games} == {"KSTC-TV 45", "KSTP-TV 5"}


def test_home_game_puts_wild_at_home(games):
    opener = games[0]
    assert (opener.away_team, opener.home_team) == ("Boston Bruins", "Minnesota Wild")
    assert opener.date == "Saturday, October 3"
    assert opener.time == "7:00pm"
    assert opener.networks == ["KSTC-TV 45"]


def test_road_game_with_dotted_opponent_name_puts_wild_away(games):
    blues = next(g for g in games if "Blues" in g.home_team)
    assert (blues.away_team, blues.home_team) == ("Minnesota Wild", "St. Louis Blues")
    assert blues.time == "6:00pm"


def test_start_utc_is_central_time_and_rolls_into_second_season_year(games):
    opener = datetime.fromisoformat(games[0].start_utc).astimezone(CENTRAL)
    assert (opener.year, opener.month, opener.day, opener.hour) == (2026, 10, 3, 19)

    # "Wednesday, March 3" uses the full month name and is in 2027.
    march = datetime.fromisoformat(games[8].start_utc).astimezone(CENTRAL)
    assert (march.year, march.month, march.day, march.hour) == (2027, 3, 3, 19)
    assert march.strftime("%A") == "Wednesday"


def test_parse_season_handles_single_and_split_years():
    assert parse_season("the 2026-27 season") == (2026, True)
    assert parse_season("for the 2027 season") == (2027, False)
    with pytest.raises(RuntimeError):
        parse_season("no season phrase here")
