"""
Analysis module for CoH3 1v1 pro scene data.

Run directly for a full report, or import individual functions.
"""

import pandas as pd
from datetime import datetime, timezone
from db import get_conn
from config import MIN_ELO


def load_matches_df() -> pd.DataFrame:
    """Load all match data as a denormalized DataFrame."""
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT
            m.match_id,
            m.map_name,
            m.match_type,
            m.start_time,
            m.duration_s,
            mp.profile_id,
            mp.faction,
            mp.elo_before,
            mp.elo_after,
            mp.elo_diff,
            mp.result,
            p.alias,
            p.country
        FROM matches m
        JOIN match_players mp ON m.match_id = mp.match_id
        LEFT JOIN players p ON mp.profile_id = p.profile_id
        WHERE m.match_type = 'ranked_1v1'
    """, conn)
    conn.close()

    if not df.empty and "start_time" in df.columns:
        df["date"] = pd.to_datetime(df["start_time"], unit="s", utc=True, errors="coerce")
        df["month"] = df["date"].dt.to_period("M")
    return df


def load_leaderboard_df() -> pd.DataFrame:
    """Load leaderboard data."""
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT le.*, p.alias, p.country
        FROM leaderboard_entries le
        JOIN players p ON le.profile_id = p.profile_id
        WHERE le.elo >= ?
        ORDER BY le.elo DESC
    """, conn, params=(MIN_ELO,))
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def faction_winrates(df: pd.DataFrame) -> pd.DataFrame:
    """Overall win rate per faction at pro level."""
    wins = df[df["result"] == "win"].groupby("faction").size().reindex(
        df["faction"].unique(), fill_value=0
    )
    total = df.groupby("faction").size()
    wr = (wins / total * 100).round(1)
    out = pd.DataFrame({"wins": wins, "total_games": total, "winrate_pct": wr})
    return out.sort_values("winrate_pct", ascending=False)


def faction_matchup_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Win rate matrix: rows = winner faction, cols = loser faction."""
    winners = df[df["result"] == "win"][["match_id", "faction"]].rename(columns={"faction": "winner_faction"})
    losers = df[df["result"] == "loss"][["match_id", "faction"]].rename(columns={"faction": "loser_faction"})
    matchups = winners.merge(losers, on="match_id")

    pivot = matchups.groupby(["winner_faction", "loser_faction"]).size().unstack(fill_value=0)

    # Convert to win rate percentage
    totals = pivot + pivot.T
    wr_matrix = (pivot / totals * 100).round(1)
    return wr_matrix


def map_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Per-map statistics: total matches, avg duration, faction win rates."""
    matches_only = df.drop_duplicates(subset="match_id")
    map_counts = matches_only.groupby("map_name").agg(
        total_matches=("match_id", "count"),
        avg_duration_min=("duration_s", lambda x: round(x.dropna().mean() / 60, 1)),
        median_duration_min=("duration_s", lambda x: round(x.dropna().median() / 60, 1)),
    ).sort_values("total_matches", ascending=False)

    return map_counts


def map_faction_winrates(df: pd.DataFrame) -> pd.DataFrame:
    """Faction win rates broken down by map."""
    wins = df[df["result"] == "win"].groupby(["map_name", "faction"]).size()
    total = df.groupby(["map_name", "faction"]).size()
    wr = (wins.reindex(total.index, fill_value=0) / total * 100).round(1)
    return wr.unstack(fill_value=0)


def duration_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Match duration distribution in 5-minute buckets."""
    matches = df.drop_duplicates(subset="match_id").dropna(subset=["duration_s"])
    matches = matches.copy()
    matches["duration_min"] = matches["duration_s"] / 60
    matches["bucket"] = pd.cut(
        matches["duration_min"],
        bins=[0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 120],
        labels=["0-5", "5-10", "10-15", "15-20", "20-25", "25-30", "30-40", "40-50", "50-60", "60+"],
    )
    dist = matches["bucket"].value_counts().sort_index()
    pct = (dist / dist.sum() * 100).round(1)
    return pd.DataFrame({"matches": dist, "pct": pct})


def top_players(df: pd.DataFrame, n: int = 30) -> pd.DataFrame:
    """Top players by number of pro-level matches played."""
    player_stats = df.groupby(["profile_id", "alias"]).agg(
        total_games=("match_id", "nunique"),
        wins=("result", lambda x: (x == "win").sum()),
        avg_elo=("elo_after", lambda x: round(x.dropna().mean())),
        peak_elo=("elo_after", lambda x: x.dropna().max() if not x.dropna().empty else None),
        factions_played=("faction", lambda x: ", ".join(sorted(x.unique()))),
    )
    player_stats["winrate_pct"] = (player_stats["wins"] / player_stats["total_games"] * 100).round(1)
    return player_stats.sort_values("total_games", ascending=False).head(n)


def head_to_head(df: pd.DataFrame, player1_alias: str, player2_alias: str) -> pd.DataFrame:
    """Head-to-head record between two players."""
    p1_matches = set(df[df["alias"] == player1_alias]["match_id"])
    p2_matches = set(df[df["alias"] == player2_alias]["match_id"])
    shared = p1_matches & p2_matches

    if not shared:
        print(f"No shared matches between {player1_alias} and {player2_alias}")
        return pd.DataFrame()

    shared_df = df[df["match_id"].isin(shared)]

    p1_results = shared_df[shared_df["alias"] == player1_alias][["match_id", "faction", "result", "elo_after"]]
    p2_results = shared_df[shared_df["alias"] == player2_alias][["match_id", "faction", "result", "elo_after"]]

    merged = p1_results.merge(
        p2_results, on="match_id", suffixes=(f"_{player1_alias}", f"_{player2_alias}")
    )
    return merged


def load_build_orders_df(patch: str | None = None) -> pd.DataFrame:
    """Load build order data from cohdb, optionally filtered by patch."""
    conn = get_conn()
    query = """
        SELECT
            bo.replay_id,
            bo.player_name,
            bo.seconds,
            bo.unit,
            bo.action_type,
            cr.duration_s as match_duration_s,
            cr.map_name,
            cr.patch
        FROM build_orders bo
        JOIN cohdb_replays cr ON bo.replay_id = cr.replay_id
    """
    params = ()
    if patch:
        query += " WHERE cr.patch = ?"
        params = (patch,)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    df["minutes"] = df["seconds"] / 60
    return df


def available_patches() -> pd.DataFrame:
    """List all patches in the database with game counts."""
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT patch, COUNT(*) as games
        FROM cohdb_replays
        WHERE patch IS NOT NULL
        GROUP BY patch
        ORDER BY patch DESC
    """, conn)
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Build Order Analysis
# ---------------------------------------------------------------------------

def opener_analysis(bo: pd.DataFrame, first_n: int = 5) -> pd.DataFrame:
    """
    Most common opening build orders (first N production actions).
    Groups by the sequence of first N units produced.
    """
    prod = bo[bo["action_type"] == "production"].copy()
    prod = prod.sort_values("seconds")
    prod["order"] = prod.groupby(["replay_id", "player_name"]).cumcount() + 1
    first = prod[prod["order"] <= first_n]

    openers = first.groupby(["replay_id", "player_name"])["unit"].apply(
        lambda x: " -> ".join(x)
    ).reset_index()
    openers.columns = ["replay_id", "player_name", "opener"]

    total_players = len(openers)
    counts = openers["opener"].value_counts().head(25)
    return pd.DataFrame({"count": counts, "pct": (counts / total_players * 100).round(1)})


def battlegroup_pickrates(bo: pd.DataFrame) -> pd.DataFrame:
    """Which battlegroups are picked and how often."""
    bg = bo[bo["action_type"] == "battlegroup"]
    counts = bg["unit"].value_counts()
    pct = (counts / counts.sum() * 100).round(1)
    avg_time = bg.groupby("unit")["seconds"].mean().round(0)
    return pd.DataFrame({
        "picks": counts,
        "pickrate_pct": pct,
        "avg_pick_time_s": avg_time,
    }).sort_values("picks", ascending=False)


def tech_timings(bo: pd.DataFrame) -> pd.DataFrame:
    """Average timing for key tech/building milestones."""
    tech = bo[bo["action_type"] == "tech"]
    stats = tech.groupby("unit").agg(
        count=("seconds", "count"),
        avg_seconds=("seconds", "mean"),
        median_seconds=("seconds", "median"),
        earliest=("seconds", "min"),
        latest=("seconds", "max"),
    ).round(0)
    stats = stats[stats["count"] >= 3]  # filter noise
    return stats.sort_values("avg_seconds")


def unit_popularity(bo: pd.DataFrame) -> pd.DataFrame:
    """Most produced units and their average production time."""
    prod = bo[bo["action_type"] == "production"]
    stats = prod.groupby("unit").agg(
        times_built=("seconds", "count"),
        avg_time_s=("seconds", "mean"),
        median_time_s=("seconds", "median"),
        first_seen_s=("seconds", "min"),
    ).round(0)
    stats["build_rate_pct"] = (
        stats["times_built"] / bo["replay_id"].nunique() * 100
    ).round(1)
    return stats.sort_values("times_built", ascending=False)


def first_unit_timing(bo: pd.DataFrame, unit_name: str) -> pd.DataFrame:
    """When a specific unit is first built across all games."""
    prod = bo[(bo["action_type"] == "production") & (bo["unit"] == unit_name)]
    first = prod.groupby(["replay_id", "player_name"])["seconds"].min().reset_index()
    first.columns = ["replay_id", "player_name", "first_built_s"]
    first["first_built_min"] = (first["first_built_s"] / 60).round(1)
    return first


def player_build_tendencies(bo: pd.DataFrame, player_name: str) -> dict:
    """Analyze a specific player's build tendencies."""
    player = bo[bo["player_name"] == player_name]
    if player.empty:
        return {"error": f"No data for player '{player_name}'"}

    games = player["replay_id"].nunique()
    return {
        "total_games": games,
        "favorite_openers": opener_analysis(player, 5).head(5),
        "battlegroups": player[player["action_type"] == "battlegroup"]["unit"].value_counts(),
        "avg_actions_per_game": round(len(player) / games, 1),
        "most_built_units": player[player["action_type"] == "production"]["unit"].value_counts().head(10),
    }


def meta_trends(df: pd.DataFrame) -> pd.DataFrame:
    """Faction pick rates and win rates over time (monthly)."""
    if "month" not in df.columns:
        return pd.DataFrame()

    monthly = df.groupby(["month", "faction"]).agg(
        games=("match_id", "count"),
        wins=("result", lambda x: (x == "win").sum()),
    )
    monthly["winrate_pct"] = (monthly["wins"] / monthly["games"] * 100).round(1)

    # Pick rate per month
    month_totals = df.groupby("month")["match_id"].count()
    monthly["pickrate_pct"] = monthly.apply(
        lambda row: round(row["games"] / month_totals.get(row.name[0], 1) * 100, 1),
        axis=1,
    )
    return monthly


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------

def full_report(patch: str | None = None):
    """Print a comprehensive analysis report, optionally filtered by patch."""
    from tabulate import tabulate

    # Show available patches
    patches = available_patches()
    if not patches.empty:
        print("Available patches:")
        print(tabulate(patches, headers="keys", tablefmt="simple", showindex=False))
        print()

    if patch:
        print(f"*** Filtering build order data to patch {patch} ***\n")

    print("Loading data...")
    df = load_matches_df()
    lb = load_leaderboard_df()

    if df.empty:
        print("No match data found. Run the scrapers first.")
        return

    unique_matches = df["match_id"].nunique()
    unique_players = df["profile_id"].nunique()
    print(f"\nDataset: {unique_matches} matches, {unique_players} players\n")

    # --- Leaderboard summary ---
    if not lb.empty:
        print("=" * 60)
        print("LEADERBOARD SUMMARY (1v1, ELO >= {})".format(MIN_ELO))
        print("=" * 60)
        lb_summary = lb.groupby("faction").agg(
            players=("profile_id", "nunique"),
            avg_elo=("elo", "mean"),
            max_elo=("elo", "max"),
        ).round(0)
        print(tabulate(lb_summary, headers="keys", tablefmt="simple"))
        print()

    # --- Faction win rates ---
    print("=" * 60)
    print("FACTION WIN RATES (1v1 Pro)")
    print("=" * 60)
    wr = faction_winrates(df)
    print(tabulate(wr, headers="keys", tablefmt="simple"))
    print()

    # --- Matchup matrix ---
    print("=" * 60)
    print("FACTION MATCHUP MATRIX (row = winner, col = loser, value = win%)")
    print("=" * 60)
    matrix = faction_matchup_matrix(df)
    print(tabulate(matrix, headers="keys", tablefmt="simple"))
    print()

    # --- Map stats ---
    print("=" * 60)
    print("MAP STATISTICS")
    print("=" * 60)
    ms = map_stats(df)
    print(tabulate(ms, headers="keys", tablefmt="simple"))
    print()

    # --- Map faction win rates ---
    print("=" * 60)
    print("MAP FACTION WIN RATES (%)")
    print("=" * 60)
    mf = map_faction_winrates(df)
    if not mf.empty:
        print(tabulate(mf, headers="keys", tablefmt="simple"))
    print()

    # --- Duration distribution ---
    print("=" * 60)
    print("MATCH DURATION DISTRIBUTION")
    print("=" * 60)
    dd = duration_distribution(df)
    print(tabulate(dd, headers="keys", tablefmt="simple"))
    print()

    # --- Top players ---
    print("=" * 60)
    print("TOP 30 PLAYERS BY GAMES PLAYED")
    print("=" * 60)
    tp = top_players(df, 30)
    print(tabulate(tp, headers="keys", tablefmt="simple"))
    print()

    # --- Meta trends ---
    print("=" * 60)
    print("MONTHLY META TRENDS (faction pick rate & win rate)")
    print("=" * 60)
    mt = meta_trends(df)
    if not mt.empty:
        print(tabulate(mt, headers="keys", tablefmt="simple"))
    print()

    # --- Build Order Analysis (from cohdb) ---
    bo = load_build_orders_df(patch=patch)
    if not bo.empty:
        bo_games = bo["replay_id"].nunique()
        print("=" * 60)
        print(f"BUILD ORDER DATA ({bo_games} games from cohdb)")
        print("=" * 60)
        print()

        print("-" * 40)
        print("TOP 25 OPENING BUILD ORDERS (first 5 units)")
        print("-" * 40)
        op = opener_analysis(bo, 5)
        print(tabulate(op, headers="keys", tablefmt="simple"))
        print()

        print("-" * 40)
        print("BATTLEGROUP PICK RATES")
        print("-" * 40)
        bg = battlegroup_pickrates(bo)
        print(tabulate(bg, headers="keys", tablefmt="simple"))
        print()

        print("-" * 40)
        print("TECH TIMINGS (avg seconds)")
        print("-" * 40)
        tt = tech_timings(bo)
        print(tabulate(tt, headers="keys", tablefmt="simple"))
        print()

        print("-" * 40)
        print("MOST PRODUCED UNITS")
        print("-" * 40)
        up = unit_popularity(bo).head(30)
        print(tabulate(up, headers="keys", tablefmt="simple"))
        print()
    else:
        print("\nNo build order data. Run: python scrape_cohdb.py")


if __name__ == "__main__":
    import sys
    patch_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith("--patch="):
            patch_arg = arg.split("=", 1)[1]
    full_report(patch=patch_arg)
