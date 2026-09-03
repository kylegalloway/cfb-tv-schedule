"""Cross-checks the two independent data sources against each other.

fbschedules.com (primary) and NCAA.com (fallback) are unrelated sites that
each publish the same real-world game info in their own conventions — this
is a *different signal* from the per-source parsing tests: it catches cases
where a source's parser still runs without error but silently produces
wrong values (e.g. the wrong day, or the wrong kickoff time), which a
same-source fixture test can't detect on its own.

Team names and network names use different abbreviation conventions between
the two sites, so this only checks games where both sides use the same
team-name spelling (season-opener "UMass at Rutgers", present in both
fixtures), and normalizes time/network format before comparing.
"""

import json
import re
from pathlib import Path

from ncaa_scraper import parse_schedule
from scraper import parse_week_response

FIXTURES = Path(__file__).parent / "fixtures"

# fbschedules abbreviation -> ncaa.com full name, for the networks that show
# up in the known-overlapping fixture games. Not meant to be exhaustive.
NETWORK_ALIASES = {
    "BTN": "Big Ten Network",
}


def _time_to_minutes(text: str) -> int:
    m = re.search(r"(\d{1,2}):?(\d{2})?\s*(a\.?m\.?|p\.?m\.?)", text, re.IGNORECASE)
    assert m, f"unparseable time: {text!r}"
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3).lower().startswith("p"):
        hour += 12
    return hour * 60 + minute


def test_umass_at_rutgers_agrees_across_both_sources():
    fb_payload = json.loads((FIXTURES / "fbschedules_week1_ajax.json").read_text())
    fb_games = parse_week_response(fb_payload["html"], "Week 1", "week-13697")
    ncaa_games = parse_schedule((FIXTURES / "ncaa_preview_article.html").read_text())

    fb_game = next(g for g in fb_games if g.away_team == "UMass" and g.home_team == "Rutgers")
    ncaa_game = next(g for g in ncaa_games if g.away_team == "UMass" and g.home_team == "Rutgers")

    assert _time_to_minutes(fb_game.time) == _time_to_minutes(ncaa_game.time)

    fb_network = NETWORK_ALIASES.get(fb_game.network, fb_game.network)
    assert fb_network == ncaa_game.network
