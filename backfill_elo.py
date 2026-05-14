"""
One-shot backfill of match_players ELO data after fixing the
matchhistoryitems -> matchhistorymember field bug in scrape_matches.py.

The Relic API endpoint returns only the player's RECENT match history
(~100 matches), so older matches in our DB may not be reachable. We
backfill what we can and leave anything older as NULL.

Idempotent: WHERE elo_before IS NULL guards against re-writing rows.
"""

import time
from db import get_conn
from scrape_matches import fetch_match_history
from config import REQUEST_DELAY, MIN_ELO


def main():
    conn = get_conn()

    pre = conn.execute(
        "SELECT COUNT(*) FROM match_players WHERE elo_before IS NULL"
    ).fetchone()[0]
    print(f"match_players rows with NULL ELO before backfill: {pre}")

    players = conn.execute("""
        SELECT DISTINCT p.profile_id, p.alias
        FROM players p
        JOIN leaderboard_entries le ON p.profile_id = le.profile_id
        WHERE le.elo >= ? AND p.alias != ''
        ORDER BY le.elo DESC
    """, (MIN_ELO,)).fetchall()

    print(f"Querying {len(players)} pro players...\n")

    total = 0
    for i, p in enumerate(players, 1):
        pid = p["profile_id"]
        alias = p["alias"]
        print(f"[{i}/{len(players)}] {alias} (pid={pid})...", end=" ", flush=True)

        data = fetch_match_history(pid)
        if not data:
            print("api failed")
            continue

        n_updated = 0
        for match in data.get("matchHistoryStats", []):
            mid = match.get("id")
            if not mid or match.get("matchtype_id") != 20:
                continue

            for member in match.get("matchhistorymember", []):
                m_pid = member.get("profile_id")
                old = member.get("oldrating")
                new = member.get("newrating")
                if m_pid is None or old is None or new is None:
                    continue
                diff = new - old
                # Only update rows that don't yet have ELO. Safe to re-run.
                n = conn.execute("""
                    UPDATE match_players
                    SET elo_before = ?, elo_after = ?, elo_diff = ?
                    WHERE match_id = ? AND profile_id = ? AND elo_before IS NULL
                """, (old, new, diff, mid, m_pid)).rowcount
                n_updated += n

        conn.commit()
        print(f"{n_updated} rows updated")
        total += n_updated
        time.sleep(REQUEST_DELAY)

    post = conn.execute(
        "SELECT COUNT(*) FROM match_players WHERE elo_before IS NULL"
    ).fetchone()[0]
    print(f"\n=== DONE ===")
    print(f"  rows updated:        {total}")
    print(f"  NULL ELO before:     {pre}")
    print(f"  NULL ELO after:      {post}")
    print(f"  coverage gained:     {pre - post} rows ({(pre - post) * 100 / pre:.1f}% of NULL)" if pre else "")
    conn.close()


if __name__ == "__main__":
    main()
