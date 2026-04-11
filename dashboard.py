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

# Import the whole module rather than individual functions.
# This way, adding a new function to analyze.py won't break the dashboard's
# top-level import on Streamlit Cloud (which sometimes lags loading the new
# version of analyze.py while loading the new dashboard.py). Missing functions
# now fail at call-time inside safe_section() rather than at import time.
import analyze

# Convenience: bind the most-used functions to the global namespace so the rest
# of this file doesn't need 'analyze.' prefix everywhere. New functions added
# later should be referenced as 'analyze.<name>' so they fail gracefully via
# safe_section if not yet deployed.
load_matches_df = analyze.load_matches_df
load_leaderboard_df = analyze.load_leaderboard_df
load_build_orders_df = analyze.load_build_orders_df
available_patches = analyze.available_patches
faction_winrates = analyze.faction_winrates
faction_matchup_matrix = analyze.faction_matchup_matrix
map_stats = analyze.map_stats
map_faction_winrates = analyze.map_faction_winrates
duration_distribution = analyze.duration_distribution
top_players = analyze.top_players
head_to_head = analyze.head_to_head
meta_trends = analyze.meta_trends
opener_analysis = analyze.opener_analysis
battlegroup_pickrates = analyze.battlegroup_pickrates
tech_timings = analyze.tech_timings
unit_popularity = analyze.unit_popularity
first_unit_timing = analyze.first_unit_timing
player_build_tendencies = analyze.player_build_tendencies
category_timing_comparison = analyze.category_timing_comparison
category_arrival_at_minute = analyze.category_arrival_at_minute

# Newer functions referenced via analyze.<name> so safe_section handles missing ones.
# (opener_winrates, opener_winrates_by_map, opener_matchup_winrates,
#  winrate_by_unit_count, battlegroup_matchup_winrates, battlegroup_overall_winrates)

from unit_categories import all_categories, CATEGORY_LABELS
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

try:
    patches_df = get_patches()
except Exception as e:
    st.sidebar.error(f"Failed to load patches: {e}")
    patches_df = pd.DataFrame()
patch_options = ["All patches"]
if not patches_df.empty:
    patch_options += patches_df["patch"].tolist()
selected_patch = st.sidebar.selectbox("Patch", patch_options)

# Ragequit filter - exclude super-short matches where someone disconnected
min_match_minutes = st.sidebar.slider(
    "Min match length (minutes)",
    0, 15, 2,
    help="Excludes ragequits / disconnects. Default 2 min.",
)

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

# Apply ragequit filter to both DataFrames
if min_match_minutes > 0:
    min_seconds = min_match_minutes * 60
    if not df.empty and "duration_s" in df.columns:
        df = df[df["duration_s"].fillna(0) >= min_seconds]
    if not bo.empty and "match_duration_s" in bo.columns:
        bo = bo[bo["match_duration_s"].fillna(0) >= min_seconds]

# --- Tabs ---
tab_overview, tab_maps, tab_builds, tab_tech, tab_compare, tab_players, tab_trends, tab_sql = st.tabs([
    "Overview", "Map Stats", "Build Orders", "Tech Timings", "Unit Compare", "Players", "Meta Trends", "SQL Query"
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

    # =====================================================
    # SLOT POSITION ADVANTAGE
    # =====================================================
    st.subheader("Map Position Advantage")
    st.caption(
        "On asymmetric maps, one spawn position has a measurable advantage. "
        "Slot 0 = first player in the cohdb timeline (= first player in the .rec file). "
        "Slot 1 winrate is just (100 − slot 0)."
    )

    with st.expander("⚠ Caveats - read me before drawing conclusions"):
        st.markdown("""
**Sample size limits:** Most maps have 40-150 games. Anything within ±5 percentage
points of 50% (basically Faymonville and Djebel) is statistical noise — those maps
are effectively symmetric.

**Slot labels are user-derived, not verified per game:** Only Crossing in the Woods
is verified by direct cast→DB replay matching. The other 5 labeled maps were derived
by combining ONE Propagandacast video observation with the user's gut feel for which
side is favored. They could be wrong if either:
  - the cast video happened to be a slot-flipped game (unlikely but possible)
  - the user's intuition about the favored side is biased

**Slot order varies game-to-game:** For the same pair of players, slot 0 vs slot 1
is randomized by matchmaking. The labels here are about FIXED physical positions per
map, not about specific players.

**ELO is high (1600+):** These winrates are from the top 1v1 ranked. Lower ELO games
may behave differently — at lower skill, positional advantage matters less because
mistakes dominate.

**Patch-specific:** Data is from patch 2.3.1 only. Spawn balance may shift on patches.

**Some maps are missing labels** (bologna, djebel, villa_fiore, egletons, desert_village,
tuscan_vineyard, cliff_crossing) — they show 'slot 0/1' instead of physical positions.
""")

    try:
        from map_slot_labels import slot_label, is_labeled
        slot_data = analyze.slot_winrates_by_map(min_games=10)
        if not slot_data.empty:
            slot_chart = slot_data.reset_index()
            def make_label(row):
                m = row["map_name"]
                if is_labeled(m):
                    s0, s1 = slot_label(m, 0), slot_label(m, 1)
                    favored = s0 if row["slot0_winrate_pct"] >= 50 else s1
                    return f"{m}  →  {favored} favored"
                return f"{m}  (unlabeled)"
            slot_chart["display"] = slot_chart.apply(make_label, axis=1)

            fig_slot = px.bar(
                slot_chart.sort_values("slot0_winrate_pct"),
                x="slot0_winrate_pct", y="display",
                orientation="h",
                color="slot0_winrate_pct",
                color_continuous_scale="RdYlGn",
                range_color=[35, 65],
                text="games",
                labels={
                    "slot0_winrate_pct": "Slot 0 win % (50% = symmetric)",
                    "display": "",
                },
                hover_data=["slot0_wins", "games"],
            )
            fig_slot.update_traces(texttemplate="n=%{text}", textposition="outside")
            fig_slot.update_layout(
                height=max(400, len(slot_data) * 35),
                shapes=[dict(type="line", x0=50, x1=50, y0=-0.5,
                             y1=len(slot_data) - 0.5,
                             line=dict(color="white", width=1, dash="dash"))],
            )
            st.plotly_chart(fig_slot, use_container_width=True)

            display_table = slot_data.copy().reset_index()
            display_table["slot_0"] = display_table["map_name"].apply(
                lambda m: slot_label(m, 0))
            display_table["slot_1"] = display_table["map_name"].apply(
                lambda m: slot_label(m, 1))
            display_table["labeled"] = display_table["map_name"].apply(
                lambda m: "✓" if is_labeled(m) else "—")
            display_table["slot_1_winrate_pct"] = (100 - display_table["slot0_winrate_pct"]).round(1)
            st.dataframe(
                display_table[["map_name", "labeled", "slot_0", "slot_1",
                              "games", "slot0_winrate_pct", "slot_1_winrate_pct"]]
                .rename(columns={
                    "slot_0": "slot 0 =",
                    "slot_1": "slot 1 =",
                    "slot0_winrate_pct": "slot 0 win %",
                    "slot_1_winrate_pct": "slot 1 win %",
                }),
                use_container_width=True, hide_index=True,
            )

            unlabeled = sum(1 for m in slot_data.index if not is_labeled(m))
            if unlabeled > 0:
                st.info(
                    f"{unlabeled} maps still show slot 0/1 instead of physical positions. "
                    "Add them to map_slot_labels.py once verified."
                )
    except Exception as e:
        st.error(f"slot data unavailable: {e}")


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

        # =====================================================
        # OPENER WINRATES (NEW)
        # =====================================================
        st.subheader("Opener Winrates")
        with_winners = bo.dropna(subset=["won"])
        # Count player-games (one player in one match) - this is what we actually
        # aggregate over in opener winrates
        player_games_total = bo.groupby(["replay_id", "player_name"]).ngroups
        player_games_with_won = with_winners.groupby(["replay_id", "player_name"]).ngroups
        coverage = (player_games_with_won / max(1, player_games_total)) * 100
        st.caption(
            f"Win/loss data for {coverage:.0f}% of player-games "
            f"({player_games_with_won} of {player_games_total})."
        )

        if with_winners.empty:
            st.warning("No winner data yet. Run: `python3 backfill_winners.py`")
        else:
            col_a, col_b, col_c, col_d = st.columns(4)
            wr_depth = col_a.slider("Opener length", 3, 8, 5, key="wr_opener_depth")
            wr_min_games = col_b.slider("Min games", 3, 50, 5, key="wr_min_games")
            wr_faction = col_c.selectbox(
                "Faction",
                ["All", "us", "wehr", "uk", "dak"],
                key="wr_faction",
            )
            map_options = ["All maps"] + sorted(with_winners["map_name"].dropna().unique().tolist())
            wr_map = col_d.selectbox("Map", map_options, key="wr_map")

            wr_result = analyze.opener_winrates(
                with_winners,
                first_n=wr_depth,
                faction=wr_faction if wr_faction != "All" else None,
                map_name=wr_map if wr_map != "All maps" else None,
                min_games=wr_min_games,
            )

            if wr_result.empty:
                st.info("No openers meet the filter criteria")
            else:
                st.markdown(f"**{len(wr_result)} unique openers** "
                           f"({int(wr_result['games'].sum())} total games)")

                # Top 25 winning openers
                top_wins = wr_result.head(25).reset_index()
                fig = px.bar(
                    top_wins.sort_values("winrate_pct"),
                    x="winrate_pct", y="opener",
                    orientation="h",
                    color="winrate_pct",
                    color_continuous_scale="RdYlGn",
                    range_color=[30, 70],
                    text="games",
                    labels={"winrate_pct": "Win Rate %", "opener": ""},
                    hover_data=["wins", "games"],
                )
                fig.update_traces(texttemplate="n=%{text}", textposition="outside")
                fig.update_layout(height=max(450, len(top_wins) * 30))
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(wr_result, use_container_width=True)

            # =====================================================
            # BEST OPENER PER MAP (cross-map breakdown)
            # =====================================================
            st.subheader("Best Opener Per Map")
            st.caption("For the selected faction, find the highest-winrate opener on each map")
            col_e, col_f = st.columns(2)
            map_first_n = col_e.slider("Opener length", 3, 8, 5, key="map_opener_depth")
            map_min_games = col_f.slider("Min games per (opener, map)", 2, 20, 3, key="map_min_games")

            if wr_faction == "All":
                st.info("Select a specific faction above to use the per-map view")
            else:
                # Compute per map
                rows = []
                for m in sorted(with_winners["map_name"].dropna().unique()):
                    map_wr = analyze.opener_winrates(
                        with_winners,
                        first_n=map_first_n,
                        faction=wr_faction,
                        map_name=m,
                        min_games=map_min_games,
                    )
                    if map_wr.empty:
                        continue
                    # Best opener on this map
                    best = map_wr.iloc[0]
                    rows.append({
                        "map": m,
                        "best_opener": best.name,  # opener is in index
                        "winrate_pct": best["winrate_pct"],
                        "wins": int(best["wins"]),
                        "games": int(best["games"]),
                        "total_openers": len(map_wr),
                    })

                if rows:
                    import pandas as pd
                    map_df = pd.DataFrame(rows).sort_values("winrate_pct", ascending=False)
                    st.dataframe(map_df, use_container_width=True, hide_index=True)

                    # Bar chart: best winrate per map
                    fig_map = px.bar(
                        map_df.sort_values("winrate_pct"),
                        x="winrate_pct", y="map",
                        orientation="h",
                        color="winrate_pct",
                        color_continuous_scale="RdYlGn",
                        range_color=[30, 80],
                        text="games",
                        labels={"winrate_pct": "Best Win Rate %", "map": ""},
                        hover_data=["best_opener", "wins", "games", "total_openers"],
                    )
                    fig_map.update_traces(texttemplate="n=%{text}", textposition="outside")
                    fig_map.update_layout(height=max(350, len(map_df) * 35))
                    st.plotly_chart(fig_map, use_container_width=True)
                else:
                    st.info(f"No openers meet the criteria for {wr_faction}")

            # =====================================================
            # SPECIFIC OPENER LOOKUP - winrate per map for an opener
            # =====================================================
            st.subheader("Specific Opener × Map Winrate")
            st.caption('Pick a faction and a specific opener, see its winrate '
                       'on each map. e.g. "Pioneer → Grenadier x3 → MG 42" on Faymonville')
            col_l, col_m = st.columns(2)
            sp_faction = col_l.selectbox(
                "Faction",
                ["us", "wehr", "uk", "dak"],
                key="sp_faction",
            )
            sp_first_n = col_m.slider("Opener length", 3, 8, 5, key="sp_first_n")

            # Compute openers globally for this faction (no map filter) so we can
            # populate the dropdown with all known openers for that faction
            faction_openers = analyze.opener_winrates(
                with_winners,
                first_n=sp_first_n,
                faction=sp_faction,
                min_games=2,  # low threshold for the dropdown options
            )
            if faction_openers.empty:
                st.info(f"No openers found for {sp_faction.upper()}")
            else:
                opener_list = faction_openers.index.tolist()

                # Search filter to narrow the dropdown
                search = st.text_input(
                    "Search openers (e.g. 'Grenadier MG' to filter)",
                    key="sp_search",
                    placeholder="Type to filter the dropdown",
                )
                if search:
                    filtered = [o for o in opener_list if all(
                        kw.lower() in o.lower() for kw in search.split())]
                else:
                    filtered = opener_list

                if not filtered:
                    st.warning(f"No openers match '{search}'")
                else:
                    selected_opener = st.selectbox(
                        f"Opener ({len(filtered)} available)",
                        filtered,
                        key="sp_opener",
                    )

                    # Compute per-map winrate for this specific opener
                    per_map_rows = []
                    for m in sorted(with_winners["map_name"].dropna().unique()):
                        m_wr = analyze.opener_winrates(
                            with_winners,
                            first_n=sp_first_n,
                            faction=sp_faction,
                            map_name=m,
                            min_games=1,
                        )
                        if selected_opener in m_wr.index:
                            row = m_wr.loc[selected_opener]
                            per_map_rows.append({
                                "map": m,
                                "games": int(row["games"]),
                                "wins": int(row["wins"]),
                                "winrate_pct": row["winrate_pct"],
                            })

                    if not per_map_rows:
                        st.info("This opener wasn't played on any map yet")
                    else:
                        per_map_df = pd.DataFrame(per_map_rows).sort_values(
                            "winrate_pct", ascending=False)
                        # Show overall row at top
                        overall_row = faction_openers.loc[selected_opener]
                        st.metric(
                            f"Overall winrate for this opener",
                            f"{overall_row['winrate_pct']}%",
                            delta=f"{int(overall_row['wins'])}W / {int(overall_row['games'])}G",
                        )
                        fig_sp = px.bar(
                            per_map_df.sort_values("winrate_pct"),
                            x="winrate_pct", y="map",
                            orientation="h",
                            color="winrate_pct",
                            color_continuous_scale="RdYlGn",
                            range_color=[0, 100],
                            text="games",
                            labels={"winrate_pct": "Win %", "map": ""},
                        )
                        fig_sp.update_traces(texttemplate="n=%{text}", textposition="outside")
                        fig_sp.update_layout(
                            height=max(300, len(per_map_df) * 35),
                            shapes=[dict(type="line", x0=50, x1=50, y0=-0.5,
                                         y1=len(per_map_df) - 0.5,
                                         line=dict(color="white", width=1, dash="dash"))],
                        )
                        st.plotly_chart(fig_sp, use_container_width=True)
                        st.dataframe(per_map_df, use_container_width=True, hide_index=True)

            # =====================================================
            # OPENER vs OPENER MATCHUPS
            # =====================================================
            st.subheader("Opener vs Opener Matchups")
            st.caption("For each opener pair, what's the winrate? Adjust min games "
                       "since most opener combinations are rare.")
            col_g, col_h, col_i = st.columns(3)
            mu_first_n = col_g.slider("Opener length", 3, 8, 4, key="mu_opener_depth")
            mu_min_games = col_h.slider("Min games", 2, 20, 3, key="mu_min_games")
            sort_options = ["Highest winrate", "Lowest winrate", "Most games"]
            mu_sort = col_i.selectbox("Sort by", sort_options, key="mu_sort")

            col_j, col_k = st.columns(2)
            faction_options = ["All", "us", "wehr", "uk", "dak"]
            mu_faction_a = col_j.selectbox("Your faction", faction_options, key="mu_fac_a")
            mu_faction_b = col_k.selectbox("Opponent faction", faction_options, key="mu_fac_b")

            mu_result = analyze.opener_matchup_winrates(
                with_winners,
                first_n=mu_first_n,
                faction_a=mu_faction_a if mu_faction_a != "All" else None,
                faction_b=mu_faction_b if mu_faction_b != "All" else None,
                min_games=mu_min_games,
            )

            if mu_result.empty:
                st.info("No opener matchups meet the criteria. Try lowering min games "
                        "or shortening the opener length.")
            else:
                # Apply sort
                if mu_sort == "Highest winrate":
                    mu_display = mu_result.sort_values(["winrate_pct", "games"], ascending=[False, False])
                elif mu_sort == "Lowest winrate":
                    mu_display = mu_result.sort_values(["winrate_pct", "games"], ascending=[True, False])
                else:
                    mu_display = mu_result.sort_values("games", ascending=False)

                st.markdown(f"**{len(mu_result)} opener matchups** "
                           f"({int(mu_result['games'].sum())} total games)")

                # Show top 30
                top = mu_display.head(30).reset_index()
                # Truncate long opener names for display
                top["opener_a_short"] = top["opener_a"].apply(
                    lambda s: s[:60] + "..." if len(s) > 60 else s)
                top["opener_b_short"] = top["opener_b"].apply(
                    lambda s: s[:60] + "..." if len(s) > 60 else s)

                # Render as a clean table
                display_df = top[["opener_a", "opener_b", "games", "a_wins", "winrate_pct"]]
                display_df.columns = ["Your Opener", "Opponent Opener", "Games", "Wins", "Win %"]
                st.dataframe(display_df, use_container_width=True, hide_index=True)

                # Lookup view: pick a specific opener and see all its matchups
                st.markdown("---")
                st.markdown("**Lookup: pick an opener to see all its matchups**")
                all_openers = sorted(mu_result.index.get_level_values("opener_a").unique())
                if all_openers:
                    selected_op = st.selectbox(
                        "Your opener", all_openers, key="mu_lookup",
                    )
                    lookup = mu_result.loc[selected_op] if selected_op in mu_result.index.get_level_values("opener_a") else None
                    if lookup is not None and not lookup.empty:
                        lookup_display = lookup.reset_index().sort_values(
                            "winrate_pct", ascending=False)
                        lookup_display.columns = ["Opponent Opener", "Games", "Wins", "Win %"]
                        # Bar chart
                        fig_lookup = px.bar(
                            lookup_display.sort_values("Win %"),
                            x="Win %", y="Opponent Opener",
                            orientation="h",
                            color="Win %",
                            color_continuous_scale="RdYlGn",
                            range_color=[0, 100],
                            text="Games",
                            labels={"Win %": f"Your win % vs this opener", "Opponent Opener": ""},
                        )
                        fig_lookup.update_traces(texttemplate="n=%{text}", textposition="outside")
                        fig_lookup.update_layout(height=max(300, len(lookup_display) * 35))
                        st.plotly_chart(fig_lookup, use_container_width=True)
                        st.dataframe(lookup_display, use_container_width=True, hide_index=True)

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

        # =====================================================
        # BG OVERALL WINRATES
        # =====================================================
        st.subheader("Battlegroup Overall Winrates")
        bg_overall = analyze.battlegroup_overall_winrates(bo, min_games=10)
        if not bg_overall.empty:
            bg_overall_chart = bg_overall.reset_index().sort_values("winrate_pct")
            fig_bgwr = px.bar(
                bg_overall_chart,
                x="winrate_pct", y="bg",
                orientation="h",
                color="winrate_pct",
                color_continuous_scale="RdYlGn",
                range_color=[35, 65],
                text="games",
                labels={"winrate_pct": "Win Rate %", "bg": ""},
                hover_data=["wins", "games"],
            )
            fig_bgwr.update_traces(texttemplate="n=%{text}", textposition="outside")
            fig_bgwr.update_layout(height=max(400, len(bg_overall) * 30))
            st.plotly_chart(fig_bgwr, use_container_width=True)
            st.dataframe(bg_overall, use_container_width=True)

        # =====================================================
        # BG vs BG MATCHUP MATRIX
        # =====================================================
        st.subheader("Battlegroup Matchup Matrix")
        st.caption("Row picks vs column picks. Cell = row's winrate %. "
                   "Only shows matchups with at least min_games occurrences.")
        bg_min_games = st.slider("Min games per matchup", 2, 20, 3, key="bg_matchup_min")
        bg_mu = analyze.battlegroup_matchup_winrates(bo, min_games=bg_min_games)
        if not bg_mu.empty:
            # Pivot into matrix form
            matrix = bg_mu.reset_index().pivot(index="bg_a", columns="bg_b", values="winrate_pct")
            games_matrix = bg_mu.reset_index().pivot(index="bg_a", columns="bg_b", values="games")

            # Sort by overall winrate from bg_overall
            if not bg_overall.empty:
                order = bg_overall.index.tolist()
                matrix = matrix.reindex(index=[b for b in order if b in matrix.index],
                                       columns=[b for b in order if b in matrix.columns])
                games_matrix = games_matrix.reindex(index=matrix.index, columns=matrix.columns)

            fig_matrix = px.imshow(
                matrix,
                text_auto=".0f",
                color_continuous_scale="RdYlGn",
                zmin=20, zmax=80,
                labels=dict(x="Opponent picked", y="Player picked", color="Win %"),
                aspect="auto",
            )
            fig_matrix.update_layout(height=600, xaxis_tickangle=-45)
            st.plotly_chart(fig_matrix, use_container_width=True)

            with st.expander("View matchup table"):
                # Flat table view
                bg_mu_display = bg_mu.reset_index()
                bg_mu_display = bg_mu_display[bg_mu_display["games"] >= bg_min_games]
                bg_mu_display = bg_mu_display.sort_values("winrate_pct", ascending=False)
                st.dataframe(bg_mu_display, use_container_width=True, hide_index=True)
        else:
            st.info("No BG matchups meet the criteria yet (need both players to pick BGs)")

        # =====================================================
        # BG WINRATES BY MAP
        # =====================================================
        st.subheader("Battlegroup × Map Winrates")
        st.caption(
            "How does each battlegroup perform on each map? Some BGs have huge swings — "
            "Mechanized swings 39pp from Pachino (66.7%) to Twin Beach (27.3%) for example."
        )
        col_bgmap_a, col_bgmap_b = st.columns(2)
        bgmap_min_games = col_bgmap_a.slider(
            "Min games per (BG, map)", 2, 15, 3, key="bgmap_min")
        try:
            bg_by_map = analyze.bg_winrates_by_map(bo, min_games=bgmap_min_games)
            if bg_by_map.empty:
                st.info("Not enough data for current filters")
            else:
                # Two views: BG-centric (pick a BG, see all maps) and map-centric
                view_mode = col_bgmap_b.selectbox(
                    "View",
                    ["Pick a BG → see all maps", "Pick a map → see all BGs", "Best BG per map", "Full heatmap"],
                    key="bgmap_view",
                )

                if view_mode == "Pick a BG → see all maps":
                    bg_options = sorted(bg_by_map.index.get_level_values("bg").unique())
                    selected_bg = st.selectbox("Battlegroup", bg_options, key="bgmap_bg")
                    filtered = bg_by_map.xs(selected_bg, level="bg") if selected_bg else None
                    if filtered is not None and not filtered.empty:
                        chart_data = filtered.reset_index().sort_values("winrate_pct")
                        fig_bgm = px.bar(
                            chart_data,
                            x="winrate_pct", y="map_name",
                            orientation="h",
                            color="winrate_pct",
                            color_continuous_scale="RdYlGn",
                            range_color=[20, 80],
                            text="games",
                            labels={"winrate_pct": f"{selected_bg} win %", "map_name": ""},
                        )
                        fig_bgm.update_traces(texttemplate="n=%{text}", textposition="outside")
                        fig_bgm.update_layout(
                            height=max(300, len(chart_data) * 35),
                            shapes=[dict(type="line", x0=50, x1=50, y0=-0.5,
                                         y1=len(chart_data) - 0.5,
                                         line=dict(color="white", width=1, dash="dash"))],
                        )
                        st.plotly_chart(fig_bgm, use_container_width=True)
                        st.dataframe(filtered.reset_index(), use_container_width=True, hide_index=True)

                elif view_mode == "Pick a map → see all BGs":
                    map_options = sorted(bg_by_map.index.get_level_values("map_name").unique())
                    selected_map = st.selectbox("Map", map_options, key="bgmap_map")
                    filtered = bg_by_map.xs(selected_map, level="map_name") if selected_map else None
                    if filtered is not None and not filtered.empty:
                        chart_data = filtered.reset_index().sort_values("winrate_pct")
                        fig_bgm = px.bar(
                            chart_data,
                            x="winrate_pct", y="bg",
                            orientation="h",
                            color="winrate_pct",
                            color_continuous_scale="RdYlGn",
                            range_color=[20, 80],
                            text="games",
                            labels={"winrate_pct": f"Win % on {selected_map}", "bg": ""},
                        )
                        fig_bgm.update_traces(texttemplate="n=%{text}", textposition="outside")
                        fig_bgm.update_layout(
                            height=max(300, len(chart_data) * 35),
                            shapes=[dict(type="line", x0=50, x1=50, y0=-0.5,
                                         y1=len(chart_data) - 0.5,
                                         line=dict(color="white", width=1, dash="dash"))],
                        )
                        st.plotly_chart(fig_bgm, use_container_width=True)
                        st.dataframe(filtered.reset_index(), use_container_width=True, hide_index=True)

                elif view_mode == "Best BG per map":
                    best = analyze.best_bg_per_map(bo, min_games=bgmap_min_games)
                    if not best.empty:
                        fig_bg_best = px.bar(
                            best.sort_values("winrate_pct"),
                            x="winrate_pct", y="map",
                            orientation="h",
                            color="winrate_pct",
                            color_continuous_scale="RdYlGn",
                            range_color=[40, 100],
                            text="games",
                            labels={"winrate_pct": "Best BG win %", "map": ""},
                            hover_data=["best_bg", "wins", "games"],
                        )
                        fig_bg_best.update_traces(texttemplate="n=%{text}", textposition="outside")
                        fig_bg_best.update_layout(height=max(300, len(best) * 35))
                        st.plotly_chart(fig_bg_best, use_container_width=True)
                        st.dataframe(best, use_container_width=True, hide_index=True)

                else:  # Full heatmap
                    matrix = bg_by_map.reset_index().pivot(
                        index="bg", columns="map_name", values="winrate_pct")
                    fig_heat = px.imshow(
                        matrix,
                        text_auto=".0f",
                        color_continuous_scale="RdYlGn",
                        zmin=20, zmax=80,
                        labels=dict(x="Map", y="Battlegroup", color="Win %"),
                        aspect="auto",
                    )
                    fig_heat.update_layout(height=600, xaxis_tickangle=-45)
                    st.plotly_chart(fig_heat, use_container_width=True)
        except Exception as e:
            st.error(f"BG×Map analysis failed: {e}")

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
# TAB 5: Unit Compare
# =========================================================================
with tab_compare, safe_section("Unit Compare"):
    st.header("Cross-Faction Unit Comparison")
    st.caption("Compare equivalent units across factions (e.g. medium tanks)")

    if not bo.empty:
        def secs_to_mss(s):
            m, sec = divmod(int(s), 60)
            return f"{m}:{sec:02d}"

        FACTION_LABEL = {"us": "USF", "wehr": "Wehrmacht", "uk": "British", "dak": "DAK"}
        FACTION_COLOR = {"us": "#4CAF50", "wehr": "#9E9E9E", "uk": "#2196F3", "dak": "#FFC107"}

        cats = all_categories()
        cat_options = [(c, CATEGORY_LABELS.get(c, c)) for c in cats]
        cat_labels = [label for _, label in cat_options]
        chosen_label = st.selectbox("Unit category", cat_labels, index=cat_labels.index("Medium Tanks") if "Medium Tanks" in cat_labels else 0)
        chosen_cat = next(c for c, label in cat_options if label == chosen_label)

        # Timing comparison table
        st.subheader(f"{chosen_label} - Arrival Timings")
        ct = category_timing_comparison(bo, chosen_cat)

        if not ct.empty:
            ct_display = ct.copy().reset_index()
            ct_display["faction"] = ct_display["faction"].map(FACTION_LABEL)
            for col in ["median_s", "mean_s", "earliest_s", "p25_s", "p75_s"]:
                ct_display[col] = ct_display[col].apply(secs_to_mss)
            ct_display.columns = ["Faction", "Unit", "Games", "Median", "Mean", "Earliest", "25%ile", "75%ile"]
            st.dataframe(ct_display, use_container_width=True, hide_index=True)

            # "By minute X" filter
            st.subheader("Arrival by Target Time")
            target_min = st.slider("Target minute", 5, 30, 15, 1)
            arrival = category_arrival_at_minute(bo, chosen_cat, target_min)

            if not arrival.empty:
                arrival_display = arrival.reset_index().rename(columns={"index": "unit"})
                arrival_display["faction"] = arrival_display["faction"].map(FACTION_LABEL)

                # Two views: per-faction-game (fair cross-faction) vs when-built (popularity-adjusted)
                metric_choice = st.radio(
                    "Metric",
                    ["% of all faction games", "% of games where this unit was built"],
                    horizontal=True,
                )
                metric_col = "pct_of_faction_games" if "all" in metric_choice else "pct_when_built"

                fig = px.bar(
                    arrival_display.sort_values(metric_col),
                    x=metric_col, y="unit",
                    orientation="h",
                    color="faction",
                    color_discrete_map={FACTION_LABEL[k]: v for k, v in FACTION_COLOR.items()},
                    text=metric_col,
                    labels={metric_col: f"% with unit by {target_min}:00", "unit": ""},
                    hover_data=["games_built", "by_target", "faction_total_games"],
                )
                fig.update_traces(texttemplate="%{text}%", textposition="outside")
                fig.update_layout(height=max(350, len(arrival_display) * 40))
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(arrival_display, use_container_width=True, hide_index=True)

            # Distribution boxplot
            st.subheader("Timing Distribution")
            from unit_categories import UNIT_CATEGORIES
            units_in_cat = [u for u, (cat, _) in UNIT_CATEGORIES.items() if cat == chosen_cat]
            cat_data = bo[
                (bo["action_type"] == "production")
                & (bo["unit"].isin(units_in_cat))
            ].copy()
            if not cat_data.empty:
                first_arr = cat_data.groupby(["replay_id", "player_name", "unit"])["seconds"].min().reset_index()
                first_arr["minutes"] = first_arr["seconds"] / 60
                first_arr["faction"] = first_arr["unit"].map(lambda u: FACTION_LABEL[UNIT_CATEGORIES[u][1]])

                fig2 = px.box(
                    first_arr, x="unit", y="minutes",
                    color="faction",
                    color_discrete_map={FACTION_LABEL[k]: v for k, v in FACTION_COLOR.items()},
                    labels={"minutes": "First Built (min)", "unit": ""},
                )
                fig2.update_layout(xaxis_tickangle=-30, height=500)
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info(f"No data for {chosen_label} in current patch selection")
    else:
        st.warning("No build order data. Run: `python3 run.py scrape-cohdb`")


# =========================================================================
# TAB 6: Players
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

                # =====================================================
                # WINRATE BY UNIT COUNT
                # =====================================================
                st.markdown("---")
                st.markdown(f"**Winrate by Unit Count** - is {selected_player}'s winrate "
                           "exponential in how many of a given unit they make?")

                # Pull this player's most-built units as the dropdown options
                player_units = bo[
                    (bo["player_name"] == selected_player)
                    & (bo["action_type"] == "production")
                ]["unit"].value_counts()
                if not player_units.empty:
                    unit_options = player_units.head(30).index.tolist()
                    selected_unit_for_count = st.selectbox(
                        "Select unit",
                        unit_options,
                        key=f"wr_unit_count_{selected_player}",
                    )
                    if selected_unit_for_count:
                        wr_by_count = analyze.winrate_by_unit_count(
                            bo, selected_unit_for_count, player_name=selected_player
                        )
                        if not wr_by_count.empty:
                            wr_chart = wr_by_count.reset_index()
                            wr_chart.columns = ["count", "games", "wins", "winrate_pct"]

                            fig_wrc = px.bar(
                                wr_chart,
                                x="count", y="winrate_pct",
                                text="games",
                                color="winrate_pct",
                                color_continuous_scale="RdYlGn",
                                range_color=[0, 100],
                                labels={
                                    "count": f"# of {selected_unit_for_count} built",
                                    "winrate_pct": "Win %",
                                },
                            )
                            fig_wrc.update_traces(texttemplate="n=%{text}", textposition="outside")
                            fig_wrc.update_layout(yaxis=dict(range=[0, 110]))
                            st.plotly_chart(fig_wrc, use_container_width=True)
                            st.dataframe(wr_chart, use_container_width=True, hide_index=True)

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
