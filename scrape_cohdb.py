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
from unit_names import is_unit

COHDB_BASE = "https://cohdb.com"
MATCHES_PER_PAGE = 20  # cohdb returns 20 per page

# Keywords that indicate tech/building actions (constructions and tier unlocks)
TECH_KEYWORDS = [
    "construct ", "unlock ", "upgrade ",
    "officer quarters",  # Wehr battle phase upgrades
    "support elements", "fire support elements", "support armor elements",
    "combat half-tracks", "advanced logistics",
    "infantry training", "armored vehicle training",
]

# Keywords that indicate battlegroup selection (when lede="Selects ")
BATTLEGROUP_KEYWORDS = [
    "battlegroup", "airborne", "armored", "infantry reserves",
    "mechanized battlegroup", "special operations", "breakthrough",
    "italian infantry", "canadian shock", "indian artillery", "gurkha",
]

def classify_action(unit: str, lede: str) -> str:
    """
    Classify a build order action into one of: production, tech, battlegroup, ability.

    Uses authoritative game data via is_unit() to identify production units.
    Anything not a recognized unit, tech, or battlegroup is treated as ability.
    """
    unit_lower = unit.lower()

    # Tech is always tech regardless of lede (constructions, unlocks, upgrades)
    for kw in TECH_KEYWORDS:
        if kw in unit_lower:
            return "tech"

    if lede == "Selects ":
        # Battlegroup picks have "battlegroup" in the name
        for kw in BATTLEGROUP_KEYWORDS:
            if kw in unit_lower:
                return "battlegroup"
        return "ability"

    # Empty lede: real production unit or an ability/call-in usage
    if is_unit(unit):
        return "production"

    return "ability"


def fetch_page(url: str, turbo_frame: str | None = None) -> str | None:
    """Fetch a page with retries. Optionally send a Turbo-Frame header
    for Hotwire/Turbo SPA pages."""
    headers = {
        "User-Agent": "CoH3ProAnalysis/1.0 (research tool)",
        "Accept": "text/html",
    }
    if turbo_frame:
        headers["Turbo-Frame"] = turbo_frame
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=30, headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"    Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    return None


def scrape_match_listing(page: int = 1, elo: int = MIN_ELO,
                         cursor: str | None = None) -> tuple[list[int], str | None]:
    """Scrape one page of the match listing.

    Returns (list_of_replay_ids, next_cursor_url_or_None).
    Supports both old page-number pagination and new cursor-based pagination.
    """
    if cursor:
        url = f"{COHDB_BASE}{cursor}"
    else:
        url = f"{COHDB_BASE}/matches?mode=ones&rating={elo}"
    print(f"  Fetching listing page {page}...", end=" ", flush=True)

    # Try Turbo-Frame header (new site format)
    page_html = fetch_page(url, turbo_frame="matches-table")
    if not page_html or 'href="/replays/' not in page_html:
        # Fall back to plain request (old format)
        page_html = fetch_page(url)
    if not page_html:
        print("failed")
        return [], None

    # Extract replay IDs
    replay_ids = re.findall(r'href="/replays/(\d+)"', page_html)
    seen = set()
    unique_ids = []
    for rid in replay_ids:
        if rid not in seen:
            seen.add(rid)
            unique_ids.append(int(rid))

    # Extract next cursor for pagination
    next_cursor = None
    cursor_match = re.search(
        r'src="(/matches\.turbo_stream\?[^"]+)"',
        page_html,
    )
    if cursor_match:
        next_cursor = html.unescape(cursor_match.group(1))

    print(f"found {len(unique_ids)} replays")
    return unique_ids, next_cursor


def scrape_replay_overview(replay_id: int) -> tuple[str | None, str | None]:
    """Fetch patch version and map name from the replay overview page.
    Returns (patch, map_name)."""
    url = f"{COHDB_BASE}/replays/{replay_id}"
    page_html = fetch_page(url)
    if not page_html:
        return None, None

    # Old format: <dd>2.3.1</dd><dt>Patch</dt>
    patch_match = re.search(
        r'<dd>\s*(\d+\.\d+(?:\.\d+)*)\s*</dd>\s*<dt[^>]*>Patch</dt>',
        page_html, re.DOTALL,
    )
    if not patch_match:
        # New format (2026+): <span>Patch</span> ... <span>v2.3.1</span>
        patch_match = re.search(r'>v(\d+\.\d+(?:\.\d+)*)</', page_html)
    patch = patch_match.group(1).strip() if patch_match else None

    # Old format: /assets/{mapname}_large-{hash}.png
    map_match = re.search(r'/assets/([a-z0-9_]+)_large-[a-f0-9]+\.png', page_html)
    if not map_match:
        # New format: map name in scenario image path /assets/scenarios/.../mapname_2p/
        map_match = re.search(r'/assets/scenarios/[^/]+/[^/]+/([a-z0-9_]+)/', page_html)
    map_name = map_match.group(1) if map_match else None

    return patch, map_name


def scrape_patch_version(replay_id: int) -> str | None:
    """Backwards-compat wrapper - returns just the patch version."""
    patch, _ = scrape_replay_overview(replay_id)
    return patch


def _parse_builds_old_format(page_html: str) -> tuple[list[dict], int | None]:
    """Parse the old data-timeline-players-value JSON format (pre-2026 site)."""
    players_match = re.search(
        r'data-timeline-players-value="([^"]+)"', page_html
    )
    if not players_match:
        return [], None

    raw = html.unescape(players_match.group(1))
    try:
        players_data = json.loads(raw)
    except json.JSONDecodeError:
        return [], None

    length_match = re.search(r'data-timeline-length-value="(\d+)"', page_html)
    duration_s = int(length_match.group(1)) if length_match else None
    return players_data, duration_s


def _parse_builds_new_format(page_html: str) -> tuple[list[dict], int | None]:
    """Parse the new Hotwire/Turbo HTML format (2026+ site update).

    Build orders are in data-tooltip-content-value attributes with
    player names in <span class="text-sm font-semibold text-{color}"> tags.
    """
    # Extract the build_orders_section turbo frame content
    section_match = re.search(
        r'<turbo-frame id="build_orders_section">(.*?)</turbo-frame>',
        page_html, re.DOTALL,
    )
    if not section_match:
        return [], None

    section = section_match.group(1)

    # Find player names — they appear as colored spans before their build entries
    # e.g. <span class="text-sm font-semibold text-lime-400">El Dorado</span>
    player_name_pattern = r'<span class="text-sm font-semibold text-[a-z]+-\d+">([^<]+)</span>'
    player_names = [html.unescape(n) for n in re.findall(player_name_pattern, section)]
    if not player_names:
        return [], None

    # Split the section by player name spans to get each player's block
    split_pattern = r'<span class="text-sm font-semibold text-[a-z]+-\d+">[^<]+</span>'
    blocks = re.split(split_pattern, section)
    # First block is before first player name (header cruft), skip it
    blocks = blocks[1:]

    players_data = []
    for i, block in enumerate(blocks):
        if i >= len(player_names):
            break
        name = player_names[i]

        # Extract all tooltip entries: "0:48 &mdash; Riflemen Squad"
        tooltips = re.findall(
            r'data-tooltip-content-value="([^"]+)"', block
        )

        actions = []
        for tt in tooltips:
            # Double-unescape: &amp;mdash; -> &mdash; -> —
            decoded = html.unescape(html.unescape(tt))
            # Handle entries with <br> (multiple actions in one tooltip)
            for entry in re.split(r'<br\s*/?>', decoded):
                entry = entry.strip()
                # Parse "M:SS — Unit Name" (mdash or regular dash)
                m = re.match(r'(\d+):(\d+)\s*[—–-]\s*(.+)', entry)
                if m:
                    minutes, seconds, unit = int(m.group(1)), int(m.group(2)), m.group(3).strip()
                    total_seconds = minutes * 60 + seconds
                    lede = ""
                    if unit.startswith("Selects "):
                        lede = "Selects "
                        unit = unit[8:]  # strip "Selects " prefix
                    elif unit.startswith("Construct "):
                        lede = "Construct "
                    actions.append({
                        "lede": lede,
                        "name": unit,
                        "time": total_seconds,
                    })

        if actions:
            players_data.append({
                "name": name,
                "actions": actions,
            })

    # Duration: look for duration text on the page
    dur_match = re.search(r'(\d+):(\d+)\s*</span>\s*<span[^>]*>Duration', page_html, re.DOTALL)
    if not dur_match:
        # Try alternative: Duration label then value
        dur_match = re.search(r'Duration</span>\s*<span[^>]*>(\d+):(\d+)', page_html, re.DOTALL)
    duration_s = None
    if dur_match:
        duration_s = int(dur_match.group(1)) * 60 + int(dur_match.group(2))

    return players_data, duration_s


def scrape_build_orders(replay_id: int) -> tuple[list[dict], int | None, str | None, str | None]:
    """
    Scrape build order data from /replays/{id}/builds + patch + map from overview.
    Returns (list of player build orders, match_duration_seconds, patch_version, map_name).
    Supports both old (data-timeline JSON) and new (Hotwire tooltip) formats.
    """
    url = f"{COHDB_BASE}/replays/{replay_id}/builds"
    page_html = fetch_page(url)
    if not page_html:
        return [], None, None, None

    # Try old format first (data-timeline-players-value JSON blob)
    players_data, duration_s = _parse_builds_old_format(page_html)

    # Fall back to new format (Hotwire tooltips)
    if not players_data:
        players_data, duration_s = _parse_builds_new_format(page_html)

    if not players_data:
        return [], None, None, None

    # Fetch patch + map from overview page
    time.sleep(REQUEST_DELAY)
    patch, map_name = scrape_replay_overview(replay_id)

    return players_data, duration_s, patch, map_name


def is_ai_player_name(name: str) -> bool:
    """Detect AI/CPU players to filter out skirmish-vs-AI games."""
    if not name:
        return False
    n = name.strip()
    # CPU prefix in any localization
    if n.startswith("CPU") or n.startswith("CPU-") or n.startswith("CPU "):
        return True
    # AI Takeover marker
    if "AI Takeover" in n or n == "AI":
        return True
    return False


def store_replay_build_orders(replay_id: int, players_data: list[dict],
                               duration_s: int | None, patch: str | None,
                               map_name: str | None, conn):
    """Store build order data for a replay. Skips replays with AI players."""
    # Skip games with any CPU/AI player - these are skirmishes, not 1v1 ranked
    # Still insert a cohdb_replays row so we don't re-fetch on next run
    for player in players_data:
        if is_ai_player_name(player.get("name", "")):
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO cohdb_replays (replay_id, duration_s, mode, patch, map_name, scraped_at)
                VALUES (?, ?, 'ai_skipped', ?, ?, ?)
                ON CONFLICT(replay_id) DO NOTHING
            """, (replay_id, duration_s, patch, map_name, now))
            return 0

    now = datetime.now(timezone.utc).isoformat()

    # Clear any existing build orders for this replay (in case of re-scrape)
    conn.execute("DELETE FROM build_orders WHERE replay_id = ?", (replay_id,))

    # Upsert the replay record
    conn.execute("""
        INSERT INTO cohdb_replays (replay_id, duration_s, mode, patch, map_name, scraped_at)
        VALUES (?, ?, 'ranked_1v1', ?, ?, ?)
        ON CONFLICT(replay_id) DO UPDATE SET
            duration_s=excluded.duration_s,
            patch=excluded.patch,
            map_name=COALESCE(excluded.map_name, cohdb_replays.map_name),
            scraped_at=excluded.scraped_at
    """, (replay_id, duration_s, patch, map_name, now))

    total_actions = 0
    for player in players_data:
        name = player.get("name", "unknown")
        actions = player.get("actions", [])

        for action in actions:
            # Support both old format (seconds/unit) and new format (time/name)
            seconds = action.get("seconds", action.get("time", 0))
            unit = action.get("unit", action.get("name", ""))
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

    cursor = None
    for page in range(1, max_pages + 1):
        replay_ids, cursor = scrape_match_listing(page, elo, cursor=cursor)
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
            players_data, duration_s, patch, map_name = scrape_build_orders(rid)

            if not players_data:
                print("no build data")
                time.sleep(REQUEST_DELAY)
                continue

            actions = store_replay_build_orders(rid, players_data, duration_s, patch, map_name, conn)
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
