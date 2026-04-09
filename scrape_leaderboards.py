"""
Scrape top 1v1 players (ELO >= MIN_ELO) from the Relic API across all factions.
"""

import time
import requests
from datetime import datetime, timezone

from config import (
    RELIC_API_BASE,
    RELIC_TITLE,
    LEADERBOARD_IDS,
    LEADERBOARD_PAGE_SIZE,
    MIN_ELO,
    REQUEST_DELAY,
    MAX_RETRIES,
)
from db import get_conn, init_db


def fetch_leaderboard_page(leaderboard_id: int, start: int, count: int) -> dict:
    url = f"{RELIC_API_BASE}/community/leaderboard/getleaderboard2"
    params = {
        "leaderboard_id": leaderboard_id,
        "title": RELIC_TITLE,
        "count": count,
        "start": start,
        "sortBy": 1,  # sort by ELO descending
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    return {}


def scrape_faction_leaderboard(faction: str, leaderboard_id: int):
    """Scrape all players with ELO >= MIN_ELO for one faction's 1v1 leaderboard."""
    print(f"\n--- Scraping {faction.upper()} 1v1 leaderboard (ELO >= {MIN_ELO}) ---")

    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    start = 1
    total_saved = 0
    done = False

    while not done:
        print(f"  Fetching positions {start}-{start + LEADERBOARD_PAGE_SIZE - 1}...")
        data = fetch_leaderboard_page(leaderboard_id, start, LEADERBOARD_PAGE_SIZE)

        if not data:
            print("  Empty response, stopping.")
            break

        stat_groups = {
            sg["id"]: sg for sg in data.get("statGroups", [])
        }
        lb_stats = data.get("leaderboardStats", [])

        if not lb_stats:
            print("  No more entries.")
            break

        page_saved = 0
        for entry in lb_stats:
            elo = entry.get("rating", 0)
            if elo < MIN_ELO:
                done = True
                break

            sg_id = entry.get("statgroup_id")
            sg = stat_groups.get(sg_id, {})
            members = sg.get("members", [])
            if not members:
                continue

            member = members[0]
            profile_id = member.get("profile_id")
            alias = member.get("alias", "")
            steam_id = member.get("name", "")
            country = member.get("country", "")

            # Upsert player
            conn.execute("""
                INSERT INTO players (profile_id, alias, steam_id, country, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    alias=excluded.alias,
                    steam_id=excluded.steam_id,
                    country=excluded.country,
                    last_updated=excluded.last_updated
            """, (profile_id, alias, steam_id, country, now))

            # Insert leaderboard entry
            conn.execute("""
                INSERT INTO leaderboard_entries
                    (profile_id, faction, elo, wins, losses, rank, streak, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile_id,
                faction,
                elo,
                entry.get("wins", 0),
                entry.get("losses", 0),
                entry.get("rank", -1),
                entry.get("streak", 0),
                now,
            ))

            page_saved += 1

        conn.commit()
        total_saved += page_saved
        print(f"  Saved {page_saved} players from this page (total: {total_saved})")

        if len(lb_stats) < LEADERBOARD_PAGE_SIZE:
            break

        start += LEADERBOARD_PAGE_SIZE
        time.sleep(REQUEST_DELAY)

    conn.close()
    print(f"  {faction.upper()} done: {total_saved} players with ELO >= {MIN_ELO}")
    return total_saved


def scrape_all_leaderboards():
    """Scrape 1v1 leaderboards for all factions."""
    init_db()
    grand_total = 0
    for faction, lb_id in LEADERBOARD_IDS.items():
        count = scrape_faction_leaderboard(faction, lb_id)
        grand_total += count
        time.sleep(REQUEST_DELAY)

    print(f"\n=== LEADERBOARD SCRAPE COMPLETE: {grand_total} total player-faction entries ===")
    return grand_total


if __name__ == "__main__":
    scrape_all_leaderboards()
