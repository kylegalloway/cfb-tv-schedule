"""Live network canary tests — verify the real sites still look the way our
parsers expect. Excluded from the default test run (see pyproject.toml's
`addopts = "-m 'not live'"`); run explicitly with:

    uv run pytest -m live

These are the tests that would have caught fbschedules.com changing its
week-selector markup, its AJAX endpoint contract, or NCAA.com restructuring
its preview article — none of which the offline fixture tests can detect,
since fixtures are frozen snapshots.
"""

import pytest

import ncaa_scraper
import scraper


@pytest.mark.live
def test_fbschedules_week_selector_still_has_all_weeks():
    session = scraper._session()
    weeks, form_fields = scraper.fetch_week_options(session)

    assert len(weeks) >= 15, "expected at least 15 regular-season weeks"
    assert all(value.startswith("week-") for _, value in weeks)
    assert form_fields["action"] == "load_fbschedules_ajax"


@pytest.mark.live
def test_fbschedules_ajax_endpoint_still_returns_parseable_games():
    session = scraper._session()
    weeks, form_fields = scraper.fetch_week_options(session)
    label, value = weeks[1]  # Week 1 — always has a full slate

    games = scraper.fetch_week(session, label, value, form_fields)

    assert len(games) > 50, "expected a full week's worth of FBS+FCS games"
    assert all(g.away_team and g.home_team and g.network for g in games)


@pytest.mark.live
def test_ncaa_fallback_page_still_parses_games():
    games = ncaa_scraper.scrape()

    assert len(games) > 0, "ncaa.com fallback source returned no games — markup may have changed"
    assert all(g.away_team and g.home_team for g in games)


@pytest.mark.live
def test_scrape_all_end_to_end_uses_primary_source_not_fallback():
    """If this ever falls back to source == 'ncaa_fallback', fbschedules.com
    parsing is broken in production, not just in this test."""
    data = scraper.scrape_all()

    assert data["source"] == "fbschedules"
    assert data["degraded"] is False
    assert len(data["games"]) > 500
