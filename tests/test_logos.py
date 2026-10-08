"""Tests logos.py's per-league logo lookup — no network access."""

import pytest

import logos


class FakeProvider:
    def __init__(self, urls):
        self.urls = urls
        self.calls = 0

    def logo_urls(self):
        self.calls += 1
        return self.urls


@pytest.fixture
def provider(tmp_path, monkeypatch):
    fake = FakeProvider({
        "Minnesota Wild": "https://example.test/MIN_light.svg",
        "Montréal Canadiens": "https://example.test/MTL_light.svg",
    })
    monkeypatch.setattr(logos, "LOGO_IMAGE_DIR", tmp_path)
    monkeypatch.setattr(logos, "PROVIDERS", {"NHL": fake})
    monkeypatch.setattr(logos, "_download", lambda url: f"<svg>{url}</svg>".encode())
    return fake


def _game(away, home, league="NHL", **extra):
    return {"league": league, "away_team": away, "home_team": home, **extra}


def test_downloads_and_applies_logos_per_league(tmp_path, provider):
    games = [_game("Montreal Canadiens", "Minnesota Wild")]

    logos.fetch_missing(games)
    logos.apply(games)

    assert (tmp_path / "nhl" / "minnesota-wild.svg").exists()
    assert games[0]["home_logo"] == "/logos/nhl/minnesota-wild.svg"
    # Matched despite the missing accent.
    assert games[0]["away_logo"] == "/logos/nhl/montreal-canadiens.svg"


def test_logos_already_on_disk_skip_the_provider(provider):
    logos.fetch_missing([_game("Minnesota Wild", "Montréal Canadiens")])
    logos.fetch_missing([_game("Minnesota Wild", "Montréal Canadiens")])

    assert provider.calls == 1


def test_unknown_team_and_leagues_without_a_provider_are_left_alone(tmp_path, provider):
    nhl = _game("Minnesota Wild", "Nowhere Nobodies")
    cfb = _game("Minnesota", "Iowa", league="CFB", away_logo="/logos/minnesota.png")

    logos.fetch_missing([nhl, cfb])
    logos.apply([nhl, cfb])

    assert "home_logo" not in nhl
    assert cfb["away_logo"] == "/logos/minnesota.png"
    assert "home_logo" not in cfb
    assert not (tmp_path / "cfb").exists()


def test_a_failing_provider_does_not_raise(provider):
    def boom():
        raise RuntimeError("NHL API down")

    provider.logo_urls = boom
    logos.fetch_missing([_game("Minnesota Wild", "Dallas Stars")])
