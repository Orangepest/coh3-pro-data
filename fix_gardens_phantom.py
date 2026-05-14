"""
Cleanup #2 from the handoff queue: gardens_2p is a cohdb name-resolution
quirk. ~726 cohdb_replays are tagged map_name='gardens_2p' but they're
actually mixed real maps. Other claude verified via cross-check: cohdb's
page title contains `Match <relic_id>` which lets us join back to our
matches table for the authoritative map_name.

Strategy:
  1. For each gardens_2p replay, fetch /replays/<id> and extract Match ID
     from the <title> tag.
  2. Populate cohdb_replays.match_id from the extracted ID.
  3. Overwrite map_name by joining to matches.map_name. If the match isn't
     in our matches table (gap-fill brought in cohdb replays that Relic
     never returned to us), set map_name = NULL — the next weekly Relic
     scrape might catch it.

Concurrent: 4 workers for HTTP fetches, serialized DB writes.
"""

import re
import sys
import time
import html
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from db import get_conn
from config import REQUEST_DELAY, MAX_RETRIES


COHDB_BASE = "https://cohdb.com"
WORKERS = 4
COMMIT_EVERY = 50


def fetch_match_id(rid):
    """Worker: fetch /replays/<rid>, extract Relic match_id from title.
    Returns (rid, match_id_or_None, error_or_None)."""
    url = f"{COHDB_BASE}/replays/{rid}"
    headers = {"User-Agent": "CoH3ProAnalysis/1.0"}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=30, headers=headers)
            if resp.status_code == 404:
                return (rid, None, "404")
            resp.raise_for_status()
            page = resp.text
            # Title format: "Match <relic_id> | cohdb"
            m = re.search(r"<title>\s*Match\s+(\d+)", page, re.IGNORECASE)
            if m:
                return (rid, int(m.group(1)), None)
            return (rid, None, "no_match_id_in_title")
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
            else:
                return (rid, None, str(e))
    return (rid, None, "all_retries_failed")


def main():
    conn = get_conn()

    rows = conn.execute("""
        SELECT replay_id FROM cohdb_replays
        WHERE map_name = 'gardens_2p' AND mode = 'ranked_1v1'
        ORDER BY replay_id DESC
    """).fetchall()
    rids = [r["replay_id"] for r in rows]
    print(f"Re-attributing {len(rids)} 'gardens_2p' replays...\n", flush=True)

    n_resolved_map = 0
    n_match_not_in_db = 0
    n_no_title = 0
    n_404 = 0
    n_api_fail = 0
    start = time.monotonic()

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_match_id, rid): rid for rid in rids}
        for i, fut in enumerate(as_completed(futures), 1):
            rid, match_id, err = fut.result()
            if err == "404":
                n_404 += 1
            elif err == "no_match_id_in_title":
                n_no_title += 1
            elif err:
                n_api_fail += 1
            elif match_id:
                # Look up real map_name from matches
                row = conn.execute(
                    "SELECT map_name FROM matches WHERE match_id = ?",
                    (match_id,),
                ).fetchone()
                if row:
                    # Match is in our DB - link and use authoritative map_name
                    conn.execute(
                        "UPDATE cohdb_replays SET match_id = ?, map_name = ? WHERE replay_id = ?",
                        (match_id, row["map_name"], rid),
                    )
                    n_resolved_map += 1
                else:
                    # Match not in our Relic-side DB - can't set match_id (FK
                    # violation), just clear the bad gardens_2p map_name.
                    conn.execute(
                        "UPDATE cohdb_replays SET map_name = NULL WHERE replay_id = ?",
                        (rid,),
                    )
                    n_match_not_in_db += 1

            if i % COMMIT_EVERY == 0:
                conn.commit()
                elapsed = time.monotonic() - start
                rate = i / elapsed
                eta = (len(rids) - i) / rate if rate else 0
                print(
                    f"  [{i}/{len(rids)}] map-resolved={n_resolved_map} "
                    f"match-not-in-db={n_match_not_in_db} no-title={n_no_title} "
                    f"404={n_404} api-fail={n_api_fail}  rate={rate:.1f}/s eta={eta:.0f}s",
                    flush=True,
                )

    conn.commit()
    elapsed = time.monotonic() - start
    print(f"\n=== DONE in {elapsed:.0f}s ===", flush=True)
    print(f"  map resolved via matches join: {n_resolved_map}", flush=True)
    print(f"  match_id found but not in DB:  {n_match_not_in_db}", flush=True)
    print(f"  no Match ID in page title:     {n_no_title}", flush=True)
    print(f"  404'd replays:                 {n_404}", flush=True)
    print(f"  API failures:                  {n_api_fail}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
