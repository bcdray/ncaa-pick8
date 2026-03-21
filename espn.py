import logging
import requests
from datetime import datetime, timedelta

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"


def _parse_round(event):
    """Extract round name from competition-level notes."""
    competition = event.get("competitions", [{}])[0]
    notes = competition.get("notes", []) or event.get("notes", [])

    for note in notes:
        headline = note.get("headline", "").lower()
        if "first four" in headline:
            return "First Four"
        if "1st round" in headline or "first round" in headline or "round of 64" in headline:
            return "Round of 64"
        if "2nd round" in headline or "second round" in headline or "round of 32" in headline:
            return "Round of 32"
        if "sweet" in headline:
            return "Sweet 16"
        if "elite" in headline:
            return "Elite 8"
        if "final four" in headline or "semifinal" in headline:
            return "Final Four"
        if "championship" in headline:
            return "Championship"

    return "Tournament"


def fetch_tournament_teams(year=None):
    """Fetch all NCAA tournament teams with seeds and win counts.

    Returns dict: espn_name -> {seed, wins, eliminated, current_round}
    First Four wins are excluded from win counts per pool rules.
    """
    if year is None:
        year = datetime.now().year

    start = datetime(year, 3, 17)
    end = datetime(year, 4, 8)

    all_events = {}
    current = start

    while current <= end:
        date_str = current.strftime("%Y%m%d")
        try:
            resp = requests.get(ESPN_URL, params={
                "dates": date_str,
                "groups": "100",
                "limit": "100",
            }, timeout=10)
            resp.raise_for_status()
            for event in resp.json().get("events", []):
                event_id = event.get("id", "")
                if event_id and event_id not in all_events:
                    all_events[event_id] = event
        except requests.RequestException as e:
            logging.warning("ESPN fetch error for %s: %s", date_str, e)

        current += timedelta(days=1)

    teams = {}

    for event in all_events.values():
        competition = event.get("competitions", [{}])[0]
        round_name = _parse_round(event)
        state = competition.get("status", {}).get("type", {}).get("state", "pre")

        for comp in competition.get("competitors", []):
            team_data = comp.get("team", {})
            name = team_data.get("shortDisplayName", team_data.get("displayName", ""))
            if not name:
                continue

            try:
                seed = int(comp.get("curatedRank", {}).get("current", comp.get("seed", 99)))
            except (ValueError, TypeError):
                seed = 99

            if name not in teams:
                teams[name] = {
                    "seed": seed,
                    "wins": 0,
                    "eliminated": False,
                    "current_round": round_name,
                }
            else:
                if seed < teams[name]["seed"]:
                    teams[name]["seed"] = seed

        # Record wins/losses — skip First Four per pool rules
        if state == "post" and round_name != "First Four":
            for comp in competition.get("competitors", []):
                team_data = comp.get("team", {})
                name = team_data.get("shortDisplayName", team_data.get("displayName", ""))
                if not name or name not in teams:
                    continue
                if comp.get("winner", False):
                    teams[name]["wins"] += 1
                    teams[name]["current_round"] = round_name
                else:
                    teams[name]["eliminated"] = True

    logging.info("Loaded %d tournament teams", len(teams))
    return teams
