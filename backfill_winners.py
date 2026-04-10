"""
Backfill winner/faction/side data for existing cohdb replays by re-scraping
the cohdb match listing pages (which contain the result column).

Each row on cohdb.com/matches?mode=ones&rating=1600 has:
  - 1v1 mode label
  - map name
  - 1st player img + name (always allies side)
  - 2nd player img + name (always axis side)
  - "allies victory" or "axis victory" text
  - duration
  - replay_id (in /replays/{id} link)
"""

import re
import time
import html
import requests
from html.parser import HTMLParser

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


def fetch_listing(page: int) -> str | None:
    url = f"{COHDB_BASE}/matches?mode=ones&rating={MIN_ELO}&page={page}"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "CoH3ProAnalysis/1.0",
                "Accept": "text/html",
            })
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"    page {page} attempt {attempt+1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    return None


PLAYER_CELL_RE = re.compile(
    r'<img[^>]*src="/assets/(americans|british_africa|british|germans|afrika_korps)[^"]*"[^>]*/>\s*([^<]+?)\s*</td>',
    re.DOTALL,
)


def parse_listing(page_html: str) -> list[dict]:
    """Parse one listing page into a list of {replay_id, players, winner_side, ...}."""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', page_html, re.DOTALL)
    matches = []

    for row in rows:
        # Need a replay link
        rid_match = re.search(r'/replays/(\d+)', row)
        if not rid_match:
            continue
        replay_id = int(rid_match.group(1))

        # Two player cells (faction + name)
        player_cells = PLAYER_CELL_RE.findall(row)
        if len(player_cells) < 2:
            continue
        p1_faction, p1_name = player_cells[0]
        p2_faction, p2_name = player_cells[1]
        p1_name = html.unescape(p1_name).strip()
        p2_name = html.unescape(p2_name).strip()

        # Result column
        result_match = re.search(r'(allies|axis)\s+victory', row, re.IGNORECASE)
        if not result_match:
            continue
        winner_side = result_match.group(1).lower()

        # Map name (3rd <td>)
        td_matches = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        # Find the map cell - it's the one that just contains text and isn't a player cell
        map_name = None
        for td in td_matches:
            stripped = re.sub(r'<[^>]+>', '', td).strip()
            # Maps are lowercase with underscores, no spaces
            if re.match(r'^[a-z][a-z0-9_]+$', stripped):
                map_name = stripped
                break

        p1_side = SIDE_OF_FACTION.get(p1_faction, "?")
        p2_side = SIDE_OF_FACTION.get(p2_faction, "?")

        matches.append({
            "replay_id": replay_id,
            "winner_side": winner_side,
            "map_name": map_name,
            "players": [
                {"name": p1_name, "faction_slug": p1_faction, "side": p1_side,
                 "won": 1 if p1_side == winner_side else 0},
                {"name": p2_name, "faction_slug": p2_faction, "side": p2_side,
                 "won": 1 if p2_side == winner_side else 0},
            ],
        })

    return matches


def store_match_result(match: dict, conn):
    """Update cohdb_replays + insert into cohdb_replay_players."""
    rid = match["replay_id"]
    # Update replay row
    conn.execute("""
        UPDATE cohdb_replays
        SET winner_side = ?, map_name = COALESCE(map_name, ?)
        WHERE replay_id = ?
    """, (match["winner_side"], match["map_name"], rid))

    # Insert player rows (replace any existing)
    conn.execute("DELETE FROM cohdb_replay_players WHERE replay_id = ?", (rid,))
    for p in match["players"]:
        conn.execute("""
            INSERT OR IGNORE INTO cohdb_replay_players
                (replay_id, player_name, faction_slug, side, won)
            VALUES (?, ?, ?, ?, ?)
        """, (rid, p["name"], p["faction_slug"], p["side"], p["won"]))


def backfill(max_pages: int = 100):
    init_db()
    conn = get_conn()

    # Find which replay_ids we still need
    needed = {r["replay_id"] for r in conn.execute(
        "SELECT replay_id FROM cohdb_replays WHERE winner_side IS NULL"
    ).fetchall()}
    print(f"Need winner data for {len(needed)} replays\n")

    if not needed:
        print("All replays already have winner data.")
        return

    updated = 0
    for page in range(1, max_pages + 1):
        if not needed:
            break
        print(f"  Page {page}...", end=" ", flush=True)
        page_html = fetch_listing(page)
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

        time.sleep(REQUEST_DELAY)

    print(f"\n=== BACKFILL COMPLETE: {updated} replays updated ===")
    conn.close()


if __name__ == "__main__":
    import sys
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    backfill(max_pages=pages)
