import logging
import os
import time

from flask import Flask, jsonify, render_template

from espn import fetch_tournament_teams
from scoring import build_scenarios, calculate_prizes, score_picks
from sheets import load_picks
from simulation import run_monte_carlo

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SHEET_ID = os.environ.get("NCAA_SHEET_ID", "")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "300"))  # 5 minutes

_cache = {"data": None, "ts": 0}
_raw_cache = {"picks": None, "teams": None, "ts": 0}
_sim_cache = {"data": None, "ts": 0}
SIM_CACHE_TTL = 3600  # 1 hour


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
    _raw_cache["picks"] = picks
    _raw_cache["teams"] = teams
    _raw_cache["ts"] = now
    return result


@app.route("/api/simulate")
def simulate():
    now = time.time()

    if _sim_cache["data"] is not None and now - _sim_cache["ts"] < SIM_CACHE_TTL:
        logging.info("Serving cached simulation")
        return _sim_cache["data"]

    # Reuse raw data from board cache if available and fresh
    if _raw_cache["picks"] is not None and now - _raw_cache["ts"] < CACHE_TTL:
        picks = _raw_cache["picks"]
        teams = _raw_cache["teams"]
    else:
        picks = load_picks(SHEET_ID)
        teams = fetch_tournament_teams()

    try:
        results = run_monte_carlo(picks, teams)
    except Exception as e:
        logging.error("Simulation error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500

    response = jsonify({"players": results, "simulations": 10_000})
    _sim_cache["data"] = response
    _sim_cache["ts"] = now
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
