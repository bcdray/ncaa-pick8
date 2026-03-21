import logging
import os
import time

from flask import Flask, jsonify, render_template

from espn import fetch_tournament_teams
from scoring import build_scenarios, calculate_prizes, score_picks
from sheets import load_picks

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SHEET_ID = os.environ.get("NCAA_SHEET_ID", "")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "300"))  # 5 minutes

_cache = {"data": None, "ts": 0}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/board")
def board():
    now = time.time()
    age = now - _cache["ts"]

    if _cache["data"] is not None and age < CACHE_TTL:
        logging.info("Serving cached response (age: %.0fs)", age)
        return _cache["data"]

    logging.info("Cache miss — fetching fresh data")
    picks = load_picks(SHEET_ID)
    teams = fetch_tournament_teams()
    scored = score_picks(picks, teams)
    prize_info = calculate_prizes(len(picks))
    scenarios = build_scenarios(scored)

    result = jsonify({
        "players": scored,
        "scenarios": scenarios,
        "prizes": prize_info["prizes"],
        "total_pot": prize_info["total_pot"],
        "num_entries": len(picks),
        "cache_age": 0,
    })

    _cache["data"] = result
    _cache["ts"] = now
    return result


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
