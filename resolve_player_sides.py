"""
Resolve every build_orders player to a side (allies/axis) and won (1/0)
by matching faction (inferred from their built units) to cohdb_replay_players.

This fixes the 5.6% gap from name mismatches between Steam in-game names
and cohdb listing display names.

Outputs: a new table `build_orders_player_resolved` with one row per
(replay_id, player_name) → (faction, side, won).
"""

import re
from db import get_conn, init_db
from canonical_roster import CANONICAL_BASE


# Build a unit_name -> faction map from canonical roster
UNIT_TO_FACTION = {}
for fac, tiers in CANONICAL_BASE.items():
    for tier_units in tiers.values():
        for u in tier_units:
            UNIT_TO_FACTION[u["name"]] = fac


# Map our short faction codes to cohdb side
FACTION_TO_SIDE = {
    "us": "allies",
    "uk": "allies",
    "wehr": "axis",
    "dak": "axis",
}

# Map our codes to cohdb faction slugs
FACTION_TO_SLUGS = {
    "us": ["americans"],
    "uk": ["british", "british_africa"],
    "wehr": ["germans"],
    "dak": ["afrika_korps"],
}


def infer_faction(units: list[str]) -> str | None:
    """Given a list of units a player built, return their most likely faction."""
    counts = {"us": 0, "wehr": 0, "uk": 0, "dak": 0}
    for u in units:
        f = UNIT_TO_FACTION.get(u)
        if f:
            counts[f] += 1
    if all(c == 0 for c in counts.values()):
        return None
    return max(counts, key=counts.get)


def init_resolved_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS build_orders_player_resolved (
            replay_id    INTEGER NOT NULL,
            player_name  TEXT NOT NULL,
            faction      TEXT,
            side         TEXT,
            won          INTEGER,
            resolved_via TEXT,  -- 'name_match' or 'faction_inference' or 'unresolved'
            PRIMARY KEY (replay_id, player_name)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bopr_replay ON build_orders_player_resolved(replay_id)"
    )


def resolve_all():
    init_db()
    conn = get_conn()
    init_resolved_table(conn)

    # Wipe and rebuild from scratch
    conn.execute("DELETE FROM build_orders_player_resolved")

    # Get every (replay_id, player_name) in build_orders that has a winner_side known
    pairs = conn.execute("""
        SELECT DISTINCT bo.replay_id, bo.player_name
        FROM build_orders bo
        JOIN cohdb_replays cr ON bo.replay_id = cr.replay_id
        WHERE cr.winner_side IS NOT NULL
    """).fetchall()

    print(f"Resolving {len(pairs)} player-game pairs...")

    name_match = 0
    faction_inferred = 0
    unresolved = 0

    for row in pairs:
        rid = row["replay_id"]
        pname = row["player_name"]

        # 1. Try direct name match against cohdb_replay_players
        crp = conn.execute("""
            SELECT faction_slug, side, won FROM cohdb_replay_players
            WHERE replay_id = ? AND player_name = ?
        """, (rid, pname)).fetchone()

        if crp:
            # Map cohdb faction_slug back to our short code
            slug = crp["faction_slug"]
            faction_short = next(
                (k for k, v in FACTION_TO_SLUGS.items() if slug in v),
                None,
            )
            conn.execute("""
                INSERT INTO build_orders_player_resolved
                    (replay_id, player_name, faction, side, won, resolved_via)
                VALUES (?, ?, ?, ?, ?, 'name_match')
            """, (rid, pname, faction_short, crp["side"], crp["won"]))
            name_match += 1
            continue

        # 2. Fallback: infer faction from this player's units
        units = [r["unit"] for r in conn.execute("""
            SELECT unit FROM build_orders
            WHERE replay_id = ? AND player_name = ? AND action_type = 'production'
        """, (rid, pname))]

        faction = infer_faction(units)
        if not faction:
            conn.execute("""
                INSERT INTO build_orders_player_resolved
                    (replay_id, player_name, resolved_via)
                VALUES (?, ?, 'unresolved')
            """, (rid, pname))
            unresolved += 1
            continue

        side = FACTION_TO_SIDE[faction]
        # Get winner side from replay
        winner = conn.execute(
            "SELECT winner_side FROM cohdb_replays WHERE replay_id = ?", (rid,)
        ).fetchone()["winner_side"]
        won = 1 if side == winner else 0

        conn.execute("""
            INSERT INTO build_orders_player_resolved
                (replay_id, player_name, faction, side, won, resolved_via)
            VALUES (?, ?, ?, ?, ?, 'faction_inference')
        """, (rid, pname, faction, side, won))
        faction_inferred += 1

    conn.commit()
    print(f"\nResolved {len(pairs)} pairs:")
    print(f"  name_match:        {name_match}")
    print(f"  faction_inference: {faction_inferred}")
    print(f"  unresolved:        {unresolved}")

    coverage = (name_match + faction_inferred) / max(1, len(pairs)) * 100
    print(f"\nFinal coverage: {coverage:.1f}%")
    conn.close()


if __name__ == "__main__":
    resolve_all()
