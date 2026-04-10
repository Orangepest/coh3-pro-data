"""
CoH3 1v1 Pro Scene Dashboard
Run: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import traceback
from contextlib import contextmanager


@contextmanager
def safe_section(name: str):
    """Wrap a dashboard section so errors don't crash other sections."""
    try:
        yield
    except Exception as e:
        st.error(f"Error in {name}: {type(e).__name__}: {e}")
        with st.expander("Show traceback"):
            st.code(traceback.format_exc())

from analyze import (
    load_matches_df,
    load_leaderboard_df,
    load_build_orders_df,
    available_patches,
    faction_winrates,
    faction_matchup_matrix,
    map_stats,
    map_faction_winrates,
    duration_distribution,
    top_players,
    head_to_head,
    meta_trends,
    opener_analysis,
    battlegroup_pickrates,
    tech_timings,
    unit_popularity,
    first_unit_timing,
    player_build_tendencies,
)
from db import get_conn
from config import MIN_ELO, DB_PATH

# --- Page config ---
st.set_page_config(
    page_title="CoH3 Pro 1v1 Analyzer",
    page_icon="",
    layout="wide",
)

FACTION_COLORS = {
    "american": "#4CAF50",
    "british": "#2196F3",
    "british_africa": "#2196F3",
    "dak": "#FFC107",
    "german": "#9E9E9E",
}

FACTION_ORDER = ["american", "british", "dak", "german"]


# --- Cached data loading ---
@st.cache_data(ttl=300)
def get_matches():
    return load_matches_df()


@st.cache_data(ttl=300)
def get_leaderboard():
    return load_leaderboard_df()


@st.cache_data(ttl=300)
def get_build_orders(patch):
    return load_build_orders_df(patch=patch if patch != "All patches" else None)


@st.cache_data(ttl=300)
def get_patches():
    return available_patches()


# --- Sidebar ---
st.sidebar.title("CoH3 Pro 1v1 Analyzer")
st.sidebar.caption(f"ELO >= {MIN_ELO}")

patches_df = get_patches()
patch_options = ["All patches"]
if not patches_df.empty:
    patch_options += patches_df["patch"].tolist()
selected_patch = st.sidebar.selectbox("Patch", patch_options)

st.sidebar.markdown("---")
st.sidebar.markdown("Data sources: cohdb.com, Relic API, coh3stats.com")

# --- Load data (defensive, never crash the dashboard) ---
try:
    df = get_matches()
except Exception as e:
    st.sidebar.error(f"Failed to load matches: {e}")
    df = pd.DataFrame()
try:
    lb = get_leaderboard()
except Exception as e:
    st.sidebar.error(f"Failed to load leaderboard: {e}")
    lb = pd.DataFrame()
try:
    bo = get_build_orders(selected_patch)
except Exception as e:
    st.sidebar.error(f"Failed to load build orders: {e}")
    bo = pd.DataFrame()

# --- Tabs ---
tab_overview, tab_maps, tab_builds, tab_tech, tab_players, tab_trends, tab_sql = st.tabs([
    "Overview", "Map Stats", "Build Orders", "Tech Timings", "Players", "Meta Trends", "SQL Query"
])


# =========================================================================
# TAB 1: Overview
# =========================================================================
with tab_overview, safe_section("Overview"):
    st.header("Overview")

    # Summary stats
    if not bo.empty:
        bo_games = bo["replay_id"].nunique()
        bo_players = bo["player_name"].nunique()
        patch_label = selected_patch if selected_patch != "All patches" else "all patches"
        col1, col2, col3 = st.columns(3)
        col1.metric("Build Order Games", bo_games)
        col2.metric("Unique Players", bo_players)
        col3.metric("Patch", patch_label)

    if not df.empty:
        match_count = df["match_id"].nunique()
        player_count = df["profile_id"].nunique()
        col1, col2 = st.columns(2)
        col1.metric("Relic API Matches", match_count)
        col2.metric("Relic API Players", player_count)

    # Faction win rates
    if not df.empty:
        st.subheader("Faction Win Rates")
        wr = faction_winrates(df)
        fig = px.bar(
            wr.reset_index(),
            x="winrate_pct",
            y="faction",
            orientation="h",
            color="faction",
            color_discrete_map=FACTION_COLORS,
            text="winrate_pct",
            labels={"winrate_pct": "Win Rate %", "faction": "Faction"},
        )
        fig.update_layout(showlegend=False, yaxis=dict(categoryorder="total ascending"))
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

        # Matchup matrix
        st.subheader("Faction Matchup Matrix (Win %)")
        matrix = faction_matchup_matrix(df)
        if not matrix.empty:
            fig2 = px.imshow(
                matrix,
                text_auto=".1f",
                color_continuous_scale="RdYlGn",
                zmin=30, zmax=70,
                labels=dict(x="Opponent", y="Faction", color="Win %"),
            )
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)

    # Leaderboard summary
    if not lb.empty:
        st.subheader("Leaderboard Summary")
        lb_summary = lb.groupby("faction").agg(
            players=("profile_id", "nunique"),
            avg_elo=("elo", "mean"),
            max_elo=("elo", "max"),
        ).round(0).astype(int)
        st.dataframe(lb_summary, use_container_width=True)

    if df.empty and bo.empty:
        st.warning("No data yet. Run the scrapers first: `python3 run.py scrape`")


# =========================================================================
# TAB 2: Map Stats
# =========================================================================
with tab_maps, safe_section("Map Stats"):
    st.header("Map Statistics")

    if not df.empty:
        ms = map_stats(df)
        st.subheader("Map Overview")
        st.dataframe(ms, use_container_width=True)

        # Map play frequency bar chart
        fig = px.bar(
            ms.reset_index().sort_values("total_matches", ascending=True),
            x="total_matches", y="map_name",
            orientation="h",
            labels={"total_matches": "Matches Played", "map_name": "Map"},
        )
        fig.update_layout(height=max(400, len(ms) * 30))
        st.plotly_chart(fig, use_container_width=True)

        # Map faction win rates
        st.subheader("Faction Win Rates by Map")
        mf = map_faction_winrates(df)
        if not mf.empty:
            st.dataframe(mf.style.format("{:.1f}%"), use_container_width=True)

        # Duration distribution
        st.subheader("Match Duration Distribution")
        dd = duration_distribution(df)
        if not dd.empty:
            fig3 = px.bar(
                dd.reset_index(),
                x="bucket", y="matches",
                text="pct",
                labels={"bucket": "Duration (minutes)", "matches": "Games", "pct": "%"},
            )
            fig3.update_traces(texttemplate="%{text}%", textposition="outside")
            st.plotly_chart(fig3, use_container_width=True)
    else:
        st.warning("No match data. Run: `python3 run.py scrape-matches`")


# =========================================================================
# TAB 3: Build Orders
# =========================================================================
with tab_builds, safe_section("Build Orders"):
    st.header("Build Orders")

    if not bo.empty:
        bo_games = bo["replay_id"].nunique()
        st.caption(f"{bo_games} games | Patch: {selected_patch}")

        # Opener analysis
        st.subheader("Most Common Openers")
        opener_depth = st.slider("First N units", 3, 8, 5, key="opener_depth")
        op = opener_analysis(bo, opener_depth)
        if not op.empty:
            st.dataframe(op, use_container_width=True)

        # Battlegroup pickrates
        st.subheader("Battlegroup Pick Rates")
        bg = battlegroup_pickrates(bo)
        if not bg.empty:
            fig = px.bar(
                bg.reset_index().sort_values("picks", ascending=True),
                x="picks", y="unit",
                orientation="h",
                text="pickrate_pct",
                labels={"picks": "Times Picked", "unit": "Battlegroup"},
            )
            fig.update_traces(texttemplate="%{text}%", textposition="outside")
            fig.update_layout(height=max(400, len(bg) * 35))
            st.plotly_chart(fig, use_container_width=True)

        # Unit popularity
        st.subheader("Most Produced Units")
        up = unit_popularity(bo).head(30)
        if not up.empty:
            fig2 = px.bar(
                up.reset_index().sort_values("times_built", ascending=True).tail(20),
                x="times_built", y="unit",
                orientation="h",
                labels={"times_built": "Times Built", "unit": "Unit"},
            )
            fig2.update_layout(height=600)
            st.plotly_chart(fig2, use_container_width=True)
            st.dataframe(up, use_container_width=True)
    else:
        st.warning("No build order data. Run: `python3 run.py scrape-cohdb`")


# =========================================================================
# TAB 4: Tech Timings
# =========================================================================
with tab_tech, safe_section("Tech Timings"):
    st.header("Tech Timings")

    if not bo.empty:
        st.caption(f"Patch: {selected_patch}")

        def secs_to_mss(s):
            """Convert seconds to m:ss string."""
            m, sec = divmod(int(s), 60)
            return f"{m}:{sec:02d}"

        # Category filter
        categories = ["All", "production", "tech", "battlegroup", "ability"]
        selected_cat = st.selectbox("Category", categories, key="tech_cat")

        bo_filtered = bo if selected_cat == "All" else bo[bo["action_type"] == selected_cat]

        # Timing chart for filtered category
        if not bo_filtered.empty:
            st.subheader(f"Average Timings - {selected_cat.title()}")
            filtered_stats = bo_filtered.groupby("unit").agg(
                count=("seconds", "count"),
                avg_seconds=("seconds", "mean"),
                median_seconds=("seconds", "median"),
                earliest=("seconds", "min"),
                latest=("seconds", "max"),
            ).round(0)
            filtered_stats = filtered_stats[filtered_stats["count"] >= 3]

            if not filtered_stats.empty:
                chart_data = filtered_stats.reset_index().sort_values("avg_seconds")
                chart_data["avg_label"] = chart_data["avg_seconds"].apply(secs_to_mss)
                fig = px.bar(
                    chart_data,
                    x="avg_seconds", y="unit",
                    orientation="h",
                    text="avg_label",
                    labels={"avg_seconds": "Average Time (seconds)", "unit": "Unit / Ability"},
                    hover_data=["count"],
                )
                fig.update_traces(textposition="outside")
                fig.update_layout(height=max(400, len(chart_data) * 35))
                st.plotly_chart(fig, use_container_width=True)

                # Table with m:ss
                display = filtered_stats.copy()
                for col in ["avg_seconds", "median_seconds", "earliest", "latest"]:
                    display[col] = display[col].apply(secs_to_mss)
                display.columns = ["count", "avg", "median", "earliest", "latest"]
                st.dataframe(display, use_container_width=True)

        # Battlegroup breakdown - what gets built after each BG pick
        st.subheader("Battlegroup Ability Breakdown")
        st.caption("What abilities/units are used after picking each battlegroup")

        bg_picks = bo[bo["action_type"] == "battlegroup"]["unit"].value_counts()
        bg_list = bg_picks[bg_picks >= 5].index.tolist()

        if bg_list:
            selected_bg = st.selectbox("Select battlegroup", bg_list, key="bg_breakdown")

            # Find replays where this BG was picked, get abilities used by same player
            bg_replays = bo[
                (bo["action_type"] == "battlegroup") & (bo["unit"] == selected_bg)
            ][["replay_id", "player_name", "seconds"]].rename(columns={"seconds": "bg_pick_time"})

            if not bg_replays.empty:
                # Join with abilities used after the BG pick
                merged = bo.merge(bg_replays, on=["replay_id", "player_name"])
                after_bg = merged[
                    (merged["seconds"] > merged["bg_pick_time"])
                    & (merged["action_type"].isin(["ability", "production"]))
                ]

                if not after_bg.empty:
                    ability_stats = after_bg.groupby("unit").agg(
                        times_used=("seconds", "count"),
                        avg_time=("seconds", "mean"),
                    ).round(0).sort_values("times_used", ascending=False).head(15)
                    ability_stats["avg_time"] = ability_stats["avg_time"].apply(secs_to_mss)

                    games_with_bg = len(bg_replays)
                    st.metric(f"Games with {selected_bg}", games_with_bg)
                    st.dataframe(ability_stats, use_container_width=True)

        # Per-unit drill down
        st.subheader("Unit Timing Drill-Down")
        all_units = sorted(bo_filtered["unit"].unique())
        if len(all_units) > 0:
            selected_unit = st.selectbox("Select unit", all_units, key="unit_drilldown")
            unit_data = bo_filtered[bo_filtered["unit"] == selected_unit]
            # Get first occurrence per player per game
            fut = unit_data.groupby(["replay_id", "player_name"])["seconds"].min().reset_index()
            fut.columns = ["replay_id", "player_name", "first_built_s"]
            fut["first_built_min"] = (fut["first_built_s"] / 60).round(1)

            if not fut.empty:
                fig2 = px.histogram(
                    fut, x="first_built_min",
                    nbins=20,
                    labels={"first_built_min": "First Used (minutes)"},
                    title=f"When {selected_unit} first appears",
                )
                st.plotly_chart(fig2, use_container_width=True)

                col1, col2, col3 = st.columns(3)
                col1.metric("Median", f"{secs_to_mss(fut['first_built_s'].median())}")
                col2.metric("Earliest", f"{secs_to_mss(fut['first_built_s'].min())}")
                col3.metric("Games Used In", f"{len(fut)} / {bo['replay_id'].nunique()}")
            else:
                st.info(f"No data for {selected_unit}")
    else:
        st.warning("No build order data. Run: `python3 run.py scrape-cohdb`")


# =========================================================================
# TAB 5: Players
# =========================================================================
with tab_players, safe_section("Players"):
    st.header("Players")

    # Top players from Relic API match data
    if not df.empty:
        st.subheader("Top Players by Games Played")
        tp = top_players(df, 50)
        if not tp.empty:
            st.dataframe(tp, use_container_width=True)

    # Player build tendencies from cohdb
    if not bo.empty:
        st.subheader("Player Build Analysis")
        all_players = bo["player_name"].value_counts()
        player_list = all_players.index.tolist()

        selected_player = st.selectbox("Select player", player_list, key="player_select")

        if selected_player:
            # Show ELO across factions from leaderboard data
            if not lb.empty:
                player_lb = lb[lb["alias"] == selected_player]
                if player_lb.empty:
                    # Try fuzzy match - cohdb names may differ slightly from Relic aliases
                    player_lb = lb[lb["alias"].str.lower() == selected_player.lower()]
                if not player_lb.empty:
                    elo_cols = st.columns(len(player_lb))
                    for i, (_, row) in enumerate(player_lb.iterrows()):
                        color = FACTION_COLORS.get(row["faction"], "#888")
                        elo_cols[i].metric(
                            f"{row['faction'].upper()}",
                            f"{int(row['elo'])} ELO",
                            f"W{int(row['wins'])} / L{int(row['losses'])}",
                        )

            result = player_build_tendencies(bo, selected_player)
            if "error" not in result:
                st.metric("Games Analyzed", result["total_games"])
                st.metric("Avg Actions/Game", result["avg_actions_per_game"])

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Favorite Openers**")
                    st.dataframe(result["favorite_openers"], use_container_width=True)
                with col2:
                    st.markdown("**Battlegroup Picks**")
                    if not result["battlegroups"].empty:
                        bg_df = result["battlegroups"].reset_index()
                        bg_df.columns = ["battlegroup", "picks"]
                        st.dataframe(bg_df, use_container_width=True)
                    else:
                        st.info("No battlegroup data")

                st.markdown("**Most Built Units**")
                if not result["most_built_units"].empty:
                    units_df = result["most_built_units"].reset_index()
                    units_df.columns = ["unit", "count"]
                    fig = px.bar(units_df, x="count", y="unit", orientation="h")
                    fig.update_layout(height=400, yaxis=dict(categoryorder="total ascending"))
                    st.plotly_chart(fig, use_container_width=True)

        # Head to head
        st.subheader("Head-to-Head")
        if not df.empty:
            aliases = df[df["alias"] != ""]["alias"].unique().tolist()
            aliases.sort()
            if len(aliases) >= 2:
                col1, col2 = st.columns(2)
                p1 = col1.selectbox("Player 1", aliases, key="h2h_p1")
                p2 = col2.selectbox("Player 2", aliases, index=min(1, len(aliases)-1), key="h2h_p2")
                if p1 and p2 and p1 != p2:
                    h2h = head_to_head(df, p1, p2)
                    if not h2h.empty:
                        st.dataframe(h2h, use_container_width=True)
                    else:
                        st.info(f"No shared matches between {p1} and {p2}")
            else:
                st.info("Need at least 2 players with aliases for head-to-head")

    if df.empty and bo.empty:
        st.warning("No data yet. Run the scrapers first.")


# =========================================================================
# TAB 6: Meta Trends
# =========================================================================
with tab_trends, safe_section("Meta Trends"):
    st.header("Meta Trends")

    if not df.empty and "month" in df.columns:
        mt = meta_trends(df)
        if not mt.empty:
            mt_reset = mt.reset_index()
            mt_reset["month"] = mt_reset["month"].astype(str)

            st.subheader("Monthly Faction Win Rate")
            fig = px.line(
                mt_reset, x="month", y="winrate_pct", color="faction",
                color_discrete_map=FACTION_COLORS,
                labels={"winrate_pct": "Win Rate %", "month": "Month", "faction": "Faction"},
                markers=True,
            )
            fig.update_layout(yaxis=dict(range=[35, 65]))
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Monthly Faction Pick Rate")
            fig2 = px.line(
                mt_reset, x="month", y="pickrate_pct", color="faction",
                color_discrete_map=FACTION_COLORS,
                labels={"pickrate_pct": "Pick Rate %", "month": "Month", "faction": "Faction"},
                markers=True,
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.dataframe(mt, use_container_width=True)
        else:
            st.info("Not enough data for trend analysis")
    else:
        st.warning("No match data with timestamps. Run: `python3 run.py scrape-matches`")


# =========================================================================
# TAB 7: SQL Query
# =========================================================================
with tab_sql, safe_section("SQL Query"):
    st.header("SQL Query")

    # Schema reference
    with st.expander("Database Schema"):
        st.markdown("""
**players** - profile_id, alias, steam_id, country, last_updated

**leaderboard_entries** - profile_id, faction, elo, wins, losses, rank, streak, scraped_at

**matches** - match_id, map_name, match_type, start_time, duration_s, scraped_at

**match_players** - match_id, profile_id, faction, elo_before, elo_after, elo_diff, result, team_id

**cohdb_replays** - replay_id, match_id, map_name, mode, duration_s, result, patch, scraped_at

**build_orders** - replay_id, player_name, seconds, unit, action_type
        """)

    query = st.text_area(
        "Enter SQL query",
        value="SELECT * FROM build_orders ORDER BY replay_id, player_name, seconds LIMIT 50",
        height=150,
    )

    if st.button("Run Query"):
        try:
            conn = get_conn()
            conn.execute("PRAGMA query_only=ON")
            result = pd.read_sql_query(query, conn)
            conn.close()
            st.success(f"{len(result)} rows returned")
            st.dataframe(result, use_container_width=True)
            st.download_button(
                "Download CSV",
                result.to_csv(index=False),
                "coh3_query_result.csv",
                mime="text/csv",
            )
        except Exception as e:
            st.error(f"Query error: {e}")
