"""
CoH3 1v1 Pro Scene Data Pipeline - Configuration
"""

import os

# --- ELO Filter ---
MIN_ELO = 1600

# --- Relic API ---
RELIC_API_BASE = "https://coh3-api.reliclink.com"
RELIC_TITLE = "coh3"

# 1v1 Leaderboard IDs per faction
LEADERBOARD_IDS = {
    "american": 2130255,
    "british": 2130257,
    "dak": 2130259,
    "german": 2130261,
}

# Race IDs (used in match data)
RACE_IDS = {
    129494: "american",
    137123: "german",
    197345: "british",
    198437: "dak",
    203852: "british_africa",
}

# Match type IDs
MATCH_TYPES = {
    1: "ranked_1v1",
    2: "ranked_2v2",
    3: "ranked_3v3",
    4: "ranked_4v4",
    20: "unranked_1v1",
    21: "unranked_2v2",
    22: "unranked_3v3",
    23: "unranked_4v4",
}

# --- coh3stats Open Data ---
COH3STATS_MATCHES_URL = "https://storage.coh3stats.com/matches/matches-{timestamp}.json"
COH3STATS_LEADERBOARD_URL = (
    "https://storage.coh3stats.com/leaderboards/{timestamp}/{timestamp}_{mode}_{faction}.json"
)

# --- Rate Limiting ---
REQUEST_DELAY = 1.0  # seconds between API requests
MAX_RETRIES = 3

# --- Patch boundaries ---
# Cohdb tags replays with a `patch` string. The Relic API does NOT, so we
# attribute Relic matches to a patch via their start_time and these cutoffs.
# Each entry: (patch_name, start_unix_utc). Sorted ascending.
# Append a new entry when Relic ships a balance/content patch.
PATCH_HISTORY = [
    # Everything in the DB prior to 2026-05-15 02:00 JST was on 2.3.1.
    # Earlier patches are not represented in our scrape window.
    ("2.3.1", 0),
    # 2026-05-15 02:00 JST = 2026-05-14 17:00 UTC. Placeholder name; update
    # once Relic announces the actual version string.
    ("2.4.0", 1778778000),
]

CURRENT_PATCH = PATCH_HISTORY[-1][0]


# --- Map name normalization ---
# Cohdb sometimes logs the same map under multiple names (e.g., the new
# Hotwire site uses both "faymonville" and "faymonville_2p" for the same
# scenario). Map all known variants to a single canonical form.
# Append entries when a new alias is discovered.
MAP_NAME_ALIASES = {
    "faymonville": "faymonville_2p",
}


def normalize_map_name(name):
    """Return the canonical form of a map name (handles cohdb suffix variants)."""
    if name is None:
        return None
    return MAP_NAME_ALIASES.get(name, name)


def patch_for_timestamp(ts):
    """Return the patch name a unix-epoch timestamp falls under, or None if ts is None."""
    if ts is None:
        return None
    result = PATCH_HISTORY[0][0]
    for name, start in PATCH_HISTORY:
        if ts >= start:
            result = name
        else:
            break
    return result

# --- Database ---
# Override with COH3DATA_DB_PATH env var (used by tests).
DB_PATH = os.environ.get(
    "COH3DATA_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "coh3_pro.db"),
)

# --- Scraping ---
LEADERBOARD_PAGE_SIZE = 200  # max per request
