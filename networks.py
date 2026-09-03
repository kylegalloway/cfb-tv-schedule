"""Splits a raw "network" cell (e.g. "ESPN/Disney+", "ABC or ESPN") into
individual channel names for filtering, and drops fragments that aren't
actually networks.

fbschedules.com's network column is free text and not always clean — some
rows contain leftover scheduling notes instead of (or in addition to) a
channel name, e.g. a `td` whose full content is literally "or Fri., Nov. 27"
(an artifact of the site's own template, present in their raw HTML — not
something our scraper introduced). Those fragments look like a stray half
of an " or " list, which is exactly the delimiter used for real multi-network
listings like "ABC or ESPN", so splitting on it is what exposes the junk;
this module also filters it back out.
"""

from __future__ import annotations

import re

_SPLIT_RE = re.compile(r"\s*/\s*|\s+or\s+", re.IGNORECASE)

# A bare weekday + month + day (e.g. "Fri., Nov. 27") is a leftover date
# fragment, never a real network name.
_DATE_FRAGMENT_RE = re.compile(
    r"^(mon|tue|wed|thu|fri|sat|sun)\.?,?\s+"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\.?\s+\d{1,2}$",
    re.IGNORECASE,
)

# fbschedules.com occasionally shorthands the ESPN family as "ESPN/2/U" or
# "ESPN2/U" instead of spelling out "ESPN/ESPN2/ESPNU" — naively splitting
# on "/" then leaves bare "2" / "U" tokens that aren't network names on
# their own. Expand the shorthand to full channel names (and drop a
# trailing "TBA" here, since "which of these three airs it" is exactly what
# TBA meant) before the general split below runs.
_ESPN_SHORTHAND_RES = [
    (re.compile(r"\bESPN/2/U\b(\s+TBA\b)?", re.IGNORECASE), "ESPN/ESPN2/ESPNU"),
    (re.compile(r"\bESPN2/U\b", re.IGNORECASE), "ESPN2/ESPNU"),
]

UNKNOWN_NETWORK = "Network TBD"


def split_networks(raw: str) -> list[str]:
    """Returns the individual network names in `raw`, e.g.
    "MNMT/FloSports" -> ["MNMT", "FloSports"]. Falls back to
    [UNKNOWN_NETWORK] if nothing usable survives (e.g. `raw` is empty or is
    entirely a date-leftover fragment), so every game still has at least one
    filterable value rather than silently vanishing from every filter.
    """
    if not raw or not raw.strip():
        return [UNKNOWN_NETWORK]

    # A leading "or " (no network before it, e.g. a truncated "TV TBA or
    # Fri., Nov. 27" note) isn't a real separator between two networks —
    # strip it so the remainder can still be checked against the
    # date-fragment filter below instead of surviving as one odd token.
    raw = re.sub(r"^or\s+", "", raw.strip(), flags=re.IGNORECASE)

    for pattern, replacement in _ESPN_SHORTHAND_RES:
        raw = pattern.sub(replacement, raw)

    tokens = []
    for part in _SPLIT_RE.split(raw):
        part = part.strip()
        if not part:
            continue
        if _DATE_FRAGMENT_RE.match(part):
            continue
        tokens.append(part)

    return tokens or [UNKNOWN_NETWORK]
