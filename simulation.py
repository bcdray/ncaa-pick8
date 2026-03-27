import random
import logging
from scoring import match_team


def run_monte_carlo(picks_list, teams_data, n_sims=10_000):
    """Run Monte Carlo simulation of remaining tournament games.

    picks_list: list of {"name": str, "picks": [str, ...]}
    teams_data: dict from fetch_tournament_teams()

    Returns list sorted by win_pct descending:
    [{"name", "win_pct", "top3_pct", "best_finish", "worst_finish",
      "eliminated", "current_points"}, ...]
    """
    if not picks_list or not teams_data:
        return []

    n_players = len(picks_list)

    # Pre-match each player's picks to ESPN team names once
    player_espn_picks = []
    for player in picks_list:
        espn_picks = []
        for pick_name in player["picks"]:
            espn_name = match_team(pick_name, teams_data)
            espn_picks.append(espn_name)
        player_espn_picks.append({"name": player["name"], "espn_picks": espn_picks})

    # Identify alive teams and current scheduled matchups
    alive = {name for name, d in teams_data.items() if not d["eliminated"]}

    if not alive:
        return _score_current(player_espn_picks, teams_data, n_players)

    scheduled_pairs = []
    seen = set()
    unscheduled = []

    for name in alive:
        opp = teams_data[name].get("next_opponent")
        if opp and opp in alive:
            pair = tuple(sorted([name, opp]))
            if pair not in seen:
                seen.add(pair)
                scheduled_pairs.append(list(pair))
        elif not opp:
            unscheduled.append(name)

    scheduled_names = {t for pair in scheduled_pairs for t in pair}
    unscheduled = [t for t in unscheduled if t not in scheduled_names]

    # Tracking
    place_counts = {p["name"]: [0] * n_players for p in picks_list}

    for _ in range(n_sims):
        sim_wins = {name: teams_data[name]["wins"] for name in teams_data}

        # Simulate current scheduled games
        next_round = []
        for a, b in scheduled_pairs:
            winner = a if random.random() < 0.5 else b
            sim_wins[winner] += 1
            next_round.append(winner)

        next_round += unscheduled

        # Simulate subsequent rounds until one champion
        while len(next_round) > 1:
            random.shuffle(next_round)
            survivors = []
            for i in range(0, len(next_round) - 1, 2):
                a, b = next_round[i], next_round[i + 1]
                winner = a if random.random() < 0.5 else b
                sim_wins[winner] += 1
                survivors.append(winner)
            if len(next_round) % 2 == 1:
                survivors.append(next_round[-1])
            next_round = survivors

        # Score each player for this simulation
        sim_scores = []
        for p in player_espn_picks:
            total = sum(
                teams_data[name]["seed"] * sim_wins[name]
                for name in p["espn_picks"]
                if name and name in sim_wins
            )
            sim_scores.append((p["name"], total))

        sim_scores.sort(key=lambda x: x[1], reverse=True)
        for rank, (name, _) in enumerate(sim_scores, 1):
            place_counts[name][rank - 1] += 1

    # Build results
    results = []
    for p in player_espn_picks:
        name = p["name"]
        counts = place_counts[name]
        wins = counts[0]
        second = counts[1] if n_players > 1 else 0
        third = counts[2] if n_players > 2 else 0
        fourth = counts[3] if n_players > 3 else 0

        best = next((i + 1 for i, c in enumerate(counts) if c > 0), n_players)
        worst = next((i + 1 for i, c in reversed(list(enumerate(counts))) if c > 0), 1)

        current_pts = sum(
            teams_data[n_]["seed"] * teams_data[n_]["wins"]
            for n_ in p["espn_picks"]
            if n_ and n_ in teams_data
        )

        results.append({
            "name": name,
            "win_pct": round(wins / n_sims * 100, 1),
            "second_pct": round(second / n_sims * 100, 1),
            "third_pct": round(third / n_sims * 100, 1),
            "fourth_pct": round(fourth / n_sims * 100, 1),
            "best_finish": best,
            "worst_finish": worst,
            "eliminated": wins == 0,
            "current_points": current_pts,
        })

    results.sort(key=lambda x: x["win_pct"], reverse=True)
    logging.info("Monte Carlo complete: %d sims, %d players", n_sims, n_players)
    return results


def _score_current(player_espn_picks, teams_data, n_players):
    """Return final standings when tournament is already over."""
    scored = []
    for p in player_espn_picks:
        pts = sum(
            teams_data[n]["seed"] * teams_data[n]["wins"]
            for n in p["espn_picks"]
            if n and n in teams_data
        )
        scored.append({"name": p["name"], "current_points": pts})
    scored.sort(key=lambda x: x["current_points"], reverse=True)
    results = []
    for i, s in enumerate(scored):
        results.append({
            "name": s["name"],
            "win_pct": 100.0 if i == 0 else 0.0,
            "top3_pct": 100.0 if i < 3 else 0.0,
            "best_finish": i + 1,
            "worst_finish": i + 1,
            "eliminated": i > 0,
            "current_points": s["current_points"],
        })
    return results
