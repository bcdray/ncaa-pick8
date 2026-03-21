import logging
import re
import unicodedata
from difflib import get_close_matches

MAX_WINS = 6  # Round of 64 through Championship


def normalize(s):
    """Lowercase, strip accents and punctuation for fuzzy comparison."""
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", "", s.lower().strip())
    return " ".join(s.split())


def _strip_seed_suffix(name):
    """Strip trailing seed annotation e.g. 'VCU - 11' -> 'VCU', 'Utah St - 9' -> 'Utah St'."""
    return re.sub(r'\s*-\s*\d+\s*$', '', name).strip()


def match_team(user_name, espn_teams):
    """Match a user-entered team name to the closest ESPN team name.

    Steps: strip seed suffix → exact → case-insensitive → normalized → fuzzy (difflib).
    Returns ESPN name string or None if no match found.
    """
    if not user_name:
        return None

    # Strip trailing seed annotation (e.g. "VCU - 11" -> "VCU")
    user_name = _strip_seed_suffix(user_name)

    # Exact match
    if user_name in espn_teams:
        return user_name

    # Case-insensitive
    for espn_name in espn_teams:
        if user_name.lower() == espn_name.lower():
            return espn_name

    # Normalized
    user_norm = normalize(user_name)
    for espn_name in espn_teams:
        if user_norm == normalize(espn_name):
            return espn_name

    # Fuzzy
    norm_map = {normalize(n): n for n in espn_teams}
    matches = get_close_matches(user_norm, norm_map.keys(), n=1, cutoff=0.75)
    if matches:
        matched = norm_map[matches[0]]
        logging.info("Fuzzy matched '%s' -> '%s'", user_name, matched)
        return matched

    logging.warning("No match found for team: '%s'", user_name)
    return None


def score_picks(picks, teams):
    """Score each player's 8 picks against tournament results.

    Points = seed × wins (First Four excluded).
    Potential left = seed × (MAX_WINS - wins) for each team still alive.

    Returns list sorted by current_points descending, with rank added.
    """
    scored = []

    for player in picks:
        current_points = 0
        potential_left = 0
        pick_details = []

        for pick_name in player["picks"]:
            espn_name = match_team(pick_name, teams)

            if espn_name:
                team = teams[espn_name]
                seed = team["seed"]
                wins = team["wins"]
                eliminated = team["eliminated"]
                points = seed * wins
                pot = seed * (MAX_WINS - wins) if not eliminated else 0

                current_points += points
                potential_left += pot

                pick_details.append({
                    "pick_name": pick_name,
                    "espn_name": espn_name,
                    "seed": seed,
                    "wins": wins,
                    "points": points,
                    "eliminated": eliminated,
                    "potential_left": pot,
                    "next_opponent": team.get("next_opponent"),
                })
            else:
                pick_details.append({
                    "pick_name": pick_name,
                    "espn_name": None,
                    "seed": "?",
                    "wins": 0,
                    "points": 0,
                    "eliminated": False,
                    "potential_left": 0,
                })

        scored.append({
            "name": player["name"],
            "current_points": current_points,
            "potential_left": potential_left,
            "picks": pick_details,
        })

    scored.sort(key=lambda x: x["current_points"], reverse=True)
    for i, p in enumerate(scored):
        p["rank"] = i + 1

    return scored


def calculate_prizes(num_entries, entry_fee=20):
    """Calculate prize amounts based on entry count.

    < 10:  2nd gets money back, 1st gets rest
    10-19: 3rd gets money back, 2nd gets 25%, 1st gets rest
    20+:   4th gets money back, 3rd gets 10%, 2nd gets 20%, 1st gets rest
    """
    total = num_entries * entry_fee

    if num_entries < 10:
        second = entry_fee
        first = total - second
        prizes = [
            {"place": 1, "label": "1st Place", "amount": first},
            {"place": 2, "label": "2nd Place", "amount": second},
        ]
    elif num_entries < 20:
        third = entry_fee
        second = round(total * 0.25)
        first = total - second - third
        prizes = [
            {"place": 1, "label": "1st Place", "amount": first},
            {"place": 2, "label": "2nd Place", "amount": second},
            {"place": 3, "label": "3rd Place", "amount": third},
        ]
    else:
        fourth = entry_fee
        third = round(total * 0.10)
        second = round(total * 0.20)
        first = total - second - third - fourth
        prizes = [
            {"place": 1, "label": "1st Place", "amount": first},
            {"place": 2, "label": "2nd Place", "amount": second},
            {"place": 3, "label": "3rd Place", "amount": third},
            {"place": 4, "label": "4th Place", "amount": fourth},
        ]

    return {"total_pot": total, "prizes": prizes}


def build_scenarios(scored_players):
    """For each player, calculate contention status and what they need to win.

    - in_contention: can they still mathematically win?
    - best_case: current points + all potential left
    - points_needed: how many more points to lead right now
    - root_for: their alive teams sorted by potential (highest first)
    - root_against: rivals' alive teams (not shared with this player) sorted by threat
    """
    if not scored_players:
        return []

    leader = scored_players[0]
    leader_current = leader["current_points"]

    scenarios = []

    for player in scored_players:
        best_case = player["current_points"] + player["potential_left"]
        in_contention = best_case > leader_current or player["rank"] == 1
        points_needed = max(0, leader_current - player["current_points"] + 1) if player["rank"] != 1 else 0

        # Teams this player picked (for exclusion in root_against)
        my_teams = {pick["espn_name"] for pick in player["picks"] if pick["espn_name"]}

        # Root for: own alive teams with points still available
        root_for = [
            {
                "team": pick["espn_name"],
                "seed": pick["seed"],
                "wins": pick["wins"],
                "potential": pick["potential_left"],
                "next_opponent": pick.get("next_opponent"),
            }
            for pick in player["picks"]
            if not pick["eliminated"] and pick.get("potential_left", 0) > 0 and pick["espn_name"]
        ]
        root_for.sort(key=lambda x: x["potential"], reverse=True)

        # Root against: other players' alive teams NOT shared with this player,
        # belonging to rivals who could still beat this player
        root_against = []
        for other in scored_players:
            if other["name"] == player["name"]:
                continue
            other_best = other["current_points"] + other["potential_left"]
            # Skip rivals who can't possibly beat this player's best case
            if other_best < player["current_points"] and other["current_points"] < player["current_points"]:
                continue
            for pick in other["picks"]:
                if (not pick["eliminated"]
                        and pick.get("potential_left", 0) > 0
                        and pick["espn_name"]
                        and pick["espn_name"] not in my_teams):
                    root_against.append({
                        "player": other["name"],
                        "team": pick["espn_name"],
                        "seed": pick["seed"],
                        "potential": pick["potential_left"],
                        "next_opponent": pick.get("next_opponent"),
                    })

        root_against.sort(key=lambda x: x["potential"], reverse=True)
        root_against = root_against[:6]

        scenarios.append({
            "name": player["name"],
            "rank": player["rank"],
            "current_points": player["current_points"],
            "best_case": best_case,
            "in_contention": in_contention,
            "points_needed": points_needed,
            "root_for": root_for,
            "root_against": root_against,
        })

    return scenarios
