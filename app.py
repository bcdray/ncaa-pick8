import logging
import os

from flask import Flask, jsonify, render_template

from espn import fetch_tournament_teams
from scoring import build_scenarios, calculate_prizes, score_picks
from sheets import load_picks

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SHEET_ID = os.environ.get("NCAA_SHEET_ID", "")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/board")
def board():
    picks = load_picks(SHEET_ID)
    teams = fetch_tournament_teams()
    scored = score_picks(picks, teams)
    prize_info = calculate_prizes(len(picks))

    scenarios = build_scenarios(scored)

    return jsonify({
        "players": scored,
        "scenarios": scenarios,
        "prizes": prize_info["prizes"],
        "total_pot": prize_info["total_pot"],
        "num_entries": len(picks),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
