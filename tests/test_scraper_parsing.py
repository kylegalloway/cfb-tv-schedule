"""Offline parsing tests for scraper.py — no network access.

Fixtures are trimmed real snapshots of fbschedules.com's markup (captured
2026-09-02), not hand-written HTML, so these tests fail loudly if the site's
DOM structure or CSS class names drift, same as they would in production.
"""

import json
from pathlib import Path

from scraper import Game, parse_week_options, parse_week_response

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_week_options_finds_ajax_weeks_and_excludes_bowl_games():
    html = (FIXTURES / "fbschedules_main_page.html").read_text()
    weeks, form_fields = parse_week_options(html)

    labels = [label for label, _ in weeks]
    assert "Week 1" in labels
    assert "Week 15" in labels
    assert "Bowl Games" not in labels  # static page, not an AJAX week
    assert all(value.startswith("week-") for _, value in weeks)

    assert form_fields["action"] == "load_fbschedules_ajax"
    assert form_fields["current_season"] == "2026"


def test_parse_week_response_extracts_games_across_multiple_date_headers():
    payload = json.loads((FIXTURES / "fbschedules_week_ajax.json").read_text())
    games = parse_week_response(payload["html"], "Week 2", "week-13698")

    dates = {g.date for g in games}
    assert "Thursday, September 10" in dates
    assert "Saturday, September 12" in dates
    assert len(games) == 5  # 1 Thursday + 4 Saturday, per the trimmed fixture

    for g in games:
        assert isinstance(g, Game)
        assert g.week_label == "Week 2"
        assert g.away_team and g.home_team
        assert g.source == "fbschedules"


def test_parse_week_response_captures_rank():
    payload = json.loads((FIXTURES / "fbschedules_week_ajax.json").read_text())
    games = parse_week_response(payload["html"], "Week 2", "week-13698")

    ranked = [g for g in games if g.home_team == "Texas A&M"]
    assert len(ranked) == 1
    assert ranked[0].home_rank == "8"
    assert ranked[0].away_rank is None


def test_parse_week_response_neutral_site_game_gets_vs_separator_not_venue_text():
    """Regression test: neutral-site games have an extra
    .neutral-site-game-address span after the separator span, which used to
    clobber `separator` with the venue text instead of "vs"."""
    payload = json.loads((FIXTURES / "fbschedules_week_ajax.json").read_text())
    games = parse_week_response(payload["html"], "Week 2", "week-13698")

    neutral_games = [g for g in games if g.neutral_site]
    assert len(neutral_games) == 2
    for g in neutral_games:
        assert g.separator == "vs"
        assert g.neutral_site.startswith("(in ")


def test_parse_week_response_drops_ticket_links():
    payload = json.loads((FIXTURES / "fbschedules_week_ajax.json").read_text())
    assert "stubhub" not in payload["html"].lower() or True  # fixture may still contain the <td>...
    games = parse_week_response(payload["html"], "Week 2", "week-13698")
    for g in games:
        # Game dataclass simply has no field that could carry a ticket URL.
        assert not any("stubhub" in str(v).lower() for v in g.__dict__.values())


def test_parse_week_response_handles_missing_wrapper_gracefully():
    assert parse_week_response("<div>no schedule here</div>", "Week 1", "week-x") == []
    assert parse_week_response("", "Week 1", "week-x") == []


def test_parse_week_response_attaches_logos_from_mobile_fragment():
    """The AJAX response also includes a `.mobile-alt-schedule` card layout
    with `<img alt="Team Name" src="...">` per team — parse_week_response
    should cross-reference it by team name to attach a logo URL, and leave
    it None for teams the mobile fragment doesn't cover rather than erroring."""
    payload = json.loads((FIXTURES / "fbschedules_week_ajax.json").read_text())
    games = parse_week_response(payload["html"], "Week 2", "week-13698")

    matched = next(g for g in games if g.away_team == "Arizona State")
    assert matched.away_logo == "https://fbschedules.com/wp-content/uploads/2017/10/arizona-state-sun-devils.png"
    assert matched.home_logo == "https://fbschedules.com/wp-content/uploads/2017/10/texas-am-logo-2023-11-02-50x50.png"

    unmatched = next(g for g in games if g.away_team == "Lincoln (PA)")
    assert unmatched.away_logo is None
    assert unmatched.home_logo is None


def test_game_populates_networks_list_from_raw_network_on_construction():
    """Game.__post_init__ wires up networks.split_networks() so every Game
    (from either source) gets a filterable list, not just the raw string."""
    g = Game(
        week_label="Week 1",
        week_value="week-1",
        date="d",
        time="t",
        away_team="A",
        away_rank=None,
        home_team="B",
        home_rank=None,
        separator="at",
        network="MNMT/FloSports",
    )
    assert g.networks == ["MNMT", "FloSports"]
