"""Defines *what* to fetch from fbschedules.com when it's behind Cloudflare's
JS challenge and scraper.py's plain `requests.Session()` can't get past it
(see scraper.py's module docstring and scrape_all()'s fallback logic).

This is a `stealth-fetcher` run-script (see ../stealth-fetcher/README.md):
stealth-fetcher owns the browser engine that can pass the challenge, this
file owns the site-specific knowledge of which URLs to hit and how. Run via:

    cd ../stealth-fetcher
    uv run stealth-fetcher run ../cfb-tv-schedule/fetch_fbschedules.py \
        -- -o ../cfb-tv-schedule/data/manual

Writes one `week<N>.php` file per week, each holding the raw
`{"html": "..."}` JSON the AJAX endpoint returns — the format
scraper.scrape_all_from_manual() reads from data/manual/. After running this,
pick the season up with:

    uv run python3 scraper.py manual
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

# Mirrors scraper.py's SCHEDULE_URL / AJAX_URL / BASE_FORM_FIELDS — keep in
# sync if fbschedules.com's markup or AJAX contract changes.
SCHEDULE_URL = "https://fbschedules.com/college-football-tv-schedule/"
AJAX_URL = "https://fbschedules.com/wp-admin/admin-ajax.php"
BASE_FORM_FIELDS = {
    "action": "load_fbschedules_ajax",
    "type": "NCAA",
    "display": "current",
    "team": "",
    "view": "weekly",
    "conference": "",
    "conference-division": "",
    "ncaa-subdivision": "",
    "ispreseason": "",
    "current-page-type": "",
    "is_spring_week_only": "",
}


def _parse_week_options(html: str) -> tuple[list[tuple[str, str]], dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")

    select = soup.select_one("select[name='select-week-menu']")
    if select is None:
        raise RuntimeError("could not find week selector on schedule page — site markup may have changed")

    weeks = []
    for option in select.find_all("option"):
        value = option.get("value", "")
        label = option.get_text(strip=True)
        if value.startswith("week-"):
            weeks.append((label, value))

    form = soup.select_one("form[name='fbschedule-frm']")
    form_fields = dict(BASE_FORM_FIELDS)
    if form is not None:
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name and name not in ("action",):
                form_fields[name] = inp.get("value", "")

    return weeks, form_fields


def _week_number(label: str, fallback_index: int) -> int:
    m = re.search(r"\d+", label)
    return int(m.group()) if m else fallback_index


def run(session, argv: list[str]) -> None:
    """Entry point stealth-fetcher's `run` command calls: `session` is a
    BrowserSession (see ../stealth-fetcher/stealth_fetcher/engines.py) that
    has already passed fbschedules.com's Cloudflare challenge."""
    parser = argparse.ArgumentParser(prog="fetch_fbschedules.py")
    parser.add_argument("-o", "--output-dir", default="data/manual")
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    main_html = session.goto(SCHEDULE_URL, wait_selector="select[name='select-week-menu']")
    weeks, form_fields = _parse_week_options(main_html)
    if not weeks:
        raise RuntimeError("fbschedules.com returned no week options")

    written = []
    for i, (label, value) in enumerate(weeks):
        params = dict(form_fields)
        params["schedule-week"] = value
        params["is_playoff"] = "false"

        body = session.get(AJAX_URL, params=params)
        json.loads(body)  # fail fast if the response isn't the JSON payload we expect

        n = _week_number(label, i)
        out_path = out_dir / f"week{n}.php"
        out_path.write_text(body)
        written.append(out_path)
        print(f"  {label} ({value}) -> {out_path.name}")

    print(f"wrote {len(written)} week files to {out_dir}")
