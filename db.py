"""
Database schema and helpers for the CoH3 pro scene data pipeline.
"""

import sqlite3
from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            profile_id  INTEGER PRIMARY KEY,
            alias       TEXT,
            steam_id    TEXT,
            country     TEXT,
            last_updated TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard_entries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id      INTEGER NOT NULL,
            faction         TEXT NOT NULL,
            elo             INTEGER NOT NULL,
            wins            INTEGER NOT NULL,
            losses          INTEGER NOT NULL,
            rank            INTEGER,
            streak          INTEGER,
            scraped_at      TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES players(profile_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id        INTEGER PRIMARY KEY,
            map_name        TEXT,
            match_type      TEXT,
            start_time      INTEGER,
            duration_s      INTEGER,
            scraped_at      TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS match_players (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        INTEGER NOT NULL,
            profile_id      INTEGER NOT NULL,
            faction         TEXT,
            elo_before      INTEGER,
            elo_after       INTEGER,
            elo_diff        INTEGER,
            result          TEXT,  -- 'win' or 'loss'
            team_id         INTEGER,
            FOREIGN KEY (match_id) REFERENCES matches(match_id),
            FOREIGN KEY (profile_id) REFERENCES players(profile_id),
            UNIQUE(match_id, profile_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS cohdb_replays (
            replay_id       INTEGER PRIMARY KEY,
            match_id        INTEGER,
            map_name        TEXT,
            mode            TEXT,
            duration_s      INTEGER,
            result          TEXT,
            patch           TEXT,
            scraped_at      TEXT,
            FOREIGN KEY (match_id) REFERENCES matches(match_id)
        )
    """)

    # Add patch column if upgrading from older schema
    try:
        c.execute("ALTER TABLE cohdb_replays ADD COLUMN patch TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Add winner_side column ('allies' or 'axis') for opener winrate analysis
    try:
        c.execute("ALTER TABLE cohdb_replays ADD COLUMN winner_side TEXT")
    except sqlite3.OperationalError:
        pass

    # Per-player faction/side/result mapping for cohdb replays
    c.execute("""
        CREATE TABLE IF NOT EXISTS cohdb_replay_players (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            replay_id       INTEGER NOT NULL,
            player_name     TEXT NOT NULL,
            faction_slug    TEXT,
            side            TEXT,  -- 'allies' or 'axis'
            won             INTEGER,  -- 1 or 0
            FOREIGN KEY (replay_id) REFERENCES cohdb_replays(replay_id),
            UNIQUE(replay_id, player_name)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS build_orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            replay_id       INTEGER NOT NULL,
            player_name     TEXT NOT NULL,
            seconds         INTEGER NOT NULL,
            unit            TEXT NOT NULL,
            action_type     TEXT NOT NULL,  -- 'production', 'tech', 'battlegroup', 'ability'
            FOREIGN KEY (replay_id) REFERENCES cohdb_replays(replay_id)
        )
    """)

    # Indexes for common queries
    c.execute("CREATE INDEX IF NOT EXISTS idx_lb_profile ON leaderboard_entries(profile_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_lb_faction_elo ON leaderboard_entries(faction, elo)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_mp_match ON match_players(match_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_mp_profile ON match_players(profile_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_matches_time ON matches(start_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_matches_map ON matches(map_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bo_replay ON build_orders(replay_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bo_player ON build_orders(player_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bo_unit ON build_orders(unit)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_crp_replay ON cohdb_replay_players(replay_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_crp_player ON cohdb_replay_players(player_name)")
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
