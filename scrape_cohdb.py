"""
Scrape build order data from cohdb.com.

1. Crawl match listings filtered for 1v1, ELO >= 1600
2. For each match, fetch the /replays/{id}/builds page
3. Extract the embedded JSON build order data
4. Store in the database
"""

import re
import json
import time
import html
import requests
from datetime import datetime, timezone

from config import MIN_ELO, REQUEST_DELAY, MAX_RETRIES
from db import get_conn, init_db

COHDB_BASE = "https://cohdb.com"
MATCHES_PER_PAGE = 20  # cohdb returns 20 per page

# Keywords that indicate tech/building actions
TECH_KEYWORDS = [
    "construct ", "unlock ", "upgrade ",
    "headquarters", "command post", "armory", "barracks",
    "weapon rack", "field support", "logistik kompanie",
    "schwerer panzer", "luftwaffe kompanie",
    "platoon command post", "company command post",
    "section command post", "battalion command post",
    "panzer kompanie", "infanterie kompanie",
    "officer quarters", "support center",
    "medical station", "medical bunker", "medical truck",
    "field infirmary",
]

# Keywords that indicate battlegroup selection (when lede="Selects ")
BATTLEGROUP_KEYWORDS = [
    "battlegroup", "airborne", "armored", "infantry reserves",
    "mechanized battlegroup", "special operations", "breakthrough",
    "italian infantry", "canadian shock", "indian artillery", "gurkha",
]

# Keywords that indicate ability/upgrade actions (NOT production units)
ABILITY_KEYWORDS = [
    " run", " loiter", " strike", " bomb", " bombing",
    " barrage", " drop", " dive", " strafing",
    " paradrop", "paradrop", "smoke screen",
    "raid package", "burnout", "pyrotechnics",
    "veteran", "training", "package",
    "transfer orders", "convert to",
    "ai takeover",
    "decapitation", "munitions surplus",
    "designate", "rapid", "advanced",
    "improved", "improvised", "fortifications",
    "support elements", "fire support",
    "advanced logistics", "field repairs", "emergency repair",
    "armored vehicle training", "infantry training",
    "side skirts", "panzerfaust rollout", "bolstered",
    "assault grenadier", "stoßtruppen", "kriegsmariner",
    "guastatori", "captain retinue", "polish lancer",
    "foot guards", "australian light", "ssf commando",
    "canadian shock section", "bersaglieri",
    "gurkha rifles", "ranger squad",
    "spy network", "resource caching", "munitions",
    "registered artillery", "zeroing artillery",
    "off-map", "incendiary", "vengeance", "strategic targets",
    "infantry assault", "breakthrough", "seek and destroy",
    "defend the fatherland", "propaganda war",
    "smoke bombing", "supply drop",
    "team weapon training", "heavy barrels",
    "pathfinder squad", "fallschirmpioneer",
    "improved m9 bazooka", "starburst flares",
    "raiding flares", "armored reserves",
    "coastal reserve", "survival",
    "transfer orders", "designate forward",
    "designate assault", "designate defensive",
    "rapid fortifications", "rapid repairs",
    "light vehicle withdraw", "advanced field",
    "incendiary bombing", "butterfly bomb",
    "air support center", "armored support center",
    "mechanized support center", "support armor elements",
    "combat half-tracks", "stug assault group",
    "mechanized group", "tank destroyer reserves",
    "panzerjäger mechanized", "assault mechanized",
    "pak 38 mechanized", "pak 38 reserves",
    "le.ig 18 mechanized", "le.ig 18 support",
    "assault grenadier squad", "panzerpioneer",
    "fallschirmjäger", "jäger squad",
    "captain retinue", "convert", "transfer",
    "veteran squad", "heavy machine gun paradrop",
    "anti-tank gun team paradrop", "lg40 recoilless gun paradrop",
    "fallschirmjäger squad paradrop", "paratrooper squad paradrop",
    "fallschirmpioneer squad paradrop",
    "registered", "zeroing", "infiltration",
    "resistance fighter", "munitions surplus",
    "decapitation strike", "spy network",
    "panzerfaust", "improvised armor",
    "grenade package", "browning automatic rifles",
    "bazooka squad",  # Bazooka Squad is an upgrade, not a base unit
    "grasshopper recon", "recon loiter",
    "smoke screen",
    "munitions", "rapid", "advanced",
]


def classify_action(unit: str, lede: str) -> str:
    """Classify a build order action into a category."""
    unit_lower = unit.lower()

    # Tech is always tech regardless of lede
    for kw in TECH_KEYWORDS:
        if kw in unit_lower:
            return "tech"

    if lede == "Selects ":
        # "Selects " can be battlegroup pick OR battlegroup ability/upgrade selection
        for kw in BATTLEGROUP_KEYWORDS:
            if kw in unit_lower:
                return "battlegroup"
        return "ability"

    # Empty lede: could be production OR ability usage
    for kw in ABILITY_KEYWORDS:
        if kw in unit_lower:
            return "ability"

    return "production"


def fetch_page(url: str) -> str | None:
    """Fetch a page with retries."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "CoH3ProAnalysis/1.0 (research tool)",
                "Accept": "text/html",
            })
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"    Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    return None


def scrape_match_listing(page: int = 1, elo: int = MIN_ELO) -> list[int]:
    """Scrape one page of the match listing. Returns list of match metadata."""
    url = f"{COHDB_BASE}/matches?mode=ones&rating={elo}&page={page}"
    print(f"  Fetching listing page {page}...", end=" ", flush=True)

    page_html = fetch_page(url)
    if not page_html:
        print("failed")
        return []

    # Extract replay IDs and basic metadata from table rows
    # Each row links to /replays/{id}
    replay_ids = re.findall(r'href="/replays/(\d+)"', page_html)
    # Deduplicate while preserving order (each match has 2 links: overview + download)
    seen = set()
    unique_ids = []
    for rid in replay_ids:
        if rid not in seen:
            seen.add(rid)
            unique_ids.append(int(rid))

    print(f"found {len(unique_ids)} replays")
    return unique_ids


def scrape_patch_version(replay_id: int) -> str | None:
    """Fetch the patch version from the replay overview page."""
    url = f"{COHDB_BASE}/replays/{replay_id}"
    page_html = fetch_page(url)
    if not page_html:
        return None
    patch_match = re.search(
        r'<dd>\s*(\d+\.\d+(?:\.\d+)*)\s*</dd>\s*<dt[^>]*>Patch</dt>',
        page_html, re.DOTALL,
    )
    return patch_match.group(1).strip() if patch_match else None


def scrape_build_orders(replay_id: int) -> tuple[list[dict], int | None, str | None]:
    """
    Scrape build order data from /replays/{id}/builds + patch from overview.
    Returns (list of player build orders, match_duration_seconds, patch_version).
    """
    url = f"{COHDB_BASE}/replays/{replay_id}/builds"
    page_html = fetch_page(url)
    if not page_html:
        return [], None, None

    # Extract the JSON from data-timeline-players-value attribute
    players_match = re.search(
        r'data-timeline-players-value="([^"]+)"', page_html
    )
    if not players_match:
        return [], None, None

    # HTML-unescape and parse JSON
    raw = html.unescape(players_match.group(1))
    try:
        players_data = json.loads(raw)
    except json.JSONDecodeError:
        return [], None, None

    # Extract match length
    length_match = re.search(r'data-timeline-length-value="(\d+)"', page_html)
    duration_s = int(length_match.group(1)) if length_match else None

    # Fetch patch from overview page
    time.sleep(REQUEST_DELAY)
    patch = scrape_patch_version(replay_id)

    return players_data, duration_s, patch


def store_replay_build_orders(replay_id: int, players_data: list[dict],
                               duration_s: int | None, patch: str | None, conn):
    """Store build order data for a replay."""
    now = datetime.now(timezone.utc).isoformat()

    # Clear any existing build orders for this replay (in case of re-scrape)
    conn.execute("DELETE FROM build_orders WHERE replay_id = ?", (replay_id,))

    # Upsert the replay record
    conn.execute("""
        INSERT INTO cohdb_replays (replay_id, duration_s, mode, patch, scraped_at)
        VALUES (?, ?, 'ranked_1v1', ?, ?)
        ON CONFLICT(replay_id) DO UPDATE SET
            duration_s=excluded.duration_s,
            patch=excluded.patch,
            scraped_at=excluded.scraped_at
    """, (replay_id, duration_s, patch, now))

    total_actions = 0
    for player in players_data:
        name = player.get("name", "unknown")
        actions = player.get("actions", [])

        for action in actions:
            seconds = action.get("seconds", 0)
            unit = action.get("unit", "")
            lede = action.get("lede", "")
            action_type = classify_action(unit, lede)

            conn.execute("""
                INSERT INTO build_orders (replay_id, player_name, seconds, unit, action_type)
                VALUES (?, ?, ?, ?, ?)
            """, (replay_id, name, seconds, unit, action_type))
            total_actions += 1

    return total_actions


def scrape_cohdb(max_pages: int = 50, elo: int = MIN_ELO):
    """
    Main scraper: crawl match listings and fetch build orders.

    Args:
        max_pages: Maximum number of listing pages to crawl (20 matches each)
        elo: Minimum ELO filter
    """
    init_db()
    conn = get_conn()

    total_replays = 0
    total_actions = 0
    skipped = 0

    print(f"\n=== Scraping cohdb.com build orders (1v1, ELO >= {elo}) ===\n")

    for page in range(1, max_pages + 1):
        replay_ids = scrape_match_listing(page, elo)
        if not replay_ids:
            print("  No more results, stopping.")
            break

        for rid in replay_ids:
            # Skip if already scraped
            existing = conn.execute(
                "SELECT 1 FROM cohdb_replays WHERE replay_id = ?", (rid,)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            print(f"    Replay {rid}:", end=" ", flush=True)
            players_data, duration_s, patch = scrape_build_orders(rid)

            if not players_data:
                print("no build data")
                time.sleep(REQUEST_DELAY)
                continue

            actions = store_replay_build_orders(rid, players_data, duration_s, patch, conn)
            conn.commit()
            total_replays += 1
            total_actions += actions

            player_names = [p.get("name", "?") for p in players_data]
            patch_str = f" [{patch}]" if patch else ""
            print(f"{' vs '.join(player_names)} ({actions} actions, {duration_s}s){patch_str}")

            time.sleep(REQUEST_DELAY)

        time.sleep(REQUEST_DELAY)

    conn.close()
    print(f"\n=== COHDB SCRAPE COMPLETE ===")
    print(f"    Replays scraped: {total_replays}")
    print(f"    Total actions:   {total_actions}")
    print(f"    Skipped (dupe):  {skipped}")
    return total_replays


if __name__ == "__main__":
    import sys
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    scrape_cohdb(max_pages=pages)
