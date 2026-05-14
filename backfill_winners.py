"""
Backfill winner/faction/side data for existing cohdb replays by re-scraping
the cohdb match listing pages.

Updated 2026-05 for cohdb Hotwire/Turbo site rewrite:
- listing uses cursor pagination via /matches.turbo_stream?...&page=<cursor>
- row layout has faction <img> per side, hidden "Allies|Axis" victor span
"""

import re
import time
import html
import requests

from config import REQUEST_DELAY, MAX_RETRIES, MIN_ELO
from db import get_conn, init_db


COHDB_BASE = "https://cohdb.com"

# Map cohdb faction slugs to allies/axis side
SIDE_OF_FACTION = {
    "americans": "allies",
    "british_africa": "allies",
    "british": "allies",
    "germans": "axis",
    "afrika_korps": "axis",
}

# Normalize new-site singular slugs to the plural form used in stored data
FACTION_SLUG_NORMALIZE = {
    "american": "americans",
    "german": "germans",
}


def fetch_listing(cursor: str | None) -> str | None:
    if cursor:
        url = f"{COHDB_BASE}{cursor}"
    else:
        url = f"{COHDB_BASE}/matches?mode=ones&rating={MIN_ELO}"
    headers = {
        "User-Agent": "CoH3ProAnalysis/1.0",
        "Accept": "text/html",
        "Turbo-Frame": "matches-table",
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=30, headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"    attempt {attempt+1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    return None


def extract_next_cursor(page_html: str) -> str | None:
    m = re.search(r'src="(/matches\.turbo_stream\?[^"]+)"', page_html)
    return html.unescape(m.group(1)) if m else None


FACTION_IMG_RE = re.compile(
    r'/assets/common/factions/([a-z_]+)_mipped'
)
PLAYER_LINK_RE = re.compile(
    r'href="/players/\d+"[^>]*>([^<]+)</a>'
)
VICTOR_RE = re.compile(
    r'<span class="hidden text-sm font-medium text-[a-z]+-\d+">\s*(Allies|Axis)\s*</span>'
)


def parse_listing(page_html: str) -> list[dict]:
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', page_html, re.DOTALL)
    matches = []

    for row in rows:
        rid_match = re.search(r'/replays/(\d+)', row)
        if not rid_match:
            continue
        replay_id = int(rid_match.group(1))

        factions = FACTION_IMG_RE.findall(row)
        if len(factions) < 2:
            continue
        # Names may be < 2 when a player's profile is private/deleted.
        # Still record winner_side + faction sides; missing names become None.
        names = PLAYER_LINK_RE.findall(row)
        victor = VICTOR_RE.search(row)
        if not victor:
            continue

        p1_faction = FACTION_SLUG_NORMALIZE.get(factions[0], factions[0])
        p2_faction = FACTION_SLUG_NORMALIZE.get(factions[1], factions[1])
        p1_side = SIDE_OF_FACTION.get(p1_faction, "?")
        p2_side = SIDE_OF_FACTION.get(p2_faction, "?")
        winner_side = victor.group(1).lower()
        p1_name = html.unescape(names[0]).strip() if len(names) > 0 else None
        p2_name = html.unescape(names[1]).strip() if len(names) > 1 else None

        matches.append({
            "replay_id": replay_id,
            "winner_side": winner_side,
            "players": [
                {"name": p1_name, "faction_slug": p1_faction, "side": p1_side,
                 "won": 1 if p1_side == winner_side else 0},
                {"name": p2_name, "faction_slug": p2_faction, "side": p2_side,
                 "won": 1 if p2_side == winner_side else 0},
            ],
        })

    return matches


def store_match_result(match: dict, conn):
    rid = match["replay_id"]
    conn.execute(
        "UPDATE cohdb_replays SET winner_side = ? WHERE replay_id = ?",
        (match["winner_side"], rid),
    )
    conn.execute("DELETE FROM cohdb_replay_players WHERE replay_id = ?", (rid,))
    for p in match["players"]:
        # Skip players with no resolvable name (private/deleted profile).
        # winner_side at the replay level is still recorded above.
        if not p["name"]:
            continue
        conn.execute("""
            INSERT OR IGNORE INTO cohdb_replay_players
                (replay_id, player_name, faction_slug, side, won)
            VALUES (?, ?, ?, ?, ?)
        """, (rid, p["name"], p["faction_slug"], p["side"], p["won"]))


def backfill(max_pages: int = 500):
    init_db()
    conn = get_conn()

    needed = {r[0] for r in conn.execute(
        "SELECT replay_id FROM cohdb_replays WHERE winner_side IS NULL"
    ).fetchall()}
    print(f"Need winner data for {len(needed)} replays\n")

    if not needed:
        print("All replays already have winner data.")
        return

    updated = 0
    cursor = None
    for page in range(1, max_pages + 1):
        if not needed:
            break
        print(f"  Page {page}...", end=" ", flush=True)
        page_html = fetch_listing(cursor)
        if not page_html:
            print("empty, stopping.")
            break
        matches = parse_listing(page_html)
        if not matches:
            print("no matches parsed.")
            break

        page_updates = 0
        for m in matches:
            if m["replay_id"] in needed:
                store_match_result(m, conn)
                needed.discard(m["replay_id"])
                page_updates += 1
                updated += 1
        conn.commit()
        print(f"{len(matches)} rows, {page_updates} backfilled. {len(needed)} still needed.")

        cursor = extract_next_cursor(page_html)
        if not cursor:
            print("  No next cursor, stopping.")
            break
        time.sleep(REQUEST_DELAY)

    print(f"\n=== BACKFILL COMPLETE: {updated} replays updated ===")

    # Scrub cohdb name-resolution phantoms (e.g. "Coastal Reserves Squad"
    # mis-attributed to DAK players). Faction info is now populated, so we
    # can safely identify and delete impossible (unit, faction) rows.
    from scrape_cohdb import scrub_phantom_units
    print("\n=== Scrubbing cohdb name-resolution phantoms ===")
    scrubbed = scrub_phantom_units(conn)
    print(f"  Total scrubbed: {scrubbed}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    backfill(max_pages=pages)
