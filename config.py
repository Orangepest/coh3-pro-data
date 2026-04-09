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

# --- Database ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coh3_pro.db")

# --- Scraping ---
LEADERBOARD_PAGE_SIZE = 200  # max per request
