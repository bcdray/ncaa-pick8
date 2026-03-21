import os
import pandas as pd
import streamlit as st

from espn import fetch_tournament_teams
from scoring import build_scenarios, calculate_prizes, score_picks
from sheets import load_picks

st.set_page_config(page_title="NCAA Pick 8", layout="wide")

SHEET_ID = os.environ.get("NCAA_SHEET_ID", "")


@st.cache_data(ttl=300)
def load_data():
    picks = load_picks(SHEET_ID)
    teams = fetch_tournament_teams()
    scored = score_picks(picks, teams)
    prize_info = calculate_prizes(len(picks))
    scenarios = build_scenarios(scored)
    return scored, prize_info, scenarios


scored, prize_info, scenarios = load_data()

st.title("🏀 NCAA Pick 8 Pool")
st.caption(f"💰 Total Pot: ${prize_info['total_pot']} · {len(scored)} entries")

tab1, tab2, tab3, tab4 = st.tabs(["Leaderboard", "Picks", "Analysis", "Scenarios"])

# ── Leaderboard ───────────────────────────────────────────────────────────────
with tab1:
    prize_map = {p["place"]: p["amount"] for p in prize_info["prizes"]}
    rows = []
    for p in scored:
        rows.append({
            "Rank": p["rank"],
            "Player": p["name"],
            "Points": p["current_points"],
            "Potential Left": p["potential_left"],
            "Prize": f"${prize_map[p['rank']]}" if p["rank"] in prize_map else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Picks ─────────────────────────────────────────────────────────────────────
with tab2:
    for p in scored:
        with st.expander(f"{p['name']} — {p['current_points']} pts · {p['potential_left']} potential left"):
            rows = []
            for pick in p["picks"]:
                rows.append({
                    "Team": pick["espn_name"] or f"❓ {pick['pick_name']}",
                    "Seed": pick["seed"],
                    "Wins": pick["wins"],
                    "Points": pick["points"],
                    "Max Left": pick["potential_left"],
                    "Status": "❌ Out" if pick["eliminated"] else ("✅ Alive" if pick["espn_name"] else "❓ Unmatched"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Analysis ──────────────────────────────────────────────────────────────────
with tab3:
    team_counts = {}
    for p in scored:
        for pick in p["picks"]:
            key = pick["espn_name"] or pick["pick_name"]
            if key not in team_counts:
                team_counts[key] = {"count": 0, "seed": pick["seed"], "points": pick["points"], "pickers": []}
            team_counts[key]["count"] += 1
            team_counts[key]["pickers"].append(p["name"])

    df = pd.DataFrame([
        {
            "Team": k,
            "Seed": v["seed"],
            "Times Picked": v["count"],
            "Pts Earned": v["points"],
            "Picked By": ", ".join(v["pickers"]),
        }
        for k, v in team_counts.items()
    ]).sort_values("Times Picked", ascending=False)

    st.bar_chart(df.set_index("Team")["Times Picked"])
    st.dataframe(df, use_container_width=True, hide_index=True)

# ── Scenarios ─────────────────────────────────────────────────────────────────
with tab4:
    for s in scenarios:
        status = "🏆 Leading" if s["rank"] == 1 else ("✅ In Contention" if s["in_contention"] else "❌ Eliminated")
        with st.expander(f"{s['name']} · {status} · Best case: {s['best_case']} pts"):
            if s["points_needed"] > 0:
                st.info(f"Needs {s['points_needed']} more points to lead")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**🟢 Root For**")
                for t in s["root_for"]:
                    opp = f"vs {t['next_opponent']}" if t["next_opponent"] else "TBD"
                    st.markdown(f"- **{t['team']}** (#{t['seed']}) · +{t['potential']} pts · {opp}")
            with col2:
                st.markdown("**🔴 Root Against**")
                for t in s["root_against"]:
                    opp = f"vs {t['next_opponent']}" if t["next_opponent"] else "TBD"
                    pickers = ", ".join(t["players"])
                    st.markdown(f"- **{t['team']}** (#{t['seed']}) · +{t['potential']} pts for {pickers} · {opp}")
