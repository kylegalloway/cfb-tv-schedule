"""Flask app serving the CFB TV schedule dashboard.

- GET  /              -> static/index.html (dashboard UI)
- GET  /api/games      -> cached data/games.json contents
- POST /api/refresh    -> runs a fresh scrape synchronously, returns the result
- Background APScheduler job re-runs the scrape on a timer.
"""

from __future__ import annotations

import json
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify

import scraper

app = Flask(__name__, static_folder="static", static_url_path="")
scrape_lock = threading.Lock()

REFRESH_INTERVAL_HOURS = float(os.environ.get("REFRESH_INTERVAL_HOURS", "6"))
PORT = int(os.environ.get("PORT", "8100"))


def _load_cached() -> dict:
    if not scraper.DATA_PATH.exists():
        return {"scraped_at": None, "weeks": [], "games": [], "source": None, "degraded": False}
    return json.loads(scraper.DATA_PATH.read_text())


def _run_scrape() -> dict:
    with scrape_lock:
        return scraper.scrape_all()


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/games")
def get_games():
    return jsonify(_load_cached())


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
    if not scraper.DATA_PATH.exists():
        print("no cached data found, running initial scrape...")
        _run_scrape()

    start_scheduler()
    app.run(host="0.0.0.0", port=PORT, debug=False)
