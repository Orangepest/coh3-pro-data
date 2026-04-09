"""
Download bulk match data from coh3stats.com open data dumps.
Filters for 1v1 ranked matches and stores them in the database.
"""

import time
import json
import requests
from datetime import datetime, timezone, timedelta

from config import (
    COH3STATS_MATCHES_URL,
    RACE_IDS,
    MIN_ELO,
    REQUEST_DELAY,
    MAX_RETRIES,
)
from db import get_conn, init_db


def date_to_timestamp(dt: datetime) -> int:
    """Convert a datetime to the coh3stats daily dump timestamp (06:00 UTC)."""
    dump_time = dt.replace(hour=6, minute=0, second=0, microsecond=0)
    return int(dump_time.timestamp())


def download_day(timestamp: int) -> list | None:
    """Download the match dump for a given day's timestamp."""
    url = COH3STATS_MATCHES_URL.format(timestamp=timestamp)
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=120)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            print(f"    Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    return None


def is_pro_1v1_match(match: dict) -> bool:
    """Check if a match is a 1v1 ranked game involving at least one 1600+ player."""
    match_type = match.get("matchtype_id", 0)
    if match_type != 1:  # ranked 1v1
        return False

    # Check matchhistoryitems for ELO data (preferred source)
    for item in match.get("matchhistoryitems", []):
        rating = item.get("newrating") or item.get("oldrating") or 0
        if rating >= MIN_ELO:
            return True

    # Fallback: check matchhistoryreportresults for inline rating
    for report in match.get("matchhistoryreportresults", []):
        for key in ("rating", "newrating", "oldrating", "matchhistory_maxrating"):
            rating = report.get(key, 0) or 0
            if rating >= MIN_ELO:
                return True

    return False


def store_match(match: dict, conn):
    """Store a single match from the open data dump."""
    match_id = match.get("id")
    if not match_id:
        return False

    existing = conn.execute("SELECT 1 FROM matches WHERE match_id = ?", (match_id,)).fetchone()
    if existing:
        return False

    now = datetime.now(timezone.utc).isoformat()
    map_name = match.get("mapname", "unknown")
    start_time = match.get("startgametime", 0)
    completion_time = match.get("completiontime", 0)
    duration_s = (completion_time - start_time) if (completion_time and start_time) else None

    conn.execute("""
        INSERT OR IGNORE INTO matches (match_id, map_name, match_type, start_time, duration_s, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (match_id, map_name, "ranked_1v1", start_time, duration_s, now))

    for report in match.get("matchhistoryreportresults", []):
        pid = report.get("profile_id")
        if not pid:
            continue

        race_id = report.get("race_id", 0)
        faction = RACE_IDS.get(race_id, f"unknown_{race_id}")
        result_type = report.get("resulttype", -1)
        result = "win" if result_type == 1 else "loss" if result_type == 0 else "unknown"

        elo_before = None
        elo_after = None
        elo_diff = None
        for item in match.get("matchhistoryitems", []):
            if item.get("profile_id") == pid:
                elo_before = item.get("oldrating")
                elo_after = item.get("newrating")
                if elo_before is not None and elo_after is not None:
                    elo_diff = elo_after - elo_before
                break

        # Upsert player (minimal info from open data)
        conn.execute("""
            INSERT INTO players (profile_id, alias, last_updated)
            VALUES (?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET last_updated=excluded.last_updated
        """, (pid, "", now))

        conn.execute("""
            INSERT OR IGNORE INTO match_players
                (match_id, profile_id, faction, elo_before, elo_after, elo_diff, result, team_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (match_id, pid, faction, elo_before, elo_after, elo_diff, result,
              report.get("teamid")))

    return True


def download_date_range(start_date: datetime, end_date: datetime):
    """Download and process open data dumps for a date range."""
    init_db()
    conn = get_conn()

    current = start_date
    total_matches = 0
    days_processed = 0

    print(f"\n=== Downloading coh3stats open data: {start_date.date()} to {end_date.date()} ===")
    print(f"    Filtering for 1v1 ranked matches with ELO >= {MIN_ELO}\n")

    while current <= end_date:
        ts = date_to_timestamp(current)
        date_str = current.strftime("%Y-%m-%d")
        print(f"[{date_str}] Downloading...", end=" ", flush=True)

        matches = download_day(ts)
        if matches is None:
            print("not available")
            current += timedelta(days=1)
            continue

        day_count = 0
        for match in matches:
            if is_pro_1v1_match(match):
                if store_match(match, conn):
                    day_count += 1

        conn.commit()
        total_matches += day_count
        days_processed += 1
        print(f"{len(matches)} total matches -> {day_count} new pro 1v1 matches")

        current += timedelta(days=1)
        time.sleep(REQUEST_DELAY)

    conn.close()
    print(f"\n=== OPEN DATA COMPLETE: {total_matches} pro matches from {days_processed} days ===")
    return total_matches


def download_recent(days: int = 30):
    """Download the last N days of open data."""
    end = datetime.now(timezone.utc) - timedelta(days=1)  # yesterday (today's not ready yet)
    start = end - timedelta(days=days)
    return download_date_range(start, end)


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    download_recent(days)
