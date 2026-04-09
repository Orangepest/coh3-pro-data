"""
Pull match history for all pro players in the database via the Relic API.
"""

import time
import requests
from datetime import datetime, timezone

from config import (
    RELIC_API_BASE,
    RELIC_TITLE,
    RACE_IDS,
    MATCH_TYPES,
    MIN_ELO,
    REQUEST_DELAY,
    MAX_RETRIES,
)
from db import get_conn, init_db


def fetch_match_history(profile_id: int) -> dict:
    url = f"{RELIC_API_BASE}/community/leaderboard/getRecentMatchHistoryByProfileId"
    params = {
        "profile_id": profile_id,
        "title": RELIC_TITLE,
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            print(f"    Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    return {}


def parse_and_store_matches(data: dict, conn):
    """Parse Relic match history response and store matches + participants."""
    now = datetime.now(timezone.utc).isoformat()

    profiles = {}
    for sg in data.get("statGroups", []):
        for member in sg.get("members", []):
            pid = member.get("profile_id")
            if pid:
                profiles[pid] = {
                    "alias": member.get("alias", ""),
                    "steam_id": member.get("name", ""),
                    "country": member.get("country", ""),
                }

    match_history = data.get("matchHistoryStats", [])
    new_matches = 0

    for match in match_history:
        match_id = match.get("id")
        if not match_id:
            continue

        # Check match type - we only care about 1v1 ranked
        match_type_id = match.get("matchtype_id", 0)
        match_type = MATCH_TYPES.get(match_type_id, f"unknown_{match_type_id}")
        if match_type != "ranked_1v1":
            continue

        # Check if match already exists
        existing = conn.execute(
            "SELECT 1 FROM matches WHERE match_id = ?", (match_id,)
        ).fetchone()
        if existing:
            continue

        map_name = match.get("mapname", "unknown")
        start_time = match.get("startgametime", 0)
        completion_time = match.get("completiontime", 0)
        duration_s = (completion_time - start_time) if (completion_time and start_time) else None

        conn.execute("""
            INSERT OR IGNORE INTO matches (match_id, map_name, match_type, start_time, duration_s, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (match_id, map_name, match_type, start_time, duration_s, now))

        # Parse match players from the nested report results
        match_reports = match.get("matchhistoryreportresults", [])
        for report in match_reports:
            pid = report.get("profile_id")
            if not pid:
                continue

            race_id = report.get("race_id", 0)
            faction = RACE_IDS.get(race_id, f"unknown_{race_id}")
            result_type = report.get("resulttype", -1)
            result = "win" if result_type == 1 else "loss" if result_type == 0 else "unknown"

            # ELO data from matchhistoryitems if available
            match_items = match.get("matchhistoryitems", [])
            elo_before = None
            elo_after = None
            elo_diff = None
            for item in match_items:
                if item.get("profile_id") == pid:
                    elo_before = item.get("oldrating")
                    elo_after = item.get("newrating")
                    if elo_before is not None and elo_after is not None:
                        elo_diff = elo_after - elo_before
                    break

            # Upsert player info
            profile_info = profiles.get(pid, {})
            if profile_info:
                conn.execute("""
                    INSERT INTO players (profile_id, alias, steam_id, country, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id) DO UPDATE SET
                        alias=excluded.alias,
                        steam_id=excluded.steam_id,
                        country=excluded.country,
                        last_updated=excluded.last_updated
                """, (pid, profile_info.get("alias", ""), profile_info.get("steam_id", ""),
                       profile_info.get("country", ""), now))

            conn.execute("""
                INSERT OR IGNORE INTO match_players
                    (match_id, profile_id, faction, elo_before, elo_after, elo_diff, result, team_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (match_id, pid, faction, elo_before, elo_after, elo_diff, result,
                  report.get("teamid")))

        new_matches += 1

    return new_matches


def scrape_all_match_histories():
    """Pull match history for every player in the DB."""
    init_db()
    conn = get_conn()

    players = conn.execute("""
        SELECT DISTINCT p.profile_id, p.alias
        FROM players p
        JOIN leaderboard_entries le ON p.profile_id = le.profile_id
        WHERE le.elo >= ?
        ORDER BY le.elo DESC
    """, (MIN_ELO,)).fetchall()

    print(f"\n=== Scraping match history for {len(players)} pro players (ELO >= {MIN_ELO}) ===\n")

    total_new = 0
    for i, player in enumerate(players, 1):
        pid = player["profile_id"]
        alias = player["alias"]
        print(f"[{i}/{len(players)}] {alias} (ID: {pid})...", end=" ")

        data = fetch_match_history(pid)
        if data:
            new = parse_and_store_matches(data, conn)
            conn.commit()
            total_new += new
            print(f"{new} new 1v1 ranked matches")
        else:
            print("failed")

        time.sleep(REQUEST_DELAY)

    conn.close()
    print(f"\n=== MATCH SCRAPE COMPLETE: {total_new} new matches stored ===")
    return total_new


if __name__ == "__main__":
    scrape_all_match_histories()
