"""stealth-fetcher run-script (see ../stealth-fetcher/README.md) that
downloads team logo images through a browser session that's already passed
fbschedules.com's Cloudflare challenge — plain HTTP `<img>` requests get 403'd
for these the same way the schedule page itself does (fbschedules.com blocks
hotlinked/non-browser image requests, not just the scrape). See scraper.py's
_localize_logos(), which builds the manifest and calls this via stealth-fetcher.

Run via:

    uv run stealth-fetcher run fetch_logos.py -- -i manifest.json -o data/logos

`manifest.json` is `{slug: logo_url}`. Writes one file per entry,
`<slug><ext>` (extension inferred from the URL), skipping any that already
exist on disk.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

# get_binary() runs fetch() *in the current page* so the request carries
# whatever session/cookies that page picked up passing Cloudflare's
# challenge — but a fresh BrowserSession starts on a blank page with no
# such session. Load fbschedules.com itself first (same as
# fetch_fbschedules.py does) purely to pass the challenge and pick up
# cf_clearance; we don't need anything from this particular page's content.
SCHEDULE_URL = "https://fbschedules.com/college-football-tv-schedule/"


def run(session, argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--manifest", required=True)
    parser.add_argument("-o", "--output-dir", required=True)
    args = parser.parse_args(argv)

    manifest: dict[str, str] = json.loads(Path(args.manifest).read_text())
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session.goto(SCHEDULE_URL, wait_selector="select[name='select-week-menu']")

    for slug, url in manifest.items():
        ext = Path(urlparse(url).path).suffix or ".png"
        dest = out_dir / f"{slug}{ext}"
        if dest.exists():
            continue
        try:
            dest.write_bytes(session.get_binary(url))
        except Exception as exc:  # noqa: BLE001 — keep fetching the rest
            print(f"warning: failed to fetch logo for {slug} ({url}): {exc}")
