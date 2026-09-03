"""Offline parsing tests for ncaa_scraper.py — no network access.

Fixture is a trimmed real snapshot (captured 2026-09-02) of the NCAA.com TV
schedule preview article used as a fallback data source.
"""

from pathlib import Path

from ncaa_scraper import parse_schedule

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_schedule_extracts_games_with_correct_source_and_date():
    html = (FIXTURES / "ncaa_preview_article.html").read_text()
    games = parse_schedule(html)

    assert len(games) > 0
    assert all(g.source == "ncaa" for g in games)
    assert any(g.date == "Thursday, Sept. 3" for g in games)


def test_parse_schedule_extracts_rank():
    html = (FIXTURES / "ncaa_preview_article.html").read_text()
    games = parse_schedule(html)

    ranked = [g for g in games if g.home_team == "Missouri"]
    assert len(ranked) == 1
    assert ranked[0].home_rank == "25"
    assert ranked[0].away_team == "Arkansas-Pine Bluff"


def test_parse_schedule_neutral_site_vs_game():
    html = (FIXTURES / "ncaa_preview_article.html").read_text()
    games = parse_schedule(html)

    neutral = [g for g in games if g.home_team == "South Carolina State"]
    assert len(neutral) == 1
    assert neutral[0].separator == "vs"
    assert neutral[0].away_team == "Florida A&M"


def test_parse_schedule_ignores_non_schedule_links():
    """The article also links to unrelated recap/result pages under
    /game/<id> for past games — these have no ' | time | network' format and
    must not be mistaken for schedule entries."""
    html = """
    <html><body><div class="article-body node__content">
    <p><strong>Thursday, Sept. 3</strong></p>
    <p>
      <a href="https://www.ncaa.com/game/123">UMass at Rutgers | 6 p.m. | Big Ten Network</a><br>
      <a href="https://www.ncaa.com/game/456">Some Team 42, Other Team 10</a>
    </p>
    </div></body></html>
    """
    games = parse_schedule(html)
    assert len(games) == 1
    assert games[0].away_team == "UMass"


def test_parse_schedule_empty_body_returns_empty_list():
    assert parse_schedule("<html><body>nothing here</body></html>") == []
