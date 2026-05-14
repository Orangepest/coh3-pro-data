"""
One-shot backfill for cohdb_replays.map_name on rows scraped during the
cohdb Hotwire/Turbo site rewrite window (where the new-format regex was
broken and silently dropped map data). Idempotent — only touches rows
where map_name IS NULL.

Concurrent: 4 worker threads issue HTTP in parallel; results are queued
back to the main thread which does DB writes serially (avoids
intra-process write contention).

Re-uses scrape_replay_overview() from scrape_cohdb.py, which has the
patched regex baked in.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from db import get_conn
from scrape_cohdb import scrape_replay_overview


WORKERS = 4
COMMIT_EVERY = 50


def fetch_one(rid):
    """Worker: fetch overview, return (rid, patch, map_name). Never raises."""
    try:
        patch, map_name, _ = scrape_replay_overview(rid)
        return (rid, patch, map_name, None)
    except Exception as e:
        return (rid, None, None, str(e))


def main(limit=None):
    conn = get_conn()
    rows = conn.execute("""
        SELECT replay_id FROM cohdb_replays
        WHERE (map_name IS NULL OR map_name = '')
          AND mode = 'ranked_1v1'
        ORDER BY replay_id DESC
    """).fetchall()
    rids = [r["replay_id"] for r in rows]
    if limit:
        rids = rids[:limit]
    print(f"Backfilling {len(rids)} replays with {WORKERS} workers...\n", flush=True)

    n_recovered = 0
    n_still_null = 0
    n_api_fail = 0
    start = time.monotonic()

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_one, rid): rid for rid in rids}
        for i, fut in enumerate(as_completed(futures), 1):
            rid, patch, map_name, err = fut.result()
            if err:
                n_api_fail += 1
            elif map_name:
                conn.execute(
                    "UPDATE cohdb_replays SET map_name = ? WHERE replay_id = ?",
                    (map_name, rid),
                )
                n_recovered += 1
            else:
                n_still_null += 1

            if i % COMMIT_EVERY == 0:
                conn.commit()
                elapsed = time.monotonic() - start
                rate = i / elapsed
                eta = (len(rids) - i) / rate
                print(
                    f"  [{i}/{len(rids)}] recovered={n_recovered} still-null={n_still_null} "
                    f"api-fail={n_api_fail}  rate={rate:.1f}/s  eta={eta:.0f}s",
                    flush=True,
                )

    conn.commit()
    elapsed = time.monotonic() - start
    print(f"\n=== DONE in {elapsed:.0f}s ===", flush=True)
    print(f"  recovered:   {n_recovered}", flush=True)
    print(f"  still NULL:  {n_still_null}", flush=True)
    print(f"  api failure: {n_api_fail}", flush=True)
    conn.close()


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit=limit)
