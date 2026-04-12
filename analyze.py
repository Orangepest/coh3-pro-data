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
        WHERE m.match_type IN ('ranked_1v1', 'automatch_1v1', 'custom_1v1')
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


def player_tiers(top_n_threshold: int = 30) -> pd.DataFrame:
    """
    Assign each player a skill tier based on their peak ELO across all factions.
    Tiers:
      S - top N players by peak ELO (default top 30)
      A - 1900-2000 ELO peak
      B - 1700-1900 ELO peak
      C - 1600-1700 ELO peak
    Returns DataFrame with columns: alias, peak_elo, tier
    """
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT p.alias, MAX(le.elo) as peak_elo
        FROM leaderboard_entries le
        JOIN players p ON le.profile_id = p.profile_id
        WHERE p.alias != ''
        GROUP BY p.alias
        ORDER BY peak_elo DESC
    """, conn)
    conn.close()
    if df.empty:
        return df

    # S = top N
    df["tier"] = "C"
    df.loc[df["peak_elo"] >= 1700, "tier"] = "B"
    df.loc[df["peak_elo"] >= 1900, "tier"] = "A"
    df.loc[df.index[:top_n_threshold], "tier"] = "S"
    return df


def faction_winrate_by_tier(df: pd.DataFrame, top_n: int = 30, tiers: pd.DataFrame | None = None) -> pd.DataFrame:
    """Faction winrate broken down by player skill tier."""
    if df.empty:
        return pd.DataFrame()

    if tiers is None:
        tiers = player_tiers(top_n_threshold=top_n)
    if tiers.empty:
        return pd.DataFrame()

    work = df.merge(
        tiers[["alias", "tier"]],
        on="alias",
        how="inner",  # only players we know the tier of
    )
    if work.empty:
        return pd.DataFrame()

    stats = work.groupby(["tier", "faction"]).agg(
        games=("result", "count"),
        wins=("result", lambda x: (x == "win").sum()),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    # Sort tiers as S > A > B > C
    tier_order = {"S": 0, "A": 1, "B": 2, "C": 3}
    stats = stats.reset_index()
    stats["_t"] = stats["tier"].map(tier_order)
    stats = stats.sort_values(["_t", "winrate_pct"], ascending=[True, False])
    return stats.drop(columns=["_t"]).set_index(["tier", "faction"])


def bg_picks_by_tier(bo: pd.DataFrame, top_n: int = 30, min_games: int = 5, tiers: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Battlegroup pick rates and winrates split by player skill tier.
    Compares what top-N players pick vs the rest.
    """
    bg = bo[bo["action_type"] == "battlegroup"].copy()
    bg = bg.dropna(subset=["won"])
    if bg.empty:
        return pd.DataFrame()

    bg = bg.sort_values("seconds")
    first_bg = bg.groupby(["replay_id", "player_name"]).agg(
        bg=("unit", "first"),
        won=("won", "first"),
    ).reset_index()

    # Attach tier via player_name == alias
    if tiers is None:
        tiers = player_tiers(top_n_threshold=top_n)
    merged = first_bg.merge(
        tiers[["alias", "tier"]].rename(columns={"alias": "player_name"}),
        on="player_name",
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame()

    stats = merged.groupby(["tier", "bg"]).agg(
        picks=("won", "count"),
        wins=("won", "sum"),
    )
    # Add pick rate per tier
    tier_totals = merged.groupby("tier").size()
    stats["pickrate_pct"] = stats.apply(
        lambda row: round(row["picks"] / tier_totals.get(row.name[0], 1) * 100, 1),
        axis=1,
    )
    stats["winrate_pct"] = (stats["wins"] / stats["picks"] * 100).round(1)
    stats = stats[stats["picks"] >= min_games]
    tier_order = {"S": 0, "A": 1, "B": 2, "C": 3}
    stats = stats.reset_index()
    stats["_t"] = stats["tier"].map(tier_order)
    stats = stats.sort_values(["_t", "pickrate_pct"], ascending=[True, False])
    return stats.drop(columns=["_t"]).set_index(["tier", "bg"])


def opener_picks_by_tier(
    bo: pd.DataFrame,
    first_n: int = 5,
    top_n: int = 30,
    min_games: int = 3,
    tiers: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Top openers per skill tier - what do top players play differently?"""
    df = bo[bo["action_type"] == "production"].copy()
    df = df.dropna(subset=["won"])
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("seconds")
    df["order"] = df.groupby(["replay_id", "player_name"]).cumcount() + 1
    first = df[df["order"] <= first_n]
    openers = first.groupby(["replay_id", "player_name"]).agg(
        opener=("unit", lambda x: " -> ".join(x)),
        won=("won", "first"),
    ).reset_index()
    openers["unit_count"] = openers["opener"].apply(lambda s: s.count(" -> ") + 1)
    openers = openers[openers["unit_count"] == first_n]

    if tiers is None:
        tiers = player_tiers(top_n_threshold=top_n)
    merged = openers.merge(
        tiers[["alias", "tier"]].rename(columns={"alias": "player_name"}),
        on="player_name",
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame()

    stats = merged.groupby(["tier", "opener"]).agg(
        games=("won", "count"),
        wins=("won", "sum"),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]
    tier_order = {"S": 0, "A": 1, "B": 2, "C": 3}
    stats = stats.reset_index()
    stats["_t"] = stats["tier"].map(tier_order)
    stats = stats.sort_values(["_t", "games"], ascending=[True, False])
    return stats.drop(columns=["_t"]).set_index(["tier", "opener"])


def winrate_by_game_length(
    df: pd.DataFrame,
    bucket_minutes: int = 5,
    min_games: int = 5,
) -> pd.DataFrame:
    """
    Bucket games by total duration and compute winrate per faction in each bucket.
    Tests hypotheses like 'Wehr wins more in long games' or 'DAK wins fast games'.

    Returns DataFrame with multiindex (length_bucket, faction) and columns:
    games, wins, winrate_pct.
    """
    if df.empty or "duration_s" not in df.columns:
        return pd.DataFrame()

    work = df.dropna(subset=["duration_s", "result", "faction"]).copy()
    if work.empty:
        return pd.DataFrame()

    # Bucket by minutes - "5-10", "10-15", etc., capped at "60+"
    work["duration_min"] = (work["duration_s"] / 60).astype(float)

    def bucket(m):
        if m >= 60:
            return "60+"
        b = int(m // bucket_minutes) * bucket_minutes
        return f"{b}-{b + bucket_minutes}"

    work["length_bucket"] = work["duration_min"].apply(bucket)

    stats = work.groupby(["length_bucket", "faction"]).agg(
        games=("result", "count"),
        wins=("result", lambda x: (x == "win").sum()),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]

    # Custom sort: numeric prefix order, "60+" last
    def sort_key(idx):
        b = idx[0]
        if b == "60+":
            return 9999
        return int(b.split("-")[0])

    sorted_idx = sorted(stats.index, key=sort_key)
    return stats.loc[sorted_idx]


def winrate_by_game_length_overall(
    df: pd.DataFrame,
    bucket_minutes: int = 5,
    min_games: int = 5,
) -> pd.DataFrame:
    """
    Game length distribution + winrate-by-length for the whole pool, regardless
    of faction. Useful for spotting "fast games favor allies" type patterns.
    """
    if df.empty:
        return pd.DataFrame()

    work = df.dropna(subset=["duration_s", "result"]).copy()
    if work.empty:
        return pd.DataFrame()

    # Need to group by match for game length, then compute who won by side
    # Use match_id since we have one row per player here
    matches = work.groupby("match_id").agg(
        duration_s=("duration_s", "first"),
    ).reset_index()
    matches["duration_min"] = matches["duration_s"] / 60

    def bucket(m):
        if m >= 60:
            return "60+"
        b = int(m // bucket_minutes) * bucket_minutes
        return f"{b}-{b + bucket_minutes}"

    matches["length_bucket"] = matches["duration_min"].apply(bucket)
    counts = matches.groupby("length_bucket").size().reset_index(name="matches")

    def sort_key(idx):
        b = idx
        if b == "60+":
            return 9999
        return int(b.split("-")[0])

    counts = counts.sort_values("length_bucket", key=lambda s: s.map(sort_key))
    counts["pct"] = (counts["matches"] / counts["matches"].sum() * 100).round(1)
    return counts


def faction_matchup_by_map(df: pd.DataFrame, min_games: int = 5) -> pd.DataFrame:
    """
    Faction-vs-faction winrates broken down by map.
    Returns DataFrame indexed by (map_name, faction_a, faction_b) with columns:
    games, a_wins, winrate_pct (winrate of faction_a vs faction_b on that map).
    """
    # Get winners and losers per match
    winners = df[df["result"] == "win"][["match_id", "map_name", "faction"]].rename(
        columns={"faction": "winner_faction"})
    losers = df[df["result"] == "loss"][["match_id", "map_name", "faction"]].rename(
        columns={"faction": "loser_faction"})
    matchups = winners.merge(losers, on=["match_id", "map_name"])
    if matchups.empty:
        return pd.DataFrame()

    # For each (map, A, B): how many times did A win against B?
    a_wins = (
        matchups.groupby(["map_name", "winner_faction", "loser_faction"])
        .size()
        .reset_index(name="a_wins")
        .rename(columns={"winner_faction": "faction_a", "loser_faction": "faction_b"})
    )
    # And how many times did B win against A (i.e. A lost to B)
    b_wins = (
        matchups.groupby(["map_name", "loser_faction", "winner_faction"])
        .size()
        .reset_index(name="b_wins")
        .rename(columns={"loser_faction": "faction_a", "winner_faction": "faction_b"})
    )

    merged = a_wins.merge(b_wins, on=["map_name", "faction_a", "faction_b"], how="outer").fillna(0)
    merged["games"] = merged["a_wins"] + merged["b_wins"]
    merged["winrate_pct"] = (merged["a_wins"] / merged["games"] * 100).round(1)
    merged = merged[merged["games"] >= min_games]
    merged["a_wins"] = merged["a_wins"].astype(int)
    merged["b_wins"] = merged["b_wins"].astype(int)
    merged["games"] = merged["games"].astype(int)
    return merged.set_index(["map_name", "faction_a", "faction_b"]).sort_values(
        "winrate_pct", ascending=False)


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
    def _safe_factions(x):
        # Drop NaN before sorting - mixing str + NaN raises TypeError
        clean = [f for f in x.dropna().unique() if isinstance(f, str)]
        return ", ".join(sorted(clean))

    player_stats = df.groupby(["profile_id", "alias"]).agg(
        total_games=("match_id", "nunique"),
        wins=("result", lambda x: (x == "win").sum()),
        avg_elo=("elo_after", lambda x: round(x.dropna().mean()) if not x.dropna().empty else 0),
        peak_elo=("elo_after", lambda x: x.dropna().max() if not x.dropna().empty else 0),
        factions_played=("faction", _safe_factions),
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


# Units that share a display name across factions get a "(FACTION)" suffix
# so they can be analyzed separately. Wehr Panzergrenadier and DAK Panzergrenadier
# are completely different units in CoH3 despite sharing the cohdb display name.
from canonical_roster import AMBIGUOUS_SHARED_NAMES


def player_slots() -> pd.DataFrame:
    """
    Recover the original player slot order from build_orders insertion order.
    The cohdb scraper inserts players in the order they appear in the timeline JSON,
    which preserves the .rec file's player slot order (slot 0, slot 1).

    Returns DataFrame with columns: replay_id, player_name, slot (0 or 1).
    """
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT replay_id, player_name, MIN(id) as first_id
        FROM build_orders
        GROUP BY replay_id, player_name
        ORDER BY replay_id, first_id
    """, conn)
    conn.close()
    if df.empty:
        return df
    df["slot"] = df.groupby("replay_id").cumcount()
    return df[["replay_id", "player_name", "slot"]]


def slot_winrates_by_map(min_games: int = 5) -> pd.DataFrame:
    """
    For each map, compute slot 0 vs slot 1 winrates. If a map has positional
    asymmetry, slot 0 will consistently win/lose more than 50%.
    """
    conn = get_conn()
    base = pd.read_sql_query("""
        SELECT bo.replay_id, bo.player_name, MIN(bo.id) as first_id,
               cr.map_name, bopr.won
        FROM build_orders bo
        JOIN cohdb_replays cr ON bo.replay_id = cr.replay_id
        LEFT JOIN build_orders_player_resolved bopr
            ON bo.replay_id = bopr.replay_id AND bo.player_name = bopr.player_name
        GROUP BY bo.replay_id, bo.player_name
    """, conn)
    conn.close()

    if base.empty:
        return pd.DataFrame()

    # CRITICAL: assign slot BEFORE dropping rows. Otherwise if one player
    # in a replay has won=NULL, dropping them flips the surviving player's
    # slot from 1 to 0, corrupting the position labels.
    base = base.sort_values(["replay_id", "first_id"])
    base["slot"] = base.groupby("replay_id").cumcount()
    base = base.dropna(subset=["won", "map_name"])

    # Only slot 0 winrate (slot 1 is just 100% - slot 0 winrate in 1v1)
    slot0 = base[base["slot"] == 0]
    stats = slot0.groupby("map_name").agg(
        games=("won", "count"),
        slot0_wins=("won", "sum"),
    )
    stats["slot0_winrate_pct"] = (stats["slot0_wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]
    return stats.sort_values("slot0_winrate_pct", ascending=False)


def load_build_orders_df(patch: str | None = None) -> pd.DataFrame:
    """Load build order data from cohdb, optionally filtered by patch.
    Joins with build_orders_player_resolved (which handles name mismatches via faction inference).

    For units in AMBIGUOUS_SHARED_NAMES (shared display name across factions),
    the unit column is rewritten as 'Name (FACTION)' so they can be analyzed
    separately.
    """
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
            cr.patch,
            cr.winner_side,
            bopr.faction as faction_short,
            bopr.side,
            bopr.won
        FROM build_orders bo
        JOIN cohdb_replays cr ON bo.replay_id = cr.replay_id
        LEFT JOIN build_orders_player_resolved bopr
            ON bo.replay_id = bopr.replay_id AND bo.player_name = bopr.player_name
    """
    params = ()
    if patch:
        query += " WHERE cr.patch = ?"
        params = (patch,)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    df["minutes"] = df["seconds"] / 60

    # Disambiguate shared unit names by appending faction
    if not df.empty:
        ambig_mask = df["unit"].isin(AMBIGUOUS_SHARED_NAMES) & df["faction_short"].notna()
        df.loc[ambig_mask, "unit"] = (
            df.loc[ambig_mask, "unit"]
            + " ("
            + df.loc[ambig_mask, "faction_short"].str.upper()
            + ")"
        )

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


def opener_winrates(
    bo: pd.DataFrame,
    first_n: int = 5,
    faction: str | None = None,
    map_name: str | None = None,
    min_games: int = 5,
) -> pd.DataFrame:
    """
    Compute winrates for each unique opening sequence (first N production units).

    Returns DataFrame with columns: opener, games, wins, winrate_pct.
    Filters out openers with fewer than min_games occurrences.
    Optionally filter by faction (us/wehr/uk/dak) and/or map_name.
    """
    df = bo[bo["action_type"] == "production"].copy()

    # Need won info to compute winrates
    df = df.dropna(subset=["won"])
    if df.empty:
        return pd.DataFrame()

    # Optional filters
    if faction:
        df = df[df["faction_short"] == faction]
    if map_name:
        df = df[df["map_name"] == map_name]
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("seconds")
    df["order"] = df.groupby(["replay_id", "player_name"]).cumcount() + 1
    first = df[df["order"] <= first_n]

    # Build opener sequence per (replay, player)
    openers = (
        first.groupby(["replay_id", "player_name"])
        .agg(
            opener=("unit", lambda x: " -> ".join(x)),
            won=("won", "first"),
        )
        .reset_index()
    )

    # Need exactly first_n units in each opener (drop short games)
    openers["unit_count"] = openers["opener"].apply(lambda s: s.count(" -> ") + 1)
    openers = openers[openers["unit_count"] == first_n]

    # Aggregate winrates
    stats = openers.groupby("opener").agg(
        games=("won", "count"),
        wins=("won", "sum"),
    )
    stats = stats[stats["games"] >= min_games]
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    return stats.sort_values(["winrate_pct", "games"], ascending=[False, False])


def key_milestone_timings(
    bo: pd.DataFrame,
    faction: str | None = None,
) -> pd.DataFrame:
    """
    Compute average timings for key build order milestones per game.
    Milestones: first infantry, first MG/HMG, first AT, first armored car,
    first medium tank, first BG pick.

    If faction is given, only games where the player played that faction.
    Returns DataFrame indexed by milestone with columns: avg_minutes,
    median_minutes, p25_minutes, p75_minutes, games.
    """
    from unit_categories import UNIT_CATEGORIES

    # Build category sets, optionally filtered by faction so we never pull
    # cross-faction units that would never match anyway.
    by_cat: dict[str, set[str]] = {}
    for unit, (cat, fac) in UNIT_CATEGORIES.items():
        if faction and fac != faction:
            continue
        by_cat.setdefault(cat, set()).add(unit)

    # Filter by faction
    df = bo[bo["action_type"] == "production"].copy()
    if faction:
        df = df[df["faction_short"] == faction]
    if df.empty:
        return pd.DataFrame()

    # For each (replay, player), find first time each category was built.
    # Skipped: "engineers" - all factions have a starting engineer/pioneer at
    # t=0, so the metric is meaningless.
    milestones = {
        "First mainline infantry": "mainline_infantry",
        "First HMG": "hmg",
        "First mortar": "mortar",
        "First AT gun": "at_gun",
        "First armored car": "armored_car",
        "First halftrack": "halftrack",
        "First light tank": "light_tank",
        "First medium tank": "medium_tank",
        "First heavy tank": "heavy_tank",
        "First tank destroyer": "tank_destroyer",
        "First artillery": "artillery",
        "First assault tank": "assault_tank",
        "First AA": "aa",
        "First elite infantry": "elite_infantry",
    }

    rows = []
    for label, cat in milestones.items():
        units_in_cat = by_cat.get(cat, set())
        if not units_in_cat:
            continue
        cat_df = df[df["unit"].isin(units_in_cat)]
        if cat_df.empty:
            continue
        # First occurrence per player-game
        first_occ = cat_df.groupby(["replay_id", "player_name"])["seconds"].min()
        if first_occ.empty:
            continue
        first_min = first_occ / 60
        rows.append({
            "milestone": label,
            "games": len(first_occ),
            "avg_min": round(first_min.mean(), 2),
            "median_min": round(first_min.median(), 2),
            "earliest_min": round(first_min.min(), 2),
            "p25_min": round(first_min.quantile(0.25), 2),
            "p75_min": round(first_min.quantile(0.75), 2),
        })

    # Add BG pick timing as a separate milestone
    bg_df = bo[bo["action_type"] == "battlegroup"]
    if faction:
        bg_df = bg_df[bg_df["faction_short"] == faction]
    if not bg_df.empty:
        first_bg = bg_df.groupby(["replay_id", "player_name"])["seconds"].min()
        first_min = first_bg / 60
        rows.append({
            "milestone": "First BG pick",
            "games": len(first_bg),
            "avg_min": round(first_min.mean(), 2),
            "median_min": round(first_min.median(), 2),
            "earliest_min": round(first_min.min(), 2),
            "p25_min": round(first_min.quantile(0.25), 2),
            "p75_min": round(first_min.quantile(0.75), 2),
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("milestone").sort_values("avg_min")


def milestone_timing_winrate_correlation(
    bo: pd.DataFrame,
    milestone_units: list[str],
    faction: str | None = None,
    bucket_minutes: int = 2,
) -> pd.DataFrame:
    """
    For a given milestone (set of units), bucket player-games by when they
    first achieved it and compute winrate per bucket.
    Tests hypotheses like 'players who get a medium tank by 12 min win more'.

    Bucket label N means the player first built the unit in [N, N+bucket_minutes) minutes.
    """
    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be positive")

    df = bo[(bo["action_type"] == "production") & (bo["unit"].isin(milestone_units))].copy()
    df = df.dropna(subset=["won"])
    if faction:
        df = df[df["faction_short"] == faction]
    if df.empty:
        return pd.DataFrame()

    first = df.groupby(["replay_id", "player_name"]).agg(
        first_seconds=("seconds", "min"),
        won=("won", "first"),
    ).reset_index()
    first["bucket_min"] = ((first["first_seconds"] // (bucket_minutes * 60)) * bucket_minutes).astype(int)

    stats = first.groupby("bucket_min").agg(
        games=("won", "count"),
        wins=("won", "sum"),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    return stats.sort_index()


def winrate_by_unit_count(
    bo: pd.DataFrame,
    unit: str,
    player_name: str | None = None,
    bucket_max: int = 6,
) -> pd.DataFrame:
    """
    For each player-game where 'player_name' (or any player if None) played,
    count how many times they built 'unit' and compute winrate per count.

    Returns DataFrame with index 'unit_count' and columns: games, wins, winrate_pct.
    Counts above bucket_max are bucketed into '{bucket_max}+'.
    """
    df = bo.dropna(subset=["won"]).copy()
    if player_name:
        df = df[df["player_name"] == player_name]
    if df.empty:
        return pd.DataFrame()

    # All player-games this player participated in
    all_games = df.groupby(["replay_id", "player_name"])["won"].first().reset_index()

    # How many of this unit each player built per game
    unit_df = df[(df["unit"] == unit) & (df["action_type"] == "production")]
    counts = (
        unit_df.groupby(["replay_id", "player_name"])
        .size()
        .reset_index(name="unit_count")
    )

    # Merge: any game where the player didn't build the unit gets count=0
    merged = all_games.merge(counts, on=["replay_id", "player_name"], how="left")
    merged["unit_count"] = merged["unit_count"].fillna(0).astype(int)

    # Bucket
    merged["bucket"] = merged["unit_count"].apply(
        lambda x: f"{bucket_max}+" if x >= bucket_max else str(x)
    )

    # Aggregate
    stats = merged.groupby("bucket").agg(
        games=("won", "count"),
        wins=("won", "sum"),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)

    # Sort by numeric bucket value
    def sort_key(b):
        return bucket_max + 1 if b == f"{bucket_max}+" else int(b)
    stats = stats.reindex(sorted(stats.index, key=sort_key))
    return stats


def opener_matchup_winrates(
    bo: pd.DataFrame,
    first_n: int = 5,
    faction_a: str | None = None,
    faction_b: str | None = None,
    min_games: int = 3,
) -> pd.DataFrame:
    """
    Compute opener vs opener winrates.
    Returns DataFrame with: opener_a, opener_b, games, a_wins, winrate_pct.

    Optionally filter by faction_a (player whose winrate is computed) and
    faction_b (opponent).
    """
    df = bo[bo["action_type"] == "production"].copy()
    df = df.dropna(subset=["won"])
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("seconds")
    df["order"] = df.groupby(["replay_id", "player_name"]).cumcount() + 1
    first = df[df["order"] <= first_n]

    # Build (opener, won, faction) per (replay, player)
    openers = first.groupby(["replay_id", "player_name"]).agg(
        opener=("unit", lambda x: " -> ".join(x)),
        won=("won", "first"),
        faction=("faction_short", "first"),
    ).reset_index()

    # Drop short games
    openers["unit_count"] = openers["opener"].apply(lambda s: s.count(" -> ") + 1)
    openers = openers[openers["unit_count"] == first_n]

    # Need both players per replay
    counts = openers.groupby("replay_id").size()
    valid = counts[counts == 2].index
    openers = openers[openers["replay_id"].isin(valid)]

    # Pair them up by replay
    rows = []
    for rid, group in openers.groupby("replay_id"):
        if len(group) != 2:
            continue
        p1, p2 = group.iloc[0], group.iloc[1]
        rows.append({
            "opener_a": p1["opener"], "faction_a": p1["faction"],
            "opener_b": p2["opener"], "faction_b": p2["faction"],
            "a_won": int(p1["won"]),
        })
        rows.append({
            "opener_a": p2["opener"], "faction_a": p2["faction"],
            "opener_b": p1["opener"], "faction_b": p1["faction"],
            "a_won": int(p2["won"]),
        })

    if not rows:
        return pd.DataFrame()

    matchup_df = pd.DataFrame(rows)
    if faction_a:
        matchup_df = matchup_df[matchup_df["faction_a"] == faction_a]
    if faction_b:
        matchup_df = matchup_df[matchup_df["faction_b"] == faction_b]
    if matchup_df.empty:
        return pd.DataFrame()

    stats = matchup_df.groupby(["opener_a", "opener_b"]).agg(
        games=("a_won", "count"),
        a_wins=("a_won", "sum"),
    )
    stats["winrate_pct"] = (stats["a_wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]
    return stats.sort_values(["winrate_pct", "games"], ascending=[False, False])


def list_openers_for_faction(
    bo: pd.DataFrame,
    faction: str,
    first_n: int = 4,
    min_games: int = 5,
) -> pd.DataFrame:
    """List all distinct openers a faction plays, ranked by frequency.

    Used to power the "pick an opener" dropdown in the counter-analysis UI.
    """
    df = bo[(bo["action_type"] == "production") & (bo["faction_short"] == faction)].copy()
    if df.empty:
        return pd.DataFrame()
    df = df.sort_values("seconds")
    df["order"] = df.groupby(["replay_id", "player_name"]).cumcount() + 1
    first = df[df["order"] <= first_n]
    openers = first.groupby(["replay_id", "player_name"]).agg(
        opener=("unit", lambda x: " -> ".join(x)),
    ).reset_index()
    openers["unit_count"] = openers["opener"].apply(lambda s: s.count(" -> ") + 1)
    openers = openers[openers["unit_count"] == first_n]
    counts = openers["opener"].value_counts().reset_index()
    counts.columns = ["opener", "games"]
    return counts[counts["games"] >= min_games]


def counter_openers(
    bo: pd.DataFrame,
    target_faction: str,
    target_opener: str,
    first_n: int = 4,
    min_games: int = 3,
) -> pd.DataFrame:
    """For a given (faction, opener), find which opposing-faction openers
    BEAT it most often. Returns one row per (counter_faction, counter_opener)
    with games + the *counter's* winrate against the target.
    """
    df = bo[bo["action_type"] == "production"].copy()
    df = df.dropna(subset=["won"])
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("seconds")
    df["order"] = df.groupby(["replay_id", "player_name"]).cumcount() + 1
    first = df[df["order"] <= first_n]

    openers = first.groupby(["replay_id", "player_name"]).agg(
        opener=("unit", lambda x: " -> ".join(x)),
        won=("won", "first"),
        faction=("faction_short", "first"),
    ).reset_index()
    openers["unit_count"] = openers["opener"].apply(lambda s: s.count(" -> ") + 1)
    openers = openers[openers["unit_count"] == first_n]

    # Need both players per replay
    counts = openers.groupby("replay_id").size()
    valid = counts[counts == 2].index
    openers = openers[openers["replay_id"].isin(valid)]

    rows = []
    for rid, group in openers.groupby("replay_id"):
        if len(group) != 2:
            continue
        p1, p2 = group.iloc[0], group.iloc[1]
        # Was either side the target opener?
        if p1["faction"] == target_faction and p1["opener"] == target_opener:
            rows.append({
                "counter_faction": p2["faction"],
                "counter_opener": p2["opener"],
                "counter_won": int(p2["won"]),
            })
        if p2["faction"] == target_faction and p2["opener"] == target_opener:
            rows.append({
                "counter_faction": p1["faction"],
                "counter_opener": p1["opener"],
                "counter_won": int(p1["won"]),
            })

    if not rows:
        return pd.DataFrame()

    cdf = pd.DataFrame(rows)
    stats = cdf.groupby(["counter_faction", "counter_opener"]).agg(
        games=("counter_won", "count"),
        wins=("counter_won", "sum"),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]
    return stats.sort_values(["winrate_pct", "games"], ascending=[False, False])


def battlegroup_matchup_winrates(
    bo: pd.DataFrame,
    min_games: int = 3,
) -> pd.DataFrame:
    """
    Compute BG vs BG winrates from build orders.
    Returns DataFrame with: bg_a, bg_b, games, a_wins, winrate_pct (winrate of bg_a vs bg_b).

    Only includes replays where BOTH players picked a battlegroup.
    """
    bg = bo[bo["action_type"] == "battlegroup"].copy()
    bg = bg.dropna(subset=["won"])
    if bg.empty:
        return pd.DataFrame()

    # Take only the FIRST BG pick per player per game
    bg = bg.sort_values("seconds")
    first_bg = bg.groupby(["replay_id", "player_name"]).agg(
        bg=("unit", "first"),
        won=("won", "first"),
    ).reset_index()

    # Need both players' BGs for each replay
    counts = first_bg.groupby("replay_id").size()
    valid_replays = counts[counts == 2].index
    first_bg = first_bg[first_bg["replay_id"].isin(valid_replays)]

    # Build matchups: for each replay, pair the two players
    rows = []
    for rid, group in first_bg.groupby("replay_id"):
        if len(group) != 2:
            continue
        p1, p2 = group.iloc[0], group.iloc[1]
        # Each side reported once - we'll compute symmetric A vs B and B vs A
        rows.append({"bg_a": p1["bg"], "bg_b": p2["bg"], "a_won": int(p1["won"])})
        rows.append({"bg_a": p2["bg"], "bg_b": p1["bg"], "a_won": int(p2["won"])})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    stats = df.groupby(["bg_a", "bg_b"]).agg(
        games=("a_won", "count"),
        a_wins=("a_won", "sum"),
    )
    stats["winrate_pct"] = (stats["a_wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]
    return stats.sort_values(["winrate_pct"], ascending=False)


def bg_winrates_by_map(bo: pd.DataFrame, min_games: int = 3) -> pd.DataFrame:
    """
    Battlegroup winrates broken down by map.
    Returns DataFrame with multiindex (map, bg) and columns: games, wins, winrate_pct.
    """
    bg = bo[bo["action_type"] == "battlegroup"].copy()
    bg = bg.dropna(subset=["won", "map_name"])
    if bg.empty:
        return pd.DataFrame()

    # Take first BG pick per player per game
    bg = bg.sort_values("seconds")
    first_bg = bg.groupby(["replay_id", "player_name"]).agg(
        bg=("unit", "first"),
        won=("won", "first"),
        map_name=("map_name", "first"),
    ).reset_index()

    stats = first_bg.groupby(["map_name", "bg"]).agg(
        games=("won", "count"),
        wins=("won", "sum"),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]
    return stats.sort_values("winrate_pct", ascending=False)


def best_bg_per_map(bo: pd.DataFrame, min_games: int = 3) -> pd.DataFrame:
    """For each map, the highest-winrate battlegroup."""
    by_map = bg_winrates_by_map(bo, min_games=min_games)
    if by_map.empty:
        return pd.DataFrame()
    rows = []
    for map_name, group in by_map.groupby(level="map_name"):
        best = group.iloc[0]  # already sorted by winrate desc
        rows.append({
            "map": map_name,
            "best_bg": group.index[0][1],  # bg name from multiindex
            "winrate_pct": best["winrate_pct"],
            "wins": int(best["wins"]),
            "games": int(best["games"]),
        })
    return pd.DataFrame(rows).sort_values("winrate_pct", ascending=False)


def battlegroup_overall_winrates(bo: pd.DataFrame, min_games: int = 5) -> pd.DataFrame:
    """Overall winrate per battlegroup (regardless of opponent)."""
    bg = bo[bo["action_type"] == "battlegroup"].copy()
    bg = bg.dropna(subset=["won"])
    if bg.empty:
        return pd.DataFrame()

    bg = bg.sort_values("seconds")
    first_bg = bg.groupby(["replay_id", "player_name"]).agg(
        bg=("unit", "first"),
        won=("won", "first"),
    ).reset_index()

    stats = first_bg.groupby("bg").agg(
        games=("won", "count"),
        wins=("won", "sum"),
    )
    stats["winrate_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats = stats[stats["games"] >= min_games]
    return stats.sort_values("winrate_pct", ascending=False)


def opener_winrates_by_map(
    bo: pd.DataFrame,
    first_n: int = 5,
    faction: str | None = None,
    min_games: int = 3,
) -> pd.DataFrame:
    """
    Compute opener winrates broken down by map.
    Returns multi-index (map, opener) with games/wins/winrate_pct.
    """
    maps = bo["map_name"].dropna().unique()
    results = []
    for m in maps:
        wr = opener_winrates(bo, first_n=first_n, faction=faction,
                              map_name=m, min_games=min_games)
        if not wr.empty:
            wr = wr.copy()
            wr["map_name"] = m
            results.append(wr)
    if not results:
        return pd.DataFrame()
    combined = pd.concat(results)
    combined = combined.set_index("map_name", append=True).reorder_levels(["map_name", "opener"])
    return combined.sort_values(["winrate_pct"], ascending=False)


def category_timing_comparison(bo: pd.DataFrame, category: str) -> pd.DataFrame:
    """
    Compare arrival timings for all units in a given category across factions.
    Returns one row per unit with timing distribution stats.
    """
    from unit_categories import UNIT_CATEGORIES

    units_in_cat = [u for u, (cat, _) in UNIT_CATEGORIES.items() if cat == category]
    if not units_in_cat:
        return pd.DataFrame()

    cat_bo = bo[
        (bo["action_type"] == "production")
        & (bo["unit"].isin(units_in_cat))
    ].copy()
    if cat_bo.empty:
        return pd.DataFrame()

    cat_bo["faction"] = cat_bo["unit"].map(lambda u: UNIT_CATEGORIES.get(u, (None, None))[1])

    # First arrival per (replay, player, unit)
    first = cat_bo.groupby(["replay_id", "player_name", "unit", "faction"])["seconds"].min().reset_index()
    first["minutes"] = first["seconds"] / 60

    # Aggregate per unit
    stats = first.groupby(["faction", "unit"]).agg(
        games=("seconds", "count"),
        median_s=("seconds", "median"),
        mean_s=("seconds", "mean"),
        earliest_s=("seconds", "min"),
        p25_s=("seconds", lambda x: x.quantile(0.25)),
        p75_s=("seconds", lambda x: x.quantile(0.75)),
    ).round(0)
    return stats.sort_values("median_s")


def category_arrival_at_minute(bo: pd.DataFrame, category: str, target_minute: float) -> pd.DataFrame:
    """
    For each unit in a category, how often does it arrive by target_minute?
    Returns BOTH:
      - pct_when_built: % of games this unit was built that it arrived by target (conditional)
      - pct_per_faction_game: % of all faction-games where it arrived by target (unconditional)
    Use pct_per_faction_game to fairly compare units across factions.
    """
    from unit_categories import UNIT_CATEGORIES

    units_in_cat = [u for u, (cat, _) in UNIT_CATEGORIES.items() if cat == category]
    if not units_in_cat:
        return pd.DataFrame()

    target_s = target_minute * 60

    # First arrival of any unit-in-category per player-game
    cat_bo = bo[
        (bo["action_type"] == "production")
        & (bo["unit"].isin(units_in_cat))
    ].copy()

    first = cat_bo.groupby(["replay_id", "player_name", "unit"])["seconds"].min().reset_index()

    # Compute per-faction game totals (denominator for unconditional %)
    # We need to know how many games each faction played - we infer it from build_orders
    # by looking at how many distinct (replay_id, player_name) pairs have ANY production
    # of a unit known to belong to that faction.
    all_prod = bo[bo["action_type"] == "production"].copy()
    all_prod["faction"] = all_prod["unit"].map(lambda u: UNIT_CATEGORIES.get(u, (None, None))[1])
    faction_games = (
        all_prod.dropna(subset=["faction"])
        .groupby("faction")[["replay_id", "player_name"]]
        .apply(lambda x: x.drop_duplicates().shape[0])
    )

    # Per-unit stats
    total_built = first.groupby("unit").size()
    in_time = first[first["seconds"] <= target_s].groupby("unit").size()

    result = pd.DataFrame({
        "games_built": total_built,
        "by_target": in_time.reindex(total_built.index, fill_value=0),
    })
    result["faction"] = result.index.map(lambda u: UNIT_CATEGORIES.get(u, (None, None))[1])

    # Conditional %: of games where unit was built, how many by target
    result["pct_when_built"] = (result["by_target"] / result["games_built"] * 100).round(1)

    # Unconditional %: of all games for that faction, how many had this unit by target
    result["faction_total_games"] = result["faction"].map(faction_games).fillna(0).astype(int)
    result["pct_of_faction_games"] = (
        result["by_target"] / result["faction_total_games"].replace(0, pd.NA) * 100
    ).round(1).fillna(0)

    return result.sort_values("pct_of_faction_games", ascending=False)


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
