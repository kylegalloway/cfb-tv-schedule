"""Tests stations.py's St. Paul OTA lineup — no network access."""

from stations import CHANNELS, LINEUP, local_network


def test_local_affiliates_translate_to_national_network():
    assert local_network("KSTP-TV 5") == "ABC"
    assert local_network("FOX9") == "FOX"
    assert local_network("kare 11") == "NBC"


def test_independent_keeps_its_own_brand():
    assert local_network("KSTC-TV 45") == "45TV"


def test_other_networks_and_markets_pass_through():
    assert local_network("ESPN") == "ESPN"
    assert local_network("ABC 7") == "ABC 7"


def test_channels_are_digital_virtual_channels():
    assert CHANNELS["ABC"] == "5.1"
    assert CHANNELS["45TV"] == "5.2"
    assert CHANNELS["FOX"] == "9.1"


def test_every_station_has_a_unique_channel_and_network():
    assert len({s.channel for s in LINEUP}) == len(LINEUP)
    assert len({s.network for s in LINEUP}) == len(LINEUP)
