"""The local over-the-air (OTA) station lineup for the viewer's market —
Minneapolis–St. Paul.

Sources name channels however they like: fbschedules.com says "ABC" (the
national network), while KSTP's own articles say "KSTP-TV 5" (the local
affiliate). `local_network()` translates a local affiliate's name to its
national network's, so both land on one "ABC" filter/guide row, and
CHANNELS gives each OTA network its digital virtual channel ("5.1") for
labels and channel-order sorting.

Virtual channels, not the old analog numbers: KSTC still brands itself
"45TV", but has broadcast as KSTP's 5.2 subchannel since 2011. Checked
against Channel Master's antenna list for St. Paul (55125):
https://www.channelmaster.com/pages/free-tv-channels-saint-paul-mn-55125
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Station:
    channel: str  # digital virtual channel, e.g. "5.1"
    call_sign: str
    # National network name as sources write it ("ABC"), or the station's
    # own brand for an independent ("45TV").
    network: str
    # Other names sources use for this station.
    aliases: frozenset[str] = frozenset()


LINEUP = [
    Station("2.1", "KTCA", "PBS", frozenset({"TPT"})),
    Station("4.1", "WCCO", "CBS", frozenset({"WCCO-TV", "WCCO-TV 4"})),
    Station("5.1", "KSTP", "ABC", frozenset({"KSTP-TV", "KSTP-TV 5"})),
    Station("5.2", "KSTC", "45TV", frozenset({"KSTC-TV", "KSTC-TV 45"})),
    # KMSP moved to ATSC 3.0; its sister WFTC carries FOX on 9.1 for
    # ATSC 1.0 tuners, and MyNetworkTV on 9.10.
    Station("9.1", "KMSP", "FOX", frozenset({"KMSP-TV", "FOX9", "FOX 9"})),
    Station("9.10", "WFTC", "MyNetworkTV", frozenset({"WFTC-TV", "MyNetworkTV 29"})),
    Station("11.1", "KARE", "NBC", frozenset({"KARE 11"})),
    Station("23.1", "WUCW", "The CW", frozenset({"CW Twin Cities"})),
    Station("41.1", "KPXM", "ION", frozenset({"KPXM-TV"})),
]

CHANNELS = {s.network: s.channel for s in LINEUP}

_BY_NAME = {name.lower(): s.network for s in LINEUP for name in s.aliases | {s.call_sign}}


def local_network(name: str) -> str:
    """Returns the national network name for a local affiliate's name
    ("KSTP-TV 5" -> "ABC"), or `name` unchanged if it isn't one of this
    market's stations. Other markets' affiliates ("ABC 7", "WDAY") don't
    air here and stay as-is."""
    return _BY_NAME.get(name.strip().lower(), name)
