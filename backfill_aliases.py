"""
One-shot backfill for players with empty alias. The Relic API's match-
history endpoint returns a `profiles` array containing alias/country for
every player involved (the queried pro AND all their opponents), so a
single sweep over our 139 pro players harvests aliases for the ~564
"unknown opponent" rows in the players table.

Idempotent: WHERE alias = '' guards against overwriting good data.
"""

import time
from db import get_conn
from scrape_matches import fetch_match_history
from config import REQUEST_DELAY, MIN_ELO


def main():
    conn = get_conn()

    pre = conn.execute(
        "SELECT COUNT(*) FROM players WHERE alias IS NULL OR alias = ''"
    ).fetchone()[0]
    print(f"players with empty alias before backfill: {pre}", flush=True)

    players = conn.execute("""
        SELECT DISTINCT p.profile_id, p.alias
        FROM players p
        JOIN leaderboard_entries le ON p.profile_id = le.profile_id
        WHERE le.elo >= ? AND p.alias != ''
        ORDER BY le.elo DESC
    """, (MIN_ELO,)).fetchall()

    print(f"Querying {len(players)} pro players to harvest opponent aliases...\n", flush=True)

    total_resolved = 0
    for i, p in enumerate(players, 1):
        pid = p["profile_id"]
        alias = p["alias"]
        print(f"[{i}/{len(players)}] {alias} (pid={pid})...", end=" ", flush=True)

        data = fetch_match_history(pid)
        if not data:
            print("api failed", flush=True)
            continue

        n_resolved = 0
        for profile in data.get("profiles", []):
            ppid = profile.get("profile_id")
            palias = profile.get("alias", "")
            pcountry = profile.get("country", "")
            psteam = profile.get("name", "")
            if not ppid or not palias:
                continue
            # Only update rows that have empty alias. Safe to re-run.
            n = conn.execute("""
                UPDATE players
                SET alias = ?,
                    country = CASE WHEN country = '' THEN ? ELSE country END,
                    steam_id = CASE WHEN steam_id = '' THEN ? ELSE steam_id END
                WHERE profile_id = ? AND (alias IS NULL OR alias = '')
            """, (palias, pcountry, psteam, ppid)).rowcount
            n_resolved += n

        conn.commit()
        print(f"{n_resolved} aliases resolved", flush=True)
        total_resolved += n_resolved
        time.sleep(REQUEST_DELAY)

    post = conn.execute(
        "SELECT COUNT(*) FROM players WHERE alias IS NULL OR alias = ''"
    ).fetchone()[0]
    print(f"\n=== DONE ===", flush=True)
    print(f"  resolved:     {total_resolved}", flush=True)
    print(f"  empty before: {pre}", flush=True)
    print(f"  empty after:  {post}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
