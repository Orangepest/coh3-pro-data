#!/usr/bin/env python3
"""
CoH3 1v1 Pro Scene Data Pipeline - Main Runner

Usage:
    python run.py scrape         # Run all scrapers (leaderboards + match history + cohdb)
    python run.py scrape-lb      # Scrape leaderboards only
    python run.py scrape-matches # Scrape match histories only
    python run.py scrape-cohdb   # Scrape cohdb build orders only (default 50 pages)
    python run.py scrape-cohdb 100  # Scrape cohdb with custom page count
    python run.py download       # Download coh3stats open data (last 30 days)
    python run.py download 90    # Download open data with custom day range
    python run.py analyze                # Run full analysis report (all patches)
    python run.py analyze --patch=2.3.1  # Analysis filtered to a specific patch
    python run.py patches                # List available patches and game counts
    python run.py player <name>          # Analyze a specific player's builds
    python run.py initdb                 # Initialize database only
"""

import sys
from db import init_db


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "initdb":
        init_db()

    elif cmd == "scrape-lb":
        from scrape_leaderboards import scrape_all_leaderboards
        scrape_all_leaderboards()

    elif cmd == "scrape-matches":
        from scrape_matches import scrape_all_match_histories
        scrape_all_match_histories()

    elif cmd == "scrape-cohdb":
        from scrape_cohdb import scrape_cohdb
        pages = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        scrape_cohdb(max_pages=pages)

    elif cmd == "scrape":
        from scrape_leaderboards import scrape_all_leaderboards
        from scrape_matches import scrape_all_match_histories
        from scrape_cohdb import scrape_cohdb

        scrape_all_leaderboards()
        scrape_all_match_histories()
        scrape_cohdb()

    elif cmd == "download":
        from download_open_data import download_recent
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        download_recent(days)

    elif cmd == "patches":
        from analyze import available_patches
        from tabulate import tabulate
        patches = available_patches()
        if patches.empty:
            print("No patch data yet. Run: python3 run.py scrape-cohdb")
        else:
            print(tabulate(patches, headers="keys", tablefmt="simple", showindex=False))

    elif cmd == "analyze":
        from analyze import full_report
        patch = None
        for arg in sys.argv[2:]:
            if arg.startswith("--patch="):
                patch = arg.split("=", 1)[1]
        full_report(patch=patch)

    elif cmd == "player":
        if len(sys.argv) < 3:
            print("Usage: python run.py player <player_name> [--patch=X.Y.Z]")
            return
        from analyze import load_build_orders_df, player_build_tendencies
        from tabulate import tabulate

        patch = None
        name_parts = []
        for arg in sys.argv[2:]:
            if arg.startswith("--patch="):
                patch = arg.split("=", 1)[1]
            else:
                name_parts.append(arg)
        name = " ".join(name_parts)
        bo = load_build_orders_df(patch=patch)
        result = player_build_tendencies(bo, name)

        if "error" in result:
            print(result["error"])
            print("\nAvailable players:")
            players = bo["player_name"].value_counts().head(20)
            print(tabulate(
                players.reset_index().rename(columns={"player_name": "player", "count": "actions"}),
                headers="keys", tablefmt="simple", showindex=False,
            ))
            return

        print(f"\n=== Player Analysis: {name} ({result['total_games']} games) ===\n")

        print("--- Favorite Openers (first 5 units) ---")
        print(tabulate(result["favorite_openers"], headers="keys", tablefmt="simple"))
        print()

        print("--- Battlegroup Picks ---")
        for bg, count in result["battlegroups"].items():
            print(f"  {bg}: {count}")
        print()

        print("--- Most Built Units ---")
        for unit, count in result["most_built_units"].items():
            print(f"  {unit}: {count}")
        print()

        print(f"Avg actions per game: {result['avg_actions_per_game']}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
