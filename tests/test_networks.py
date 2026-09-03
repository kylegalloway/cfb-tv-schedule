from networks import UNKNOWN_NETWORK, split_networks


def test_splits_slash_separated_networks():
    assert split_networks("MNMT/FloSports") == ["MNMT", "FloSports"]
    assert split_networks("ESPN/Disney+") == ["ESPN", "Disney+"]


def test_splits_or_separated_networks():
    assert split_networks("ABC or ESPN") == ["ABC", "ESPN"]
    assert split_networks("ESPN2 or ESPNU") == ["ESPN2", "ESPNU"]


def test_single_network_passthrough():
    assert split_networks("ESPN") == ["ESPN"]


def test_empty_or_blank_falls_back_to_unknown():
    assert split_networks("") == [UNKNOWN_NETWORK]
    assert split_networks("   ") == [UNKNOWN_NETWORK]


def test_date_leftover_fragment_is_filtered_to_unknown():
    """Real fbschedules.com data occasionally has a td whose entire content
    is a stray date fragment instead of a network name, e.g. a game whose
    raw network cell is literally "or Fri., Nov. 27" — not a real channel."""
    assert split_networks("or Fri., Nov. 27") == [UNKNOWN_NETWORK]


def test_espn_family_shorthand_is_expanded_not_left_as_bare_digit_or_letter():
    """Real fbschedules.com data: "ESPN/2/U TBA" and "ESPN2/U/CBSSN" are the
    site's shorthand for "could air on ESPN, ESPN2, or ESPNU" — naively
    splitting on "/" leaves a bare "2" and "U" token, which aren't network
    names on their own and shouldn't show up as filter options."""
    assert split_networks("ESPN/2/U TBA") == ["ESPN", "ESPN2", "ESPNU"]
    assert split_networks("ESPN2/U/CBSSN") == ["ESPN2", "ESPNU", "CBSSN"]


def test_placeholder_text_is_kept_not_treated_as_junk():
    """"TV TBA" / "Flex Game" are legitimate placeholders (the network
    genuinely isn't announced yet) — distinct from a stray date fragment —
    so they should remain filterable, not get collapsed to UNKNOWN_NETWORK."""
    assert split_networks("TV TBA") == ["TV TBA"]
    assert split_networks("Flex Game") == ["Flex Game"]
