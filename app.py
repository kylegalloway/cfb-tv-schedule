"""Flask app serving the OTA sports TV schedule dashboard.

- GET  /              -> static/index.html (dashboard UI)
- GET  /api/games      -> every source's cached games, merged (schedule.py)
- POST /api/refresh    -> re-scrapes every source synchronously, returns the merge
- Background APScheduler job re-runs the scrape on a timer.
"""

from __future__ import annotations

import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, send_from_directory

import schedule
import scraper

app = Flask(__name__, static_folder="static", static_url_path="")
scrape_lock = threading.Lock()

REFRESH_INTERVAL_HOURS = float(os.environ.get("REFRESH_INTERVAL_HOURS", "72"))
PORT = int(os.environ.get("PORT", "8100"))


def _run_scrape() -> dict:
    with scrape_lock:
        return schedule.refresh_all()


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/games")
def get_games():
    return jsonify(schedule.load_all())


@app.get("/logos/<path:filename>")
def get_logo(filename):
    # Locally cached team logos — scraper.py's _localize_logos() points
    # games at these instead of fbschedules.com's URLs directly, since
    # Cloudflare 403s hotlinked image requests the same as scraping.
    return send_from_directory(scraper.LOGO_IMAGE_DIR, filename)


@app.post("/api/refresh")
def refresh():
    data = _run_scrape()
    return jsonify(data)


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_scrape, "interval", hours=REFRESH_INTERVAL_HOURS, id="scrape_job")
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    if not schedule.has_cached_data():
        print("no cached data found, running initial scrape...")
        _run_scrape()

    start_scheduler()
    app.run(host="0.0.0.0", port=PORT, debug=False)
